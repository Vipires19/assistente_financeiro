"""
Serviço para lógica de trial (período de teste).

Localização: core/services/trial_service.py
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.repositories.user_repository import UserRepository


def _utcnow():
    return datetime.now(timezone.utc)


def iniciar_trial(user_repo: "UserRepository", user_id: str) -> Optional[datetime]:
    """
    Inicia o período de trial de 7 dias para o usuário, se ainda não tiver plano ativo.

    Regras:
    - Não sobrescreve se já existir plano ativo (trial, mensal, anual com fim > agora).
    - Define assinatura (plano, inicio, fim, status) e campos no usuário:
      trial_start, trial_end, status_pagamento.

    Returns:
        datetime do trial_end (fim do trial) se o trial foi iniciado/atualizado,
        None se não foi alterado (já tinha plano ativo).
    """
    user = user_repo.find_by_id(user_id)
    if not user:
        return None
    now = _utcnow()
    assinatura = user.get("assinatura") or {}
    plano = assinatura.get("plano") or user.get("plano")
    fim = assinatura.get("proximo_vencimento") or assinatura.get("fim") or user.get("data_vencimento_plano")
    # Já tem plano ativo e não expirado
    if plano in ("trial", "mensal", "anual") and fim:
        try:
            if getattr(fim, "tzinfo", None) is None:
                fim = fim.replace(tzinfo=timezone.utc)
            if fim > now:
                return fim
        except (TypeError, AttributeError):
            pass
    # Iniciar ou reiniciar trial
    trial_start = now
    trial_end = now + timedelta(days=7)
    user_repo.update(
        user_id,
        assinatura={
            "plano": "trial",
            "status": "ativa",
            "inicio": trial_start,
            "fim": trial_end,
            "renovacao_automatica": assinatura.get("renovacao_automatica", False),
            "gateway": assinatura.get("gateway"),
            "gateway_subscription_id": assinatura.get("gateway_subscription_id"),
            "ultimo_pagamento_em": assinatura.get("ultimo_pagamento_em"),
            "proximo_vencimento": assinatura.get("proximo_vencimento"),
        },
        plano="trial",
        trial_start=trial_start,
        trial_end=trial_end,
        status_pagamento="trial",
    )
    return trial_end
