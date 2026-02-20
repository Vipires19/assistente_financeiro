"""
Serviço de insights financeiros gerados por IA.

Localização: finance/services/ai_insights.py

Função isolada para gerar insight, alerta e recomendação a partir de
dados consolidados, usando OpenAI (gpt-4o-mini).
"""
import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# OPENAI_API_KEY deve estar no .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Fallback seguro quando a API falha ou a resposta não é JSON válido
FALLBACK_RESPONSE = {
    "insight": "Não foi possível gerar a análise no momento. Tente novamente mais tarde.",
    "alerta": "",
    "recomendacao": "Verifique sua conexão e a configuração da OPENAI_API_KEY.",
}


def gerar_insights_financeiros(dados: dict) -> dict:
    """
    Gera insight estratégico, alerta e recomendação a partir de dados financeiros.

    Args:
        dados: Dicionário com dados consolidados (ex.: total_income, total_expenses,
               balance, day_with_highest_expense, category_with_highest_expense,
               hour_with_highest_expense).

    Returns:
        Dict com chaves: "insight", "alerta", "recomendacao".
        Em caso de erro, retorna fallback seguro (mesmo formato).
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY não configurada em ai_insights.")
        return {
            "insight": "Configure OPENAI_API_KEY no .env para receber análises automáticas.",
            "alerta": "",
            "recomendacao": "Adicione OPENAI_API_KEY nas variáveis de ambiente.",
        }

    try:
        dados_json = json.dumps(dados, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        logger.warning("Dados não serializáveis para JSON em gerar_insights_financeiros: %s", e)
        return FALLBACK_RESPONSE

    prompt = (
        "Você é um assistente financeiro inteligente.\n"
        "Analise os dados abaixo e gere:\n\n"
        "- Um insight estratégico\n"
        "- Um alerta (se houver risco)\n"
        "- Uma recomendação prática\n\n"
        "Responda em JSON no formato:\n"
        '{"insight": "...", "alerta": "...", "recomendacao": "..."}\n\n'
        "Dados:\n"
        f"{dados_json}"
    )

    try:
        print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        content = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Erro ao chamar OpenAI em gerar_insights_financeiros: %s", e)
        return FALLBACK_RESPONSE

    # Garantir que a resposta seja parseada como JSON
    try:
        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1] if len(parts) > 1 else content
            if content.strip().startswith("json"):
                content = content.strip()[4:].strip()
        parsed = json.loads(content)
        return {
            "insight": parsed.get("insight", ""),
            "alerta": parsed.get("alerta", ""),
            "recomendacao": parsed.get("recomendacao", ""),
        }
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Resposta da OpenAI não é JSON válido em gerar_insights_financeiros: %s", e)
        return FALLBACK_RESPONSE
