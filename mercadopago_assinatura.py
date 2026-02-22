"""
Integração Mercado Pago: assinatura recorrente (preapproval).
Rotas: POST /api/assinar/<plano>, POST /api/webhook/mercadopago.
Não altera Agent, Celery nem worker de downgrade.
"""
import os
import logging
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
import requests
from bson import ObjectId
from flask import request, jsonify
from pymongo import MongoClient

logger = logging.getLogger("mercadopago_assinatura")

# Config (será injetado pelo app)
MONGO_USER = None
MONGO_PASS = None
MP_ACCESS_TOKEN = None
MP_WEBHOOK_SECRET = None
BACK_URL_BASE = None
_client = None
_coll_usuarios = None

MP_PREAPPROVAL_URL = "https://api.mercadopago.com/preapproval"

PLANOS_CONFIG = {
    "mensal": {
        "reason": "Plano Mensal Leozera",
        "frequency": 1,
        "frequency_type": "months",
        "transaction_amount": 29.90,
    },
    "anual": {
        "reason": "Plano Anual Leozera",
        "frequency": 12,
        "frequency_type": "months",
        "transaction_amount": 296.90,
    },
}


def _get_coll_usuarios():
    global _client, _coll_usuarios
    if _coll_usuarios is not None:
        return _coll_usuarios
    if not MONGO_USER or not MONGO_PASS:
        raise RuntimeError("MONGO_USER/MONGO_PASS não configurados para assinatura")
    _client = MongoClient(
        "mongodb+srv://%s:%s@cluster0.gjkin5a.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        % (MONGO_USER, MONGO_PASS)
    )
    _coll_usuarios = _client.financeiro_db.users
    return _coll_usuarios


def get_current_user():
    """
    Retorna o usuário autenticado a partir do request.
    Espera header X-User-Id (MongoDB _id) ou Authorization Bearer com user_id.
    Retorna (user_doc, None) ou (None, (json_response, status_code)).
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id and request.headers.get("Authorization"):
        # Opcional: Bearer <user_id> para compatibilidade
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            user_id = auth[7:].strip()
    if not user_id:
        return None, (jsonify({"error": "Não autenticado", "message": "Header X-User-Id ou Authorization obrigatório"}), 401)
    try:
        coll = _get_coll_usuarios()
        user = coll.find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        logger.exception("Erro ao buscar usuário: %s", e)
        return None, (jsonify({"error": "Erro interno"}), 500)
    if not user:
        return None, (jsonify({"error": "Usuário não encontrado"}), 404)
    return user, None


def _chamar_mp_preapproval(body):
    """POST em /preapproval. Retorna (data_dict, None) ou (None, error_msg)."""
    if not MP_ACCESS_TOKEN:
        return None, "MP_ACCESS_TOKEN não configurado"
    try:
        r = requests.post(
            MP_PREAPPROVAL_URL,
            headers={
                "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
        data = r.json() if r.text else {}
        if r.status_code != 201 and r.status_code != 200:
            return None, data.get("message", data.get("error", r.text or f"HTTP {r.status_code}"))
        return data, None
    except requests.RequestException as e:
        logger.exception("Erro ao chamar MP preapproval: %s", e)
        return None, str(e)


def _buscar_preapproval_mp(preapproval_id):
    """GET /preapproval/{id}. Retorna (data_dict, None) ou (None, error_msg). Nunca confiar só no webhook."""
    if not MP_ACCESS_TOKEN:
        return None, "MP_ACCESS_TOKEN não configurado"
    try:
        r = requests.get(
            f"{MP_PREAPPROVAL_URL}/{preapproval_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        data = r.json() if r.text else {}
        if r.status_code != 200:
            return None, data.get("message", data.get("error", r.text or f"HTTP {r.status_code}"))
        return data, None
    except requests.RequestException as e:
        logger.exception("Erro ao buscar preapproval MP: %s", e)
        return None, str(e)


def assinar_plano_for_user_id(plano, user_id):
    """
    Lógica de criação de preapproval no MP para um user_id (ex.: vindo da sessão).
    Retorna (checkout_url, None) ou (None, {"error": str, "message": str, "status": int}).
    Usado pelo Django (session) ou por qualquer chamador que já tenha o user_id.
    """
    if plano not in PLANOS_CONFIG:
        return None, {"error": "Plano inválido", "message": "Use 'mensal' ou 'anual'", "status": 400}
    try:
        coll = _get_coll_usuarios()
        user = coll.find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        logger.exception("Erro ao buscar usuário: %s", e)
        return None, {"error": "Erro interno", "message": "Erro ao buscar usuário", "status": 500}
    if not user:
        return None, {"error": "Usuário não encontrado", "message": "Usuário não encontrado", "status": 404}

    email = user.get("email")
    if not email:
        return None, {"error": "Usuário sem email", "message": "Cadastre um email para assinar", "status": 400}

    config = PLANOS_CONFIG[plano]
    back_url = (BACK_URL_BASE or "").rstrip("/") + "/pagamento/sucesso"
    if not BACK_URL_BASE:
        back_url = os.getenv("BACK_URL", "https://SEU_DOMINIO/pagamento/sucesso")

    body = {
        "reason": config["reason"],
        "auto_recurring": {
            "frequency": config["frequency"],
            "frequency_type": config["frequency_type"],
            "transaction_amount": config["transaction_amount"],
            "currency_id": "BRL",
        },
        "payer_email": email,
        "back_url": back_url,
        "status": "pending",
    }

    data, err = _chamar_mp_preapproval(body)
    if err:
        return None, {"error": "Mercado Pago", "message": err, "status": 502}

    mp_id = data.get("id")
    init_point = data.get("init_point")
    if not mp_id or not init_point:
        return None, {"error": "Resposta inválida do Mercado Pago", "message": "Resposta inválida do Mercado Pago", "status": 502}

    try:
        coll.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "mercadopago_subscription_id": mp_id,
                    "plano_solicitado": plano,
                    "status_assinatura": "pendente_pagamento",
                    "assinatura.gateway": "mercadopago",
                    "assinatura.gateway_subscription_id": mp_id,
                    "assinatura.status": "pendente_pagamento",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception as e:
        logger.exception("Erro ao salvar assinatura no Mongo: %s", e)
        return None, {"error": "Erro ao registrar assinatura", "message": "Erro ao registrar assinatura", "status": 500}

    return init_point, None


def assinar_plano(plano):
    """
    POST /api/assinar/<plano>
    Cria preapproval no MP, salva no Mongo e retorna checkout_url.
    Apenas sessão: nenhum fallback por header. Sem sessão válida → 401.
    """
    if plano not in ("mensal", "anual"):
        return jsonify({"error": "Plano inválido", "message": "Use 'mensal' ou 'anual'"}), 400

    user_id = None
    if hasattr(request, "session") and getattr(request, "session", None):
        user_id = request.session.get("user_id")
    if not user_id:
        return jsonify({"error": "Não autenticado", "message": "É necessário fazer login para assinar."}), 401

    checkout_url, err = assinar_plano_for_user_id(plano, user_id)
    if err:
        return jsonify({"error": err["error"], "message": err.get("message", err["error"])}), err.get("status", 500)
    return jsonify({"checkout_url": checkout_url}), 200


def webhook_mercadopago():
    """
    POST /api/webhook/mercadopago
    Só processa type == "preapproval". Sempre consulta a API do MP antes de atualizar.
    """
    payload = request.get_json(silent=True) or {}
    event_type = payload.get("type")
    if event_type != "preapproval":
        return jsonify({"status": "ignored"}), 200

    # Id da assinatura pode vir em data.id ou action.id conforme documentação MP
    data = payload.get("data", {}) or payload.get("action", {})
    preapproval_id = data.get("id") if isinstance(data, dict) else None
    if not preapproval_id and isinstance(payload.get("data"), str):
        preapproval_id = payload["data"]

    if not preapproval_id:
        logger.warning("Webhook MP sem id de preapproval: %s", payload)
        return jsonify({"status": "ignored"}), 200

    # Segurança: sempre consultar API do Mercado Pago antes de atualizar
    mp_data, err = _buscar_preapproval_mp(preapproval_id)
    if err or not mp_data:
        logger.warning("Não foi possível obter preapproval %s do MP: %s", preapproval_id, err)
        return jsonify({"status": "error", "message": "Falha ao validar assinatura no MP"}), 400

    status_mp = (mp_data.get("status") or "").lower()

    coll = _get_coll_usuarios()
    # Garantir que a assinatura pertence ao usuário correto: só atualizamos quem tem esse subscription_id
    sub_id_str = str(preapproval_id)
    user = coll.find_one({"mercadopago_subscription_id": sub_id_str})
    if not user:
        user = coll.find_one({"assinatura.gateway_subscription_id": sub_id_str})
    if not user:
        logger.warning("Nenhum usuário encontrado com mercadopago_subscription_id ou assinatura.gateway_subscription_id=%s", preapproval_id)
        return jsonify({"status": "ignored"}), 200

    now = datetime.now(timezone.utc)
    assinatura = user.get("assinatura") or {}

    if status_mp == "authorized":
        plano_solicitado = assinatura.get("plano_solicitado") or user.get("plano_solicitado") or "mensal"
        if plano_solicitado == "anual":
            data_vencimento = now + relativedelta(months=12)
        else:
            data_vencimento = now + relativedelta(months=1)

        subscription_id = str(preapproval_id)
        coll.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "plano": plano_solicitado,
                    "status_assinatura": "ativa",
                    "data_inicio_plano": now,
                    "data_vencimento_plano": data_vencimento,
                    "mercadopago_subscription_id": subscription_id,
                    "assinatura.plano": plano_solicitado,
                    "assinatura.status": "ativa",
                    "assinatura.inicio": now,
                    "assinatura.fim": data_vencimento,
                    "assinatura.proximo_vencimento": data_vencimento,
                    "assinatura.gateway": "mercadopago",
                    "assinatura.gateway_subscription_id": subscription_id,
                    "assinatura.ultimo_pagamento_em": now,
                    "updated_at": now,
                },
                "$unset": {
                    "plano_solicitado": "",
                },
            },
        )
        logger.info("Assinatura ativada: user_id=%s plano=%s", user["_id"], plano_solicitado)
    elif status_mp in ("cancelled", "paused", "expired", "rejected"):
        coll.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "plano": "sem_plano",
                    "status_assinatura": "cancelada",
                    "assinatura.plano": "sem_plano",
                    "assinatura.status": "cancelada",
                    "updated_at": now,
                }
            },
        )
        logger.info(
            "Assinatura cancelada/expirada: user_id=%s status=%s",
            user["_id"],
            status_mp,
        )
    else:
        logger.info("Status não tratado explicitamente: %s", status_mp)

    return jsonify({"status": "success"}), 200
