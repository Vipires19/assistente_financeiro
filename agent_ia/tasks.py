"""
Tasks Celery para lembretes de compromissos.
Envio via WAHA centralizado em services.waha_sender (mesma lógica do app).
"""
import logging
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytz
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from celery_app import celery

# Garantir import do services na raiz do projeto (financeiro)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from services.waha_sender import enviar_mensagem_waha  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("worker_lembretes")

# ---------------------------------------------------------------------------
# Config (sem MongoClient global)
# ---------------------------------------------------------------------------
MONGO_USER = urllib.parse.quote_plus(os.getenv("MONGO_USER", ""))
MONGO_PASS = urllib.parse.quote_plus(os.getenv("MONGO_PASS", ""))
TZ = pytz.timezone("America/Sao_Paulo")
LIMITE_12H = timedelta(hours=12)
LIMITE_1H = timedelta(hours=1)


def get_mongo_colls() -> Tuple[Collection, Collection, Collection]:
    """
    Retorna (compromissos, users, despesas_fixas) criando um novo MongoClient.
    Deve ser chamado dentro da task para evitar uso de cliente global após fork do Celery.
    """
    client = MongoClient(
        "mongodb+srv://%s:%s@cluster0.gjkin5a.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        % (MONGO_USER, MONGO_PASS)
    )
    db = client.financeiro_db
    return db.compromissos, db.users, db.despesas_fixas


def _intervalo_dia_civil_brasilia_utc(agora_brasilia: datetime) -> Tuple[datetime, datetime]:
    """
    Retorna (início do dia civil em America/Sao_Paulo, início do dia seguinte), em UTC aware,
    para comparação no MongoDB (uma data civil completa, sem depender só do mês).
    """
    d = agora_brasilia.date()
    inicio_sp = TZ.localize(datetime.combine(d, dt_time.min))
    fim_sp = inicio_sp + timedelta(days=1)
    return inicio_sp.astimezone(timezone.utc), fim_sp.astimezone(timezone.utc)


def _filtro_mongo_ultimo_envio_nao_foi_hoje_brasilia(
    agora_brasilia: datetime,
) -> Dict[str, Any]:
    """
    Documentos em que ultimo_envio NÃO cai no intervalo [hoje 00:00, amanhã 00:00) em Brasília.
    Compatível com valores naive em UTC legados (comparados como instantes no BSON).
    """
    inicio_utc, fim_utc = _intervalo_dia_civil_brasilia_utc(agora_brasilia)
    return {
        "$or": [
            {"ultimo_envio": {"$exists": False}},
            {"ultimo_envio": None},
            {"ultimo_envio": {"$lt": inicio_utc}},
            {"ultimo_envio": {"$gte": fim_utc}},
        ]
    }


def _rollback_ultimo_envio(
    coll: Collection, desp_id: Any, valor_anterior: Any
) -> None:
    """Restaura ultimo_envio após falha no envio (permite nova tentativa no mesmo dia)."""
    try:
        if valor_anterior is None:
            coll.update_one({"_id": desp_id}, {"$unset": {"ultimo_envio": ""}})
        else:
            coll.update_one({"_id": desp_id}, {"$set": {"ultimo_envio": valor_anterior}})
    except Exception as e:
        logger.error("rollback ultimo_envio _id=%s: %s", desp_id, e)


def _formatar_moeda_brl(val: Any) -> str:
    """Valor numérico como string pt-BR (ex.: 1.234,56), para uso em mensagens."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        v = 0.0
    neg = v < 0
    v = abs(v)
    s = f"{v:.2f}"
    intp, frac = s.split(".")
    parts: list[str] = []
    while intp:
        parts.insert(0, intp[-3:])
        intp = intp[:-3]
    int_fmt = ".".join(parts)
    prefix = "-" if neg else ""
    return f"{prefix}{int_fmt},{frac}"


# Link da página de planos (env ou fallback)
LINK_PLANOS = os.getenv("LINK_PLANOS", "https://vipires19.pythonanywhere.com/planos/")


def construir_datetime_compromisso(compromisso: dict) -> Optional[datetime]:
    """
    Converte data + hora_inicio do compromisso em datetime timezone-aware (America/Sao_Paulo).
    Retorna None se faltar data ou hora_inicio.
    """
    try:
        data_field = compromisso.get("data")
        if data_field is None:
            return None
        if hasattr(data_field, "date"):
            data_val = data_field.date()
        else:
            data_val = data_field
        hora_str = compromisso.get("hora_inicio") or compromisso.get("hora")
        if not hora_str:
            return None
        parts = str(hora_str).strip().split(":")
        if len(parts) != 2:
            return None
        h, m = int(parts[0]), int(parts[1])
        t = dt_time(h, m)
        dt_naive = datetime.combine(data_val, t)
        return TZ.localize(dt_naive)
    except Exception as e:
        logger.error("construir_datetime_compromisso: %s", e)
        return None


@celery.task
def verificar_lembretes() -> None:
    """
    Executa a checagem de compromissos e envia lembretes (12h e 1h antes).
    Toda a lógica anterior do worker_lembretes.py está aqui.
    """
    coll_compromissos, coll_clientes, coll_despesas_fixas = get_mongo_colls()
    now = datetime.now(TZ)
    logger.info("Verificando compromissos...")

    # ----- Janela 12h: lembrete (se confirmado) ou pedido de confirmação (se não confirmado) -----
    cursor_12h = coll_compromissos.find({
        "status": {"$ne": "cancelado"},
        "$or": [
            {"lembrete_12h_enviado": {"$ne": True}},
            {"confirmacao_enviada": {"$ne": True}},
        ],
    })
    for comp in cursor_12h:
        try:
            dt_comp = construir_datetime_compromisso(comp)
            if dt_comp is None:
                continue
            diff = dt_comp - now
            if diff <= timedelta(0) or diff > LIMITE_12H:
                continue
            user_id = comp.get("user_id")
            if not user_id:
                continue
            user_id = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
            cliente = coll_clientes.find_one({"_id": user_id})
            if not cliente:
                continue
            telefone = cliente.get("telefone") or cliente.get("phone")
            if not telefone:
                continue
            titulo = comp.get("titulo") or comp.get("descricao") or "Compromisso"
            hora_inicio = comp.get("hora_inicio") or comp.get("hora") or ""
            data_formatada = dt_comp.strftime("%d/%m/%Y")
            codigo = str(comp["_id"])[:6]

            # Considera confirmado se flag explícita ou status confirmado (compatibilidade)
            ja_confirmado = comp.get("confirmado_usuario") or comp.get("status") == "confirmado"
            if ja_confirmado:
                # Já confirmado → enviar lembrete 12h (uma vez)
                filtro = {
                    "_id": comp["_id"],
                    "lembrete_12h_enviado": {"$ne": True},
                }
                result = coll_compromissos.update_one(
                    filtro,
                    {"$set": {"lembrete_12h_enviado": True}},
                )
                if result.modified_count == 1:
                    texto = (
                        "🔔 Lembrete!\n"
                        "Em 12 horas você tem o compromisso:\n\n"
                        f"📅 {titulo}\n"
                        f"🕒 {data_formatada} às {hora_inicio}"
                    )
                    if enviar_mensagem_waha(telefone, texto):
                        logger.info("Lembrete 12h enviado para %s — %s", telefone, titulo)
            else:
                # Não confirmado → enviar pedido de confirmação (uma vez)
                filtro = {
                    "_id": comp["_id"],
                    "confirmacao_enviada": {"$ne": True},
                }
                result = coll_compromissos.update_one(
                    filtro,
                    {
                        "$set": {
                            "confirmacao_enviada": True,
                            "confirmacao_pendente": True,
                            "codigo_confirmacao": codigo,
                        }
                    },
                )
                if result.modified_count == 1:
                    texto = (
                        "Você confirma este compromisso?\n\n"
                        f"📅 {titulo}\n"
                        f"🕒 {data_formatada} às {hora_inicio}\n\n"
                        "Responda:\n"
                        f"CONFIRMAR {codigo}\n"
                        "ou\n"
                        f"CANCELAR {codigo}"
                    )
                    if enviar_mensagem_waha(telefone, texto):
                        logger.info("Pedido de confirmação enviado para %s — %s", telefone, titulo)
        except Exception as e:
            logger.error("Erro ao processar compromisso 12h _id=%s: %s", comp.get("_id"), e)

    # ----- Lembrete 1h (status confirmado) — update atômico para envio único -----
    cursor_1h = coll_compromissos.find({
        "status": {"$ne": "cancelado"},
        "$or": [
            {"status": "confirmado"},
            {"confirmado_usuario": True},
        ],
        "lembrete_1h_enviado": {"$ne": True},
    })
    for comp in cursor_1h:
        try:
            dt_comp = construir_datetime_compromisso(comp)
            if dt_comp is None:
                continue
            diff = dt_comp - now
            if diff <= timedelta(minutes=0) or diff > LIMITE_1H:
                continue
            user_id = comp.get("user_id")
            if not user_id:
                continue
            user_id = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
            cliente = coll_clientes.find_one({"_id": user_id})
            if not cliente:
                continue
            telefone = cliente.get("telefone") or cliente.get("phone")
            if not telefone:
                continue
            titulo = comp.get("titulo") or comp.get("descricao") or "Compromisso"
            hora_inicio = comp.get("hora_inicio") or comp.get("hora") or ""
            # Update atômico: só marca se ainda não foi marcado (evita race condition)
            result = coll_compromissos.update_one(
                {"_id": comp["_id"], "lembrete_1h_enviado": {"$ne": True}},
                {"$set": {"lembrete_1h_enviado": True}},
            )
            if result.modified_count == 1:
                texto = (
                    "🔔 Lembrete!\n"
                    "Seu compromisso começa em 1 hora:\n\n"
                    f"📅 {titulo}\n"
                    f"🕒 {hora_inicio}"
                )
                if enviar_mensagem_waha(telefone, texto):
                    logger.info("Lembrete 1h enviado para %s — %s", telefone, titulo)
        except Exception as e:
            logger.error("Erro ao processar compromisso 1h _id=%s: %s", comp.get("_id"), e)

    # ----- Despesas fixas: 1 envio por dia civil (Brasil), seguro com vários workers -----
    # Claim atômico no Mongo (ultimo_envio ainda não é "hoje" em SP); rollback se WA falhar.
    logger.info("Verificando despesas fixas (dia %s)...", now.day)
    try:
        filtro_nao_enviou_hoje = _filtro_mongo_ultimo_envio_nao_foi_hoje_brasilia(now)
        cursor_df = coll_despesas_fixas.find(
            {
                "ativo": True,
                "dia_vencimento": now.day,
                **filtro_nao_enviou_hoje,
            }
        )
        for desp in cursor_df:
            antigo_ultimo = desp.get("ultimo_envio")
            claimed = False
            try:
                agora_sp = datetime.now(TZ)
                # Reserva o slot do dia: só um worker altera (modified_count == 1)
                claim = coll_despesas_fixas.update_one(
                    {
                        "_id": desp["_id"],
                        "ativo": True,
                        "dia_vencimento": now.day,
                        **filtro_nao_enviou_hoje,
                    },
                    {"$set": {"ultimo_envio": agora_sp}},
                )
                if claim.modified_count != 1:
                    continue
                claimed = True

                user_id = desp.get("user_id")
                if not user_id:
                    _rollback_ultimo_envio(
                        coll_despesas_fixas, desp["_id"], antigo_ultimo
                    )
                    continue
                user_id = (
                    ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
                )
                cliente = coll_clientes.find_one({"_id": user_id})
                if not cliente:
                    _rollback_ultimo_envio(
                        coll_despesas_fixas, desp["_id"], antigo_ultimo
                    )
                    continue
                telefone = cliente.get("telefone") or cliente.get("phone")
                if not telefone:
                    _rollback_ultimo_envio(
                        coll_despesas_fixas, desp["_id"], antigo_ultimo
                    )
                    continue
                nome = (desp.get("nome") or "").strip() or "despesa fixa"
                valor_fmt = _formatar_moeda_brl(desp.get("valor"))
                texto = (
                    "💸 Lembrete financeiro\n\n"
                    "Hoje é o dia de pagar:\n"
                    f"📌 {nome}\n"
                    f"💰 R$ {valor_fmt}\n\n"
                    "Não esqueça de registrar depois 😉"
                )
                if enviar_mensagem_waha(telefone, texto):
                    logger.info(
                        "Lembrete despesa fixa enviado para %s — %s",
                        telefone,
                        nome,
                    )
                else:
                    _rollback_ultimo_envio(
                        coll_despesas_fixas, desp["_id"], antigo_ultimo
                    )
                    logger.warning(
                        "Falha WA despesa fixa _id=%s — ultimo_envio revertido",
                        desp.get("_id"),
                    )
            except Exception as e:
                logger.error(
                    "Erro ao processar despesa fixa _id=%s: %s",
                    desp.get("_id"),
                    e,
                )
                if claimed:
                    try:
                        _rollback_ultimo_envio(
                            coll_despesas_fixas, desp["_id"], antigo_ultimo
                        )
                    except Exception:
                        pass
    except Exception as e:
        logger.error("verificar_lembretes despesas fixas: %s", e)


@celery.task
def enviar_confirmacao(compromisso_id: str) -> bool:
    """
    Envia mensagem de confirmação (lembrete 12h) para um único compromisso por ID.
    Útil para disparo sob demanda. Retorna True se enviou com sucesso.
    """
    coll_compromissos, coll_clientes, _ = get_mongo_colls()
    try:
        comp = coll_compromissos.find_one({
            "_id": ObjectId(compromisso_id),
            "status": "pendente",
            "lembrete_12h_enviado": {"$ne": True},
        })
        if not comp:
            return False
        user_id = comp.get("user_id")
        if not user_id:
            return False
        user_id = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        cliente = coll_clientes.find_one({"_id": user_id})
        if not cliente:
            return False
        telefone = cliente.get("telefone") or cliente.get("phone")
        if not telefone:
            return False
        titulo = comp.get("titulo") or comp.get("descricao") or "Compromisso"
        hora_inicio = comp.get("hora_inicio") or comp.get("hora") or ""
        dt_comp = construir_datetime_compromisso(comp)
        data_formatada = dt_comp.strftime("%d/%m/%Y") if dt_comp else ""
        codigo = str(comp["_id"])[:6]
        texto = (
            "Você confirma este compromisso?\n\n"
            f"📅 {titulo}\n"
            f"🕒 {data_formatada} às {hora_inicio}\n\n"
            "Responda:\n"
            f"CONFIRMAR {codigo}\n"
            "ou\n"
            f"CANCELAR {codigo}"
        )
        if enviar_mensagem_waha(telefone, texto):
            coll_compromissos.update_one(
                {"_id": comp["_id"]},
                {
                    "$set": {
                        "lembrete_12h_enviado": True,
                        "confirmacao_pendente": True,
                        "codigo_confirmacao": codigo,
                    }
                },
            )
            logger.info("Lembrete 12h enviado para %s — %s (enviar_confirmacao)", telefone, titulo)
            return True
        return False
    except Exception as e:
        logger.error("enviar_confirmacao compromisso_id=%s: %s", compromisso_id, e)
        return False


@celery.task
def verificar_trial_expirado() -> None:
    """
    Busca usuários em trial com trial_end < agora e trial_notificado != True.
    Atualiza para sem_plano/expirado, marca trial_notificado e envia aviso no WhatsApp.
    Usa a mesma função centralizada enviar_mensagem_waha (lembretes).
    """
    _, coll_clientes, _ = get_mongo_colls()
    now = datetime.now(timezone.utc)
    # Usuários em trial com fim < agora e ainda não notificados (top-level ou assinatura)
    cursor = coll_clientes.find({
        "$and": [
            {"$or": [{"plano": "trial"}, {"assinatura.plano": "trial"}]},
            {"$or": [
                {"trial_end": {"$lt": now}},
                {"assinatura.fim": {"$lt": now}},
            ]},
            {"trial_notificado": {"$ne": True}},
        ]
    })
    for user in cursor:
        try:
            user_id = user.get("_id")
            if not user_id:
                continue
            telefone = user.get("telefone") or user.get("phone")
            if not telefone:
                logger.warning("verificar_trial_expirado: user %s sem telefone", user_id)
            else:
                texto = (
                    "⏳ Seu período de teste gratuito terminou.\n\n"
                    "Espero que você tenha aproveitado esses 7 dias para conhecer tudo que posso fazer por você 😉\n\n"
                    "Para continuar utilizando todas as funcionalidades do Leozera, escolha um dos planos disponíveis:\n\n"
                    f"👉 {LINK_PLANOS}\n\n"
                    "Se precisar de ajuda, estou aqui pra você."
                )
                if enviar_mensagem_waha(telefone, texto):
                    logger.info("Aviso trial expirado enviado para %s", telefone)
                else:
                    logger.warning("Falha ao enviar aviso trial expirado para %s", telefone)
            coll_clientes.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "plano": "sem_plano",
                        "status_pagamento": "expirado",
                        "trial_notificado": True,
                        "assinatura.plano": "sem_plano",
                        "assinatura.status": "inativa",
                        "updated_at": now,
                    }
                },
            )
            logger.info("Trial expirado processado: user_id=%s", user_id)
        except Exception as e:
            logger.error("verificar_trial_expirado: erro user_id=%s: %s", user.get("_id"), e)


@celery.task
def verificar_planos_vencidos() -> None:
    """
    Rebaixa automaticamente usuários cujo plano venceu.
    Considera assinatura.status em ["ativa", "cancelada"]: ambos mantêm acesso até
    assinatura.proximo_vencimento. Só após passar o vencimento o plano é encerrado
    (assinatura.plano = "sem_plano", assinatura.status = "inativa").
    """
    _, coll_clientes, _ = get_mongo_colls()
    now = datetime.now(timezone.utc)
    cursor = coll_clientes.find({
        "assinatura.status": {"$in": ["ativa", "cancelada"]},
        "assinatura.proximo_vencimento": {"$exists": True, "$lt": now},
    })
    for user in cursor:
        try:
            user_id = user.get("_id")
            if not user_id:
                continue
            coll_clientes.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "assinatura.plano": "sem_plano",
                        "assinatura.status": "inativa",
                        "downgraded_at": now,
                        "updated_at": now,
                    }
                },
            )
            logger.info("[DOWNGRADE] Usuário %s rebaixado para sem_plano", user_id)
        except Exception as e:
            logger.error("verificar_planos_vencidos: erro user_id=%s: %s", user.get("_id"), e)
