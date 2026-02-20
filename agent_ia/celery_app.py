"""
App Celery para o projeto Leozera.
Broker e backend: Redis. Tasks de lembretes em agent_ia.tasks.
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery = Celery(
    "leozera",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery.conf.update(
    timezone="America/Sao_Paulo",
    enable_utc=True,
    include=["tasks"],
)

# Celery Beat: lembretes a cada 5 min; trial expirado a cada 10 min; planos vencidos a cada 5 min
celery.conf.beat_schedule = {
    "verificar-lembretes-a-cada-5-minutos": {
        "task": "tasks.verificar_lembretes",
        "schedule": 300.0,
    },
    "verificar-trial-expirado": {
        "task": "tasks.verificar_trial_expirado",
        "schedule": 600.0,
    },
    "verificar-planos-vencidos": {
        "task": "tasks.verificar_planos_vencidos",
        "schedule": 300.0,
    },
}
