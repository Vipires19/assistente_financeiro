"""
Serviço de insights financeiros gerados por IA.

Localização: finance/services/ai_insights.py

Modelo híbrido: o backend calcula padrões financeiros e a IA apenas interpreta.
Gera diagnóstico, impacto, projeção e recomendação a partir de dados consolidados.
"""
import os
import json
import logging
from collections import defaultdict
from openai import OpenAI

logger = logging.getLogger(__name__)

# OPENAI_API_KEY deve estar no .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Fallback seguro quando a API falha ou a resposta não é JSON válido (novo formato)
FALLBACK_RESPONSE = {
    "diagnostico": "Não foi possível gerar a análise no momento. Tente novamente mais tarde.",
    "impacto": "",
    "projecao": "",
    "recomendacao": "Verifique sua conexão e a configuração da OPENAI_API_KEY.",
}


def _calcular_taxa_economia(dados: dict) -> float:
    """Calcula taxa de economia: (total_income - total_expenses) / total_income. Retorna 0 se total_income = 0."""
    total_income = float(dados.get("total_income") or 0)
    total_expenses = float(dados.get("total_expenses") or 0)
    if total_income == 0:
        return 0.0
    return round((total_income - total_expenses) / total_income, 4)


def _calcular_percentual_categoria(dados: dict) -> tuple:
    """
    Se existir category_with_highest_expense, calcula percentual_categoria = categoria_total / total_expenses.
    Proteção: se total_expenses == 0, percentual_categoria = 0.
    Retorna (categoria_dominante, percentual_categoria) ou (None, None).
    """
    cat_info = dados.get("category_with_highest_expense")
    if not cat_info or not isinstance(cat_info, dict):
        return None, None
    total_expenses = float(dados.get("total_expenses") or 0)
    if total_expenses == 0:
        return cat_info.get("category"), 0.0
    categoria_total = float(cat_info.get("total") or 0)
    percentual = round(categoria_total / total_expenses, 4)
    return cat_info.get("category"), percentual


def _calcular_conta_mais_usada(dados: dict) -> tuple:
    """
    Agrupa despesas por account_id, identifica a conta com maior valor.
    Mapeia para nome usando accounts; se account_id não existir na lista, usa "Conta não identificada".
    Retorna (conta_mais_usada_nome, percentual_conta) ou (None, None).
    """
    transactions = dados.get("transactions") or []
    if not transactions or not isinstance(transactions, list):
        return None, None
    total_expenses = float(dados.get("total_expenses") or 0)
    if total_expenses == 0:
        return None, None

    # Agrupar gastos por account_id (apenas type expense)
    por_conta = defaultdict(float)
    for t in transactions:
        if t.get("type") != "expense":
            continue
        value = t.get("value") or 0
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        acc_id = t.get("account_id")
        key = acc_id if acc_id is not None else "__sem_conta__"
        por_conta[key] += value

    if not por_conta:
        return None, None

    conta_mais_usada_key = max(por_conta, key=por_conta.get)
    total_conta = por_conta[conta_mais_usada_key]
    # Proteção divisão por zero: se total_expenses for 0 (não deveria chegar aqui), percentual = 0
    percentual = round(total_conta / total_expenses, 4) if total_expenses else 0.0

    if conta_mais_usada_key == "__sem_conta__":
        return "Sem conta informada", percentual

    # Mapear para nome usando accounts; se não existir na lista, usar "Conta não identificada"
    conta_mais_usada = "Conta não identificada"
    accounts = dados.get("accounts") or []
    for acc in accounts:
        aid = acc.get("id") or acc.get("_id")
        if str(aid) == str(conta_mais_usada_key):
            conta_mais_usada = acc.get("name") or acc.get("nome") or "Conta não identificada"
            break
    return conta_mais_usada, percentual


def _enriquecer_dados(dados: dict) -> dict:
    """
    Enriquece o objeto dados com os padrões calculados no backend:
    taxa_economia_percent, categoria_dominante, percentual_categoria, conta_mais_usada, percentual_conta.
    Não altera o dict original; retorna uma cópia com as chaves adicionais.
    """
    enriquecido = dict(dados)

    # ALTERAÇÃO 1: Taxa de economia
    enriquecido["taxa_economia_percent"] = _calcular_taxa_economia(dados)

    # ALTERAÇÃO 2: Percentual da categoria dominante
    cat_dom, pct_cat = _calcular_percentual_categoria(dados)
    enriquecido["categoria_dominante"] = cat_dom
    enriquecido["percentual_categoria"] = pct_cat

    # ALTERAÇÃO 3: Conta mais usada
    conta, pct_conta = _calcular_conta_mais_usada(dados)
    enriquecido["conta_mais_usada"] = conta
    enriquecido["percentual_conta"] = pct_conta

    return enriquecido


def _construir_resumo_financeiro(dados_enriquecidos: dict) -> dict:
    """
    Monta objeto resumo_financeiro com apenas os campos necessários para o prompt da IA.
    Reduz volume de dados e custo de tokens. Valores inexistentes como null ou 0 conforme apropriado.
    """
    total_income = dados_enriquecidos.get("total_income")
    total_expenses = dados_enriquecidos.get("total_expenses")
    balance = dados_enriquecidos.get("balance")
    return {
        "total_income": total_income if total_income is not None else 0,
        "total_expenses": total_expenses if total_expenses is not None else 0,
        "balance": balance if balance is not None else 0,
        "taxa_economia_percent": dados_enriquecidos.get("taxa_economia_percent"),
        "categoria_dominante": dados_enriquecidos.get("categoria_dominante"),
        "percentual_categoria": dados_enriquecidos.get("percentual_categoria"),
        "conta_mais_usada": dados_enriquecidos.get("conta_mais_usada"),
        "percentual_conta": dados_enriquecidos.get("percentual_conta"),
    }


def gerar_insights_financeiros(dados: dict) -> dict:
    """
    Gera diagnóstico, impacto, projeção e recomendação a partir de dados financeiros.

    O backend calcula os padrões (taxa de economia, categoria dominante, conta mais usada);
    a IA apenas interpreta e redige os campos em linguagem simples.

    Args:
        dados: Dicionário com dados consolidados (ex.: total_income, total_expenses,
               balance, category_with_highest_expense, transactions com account_id, etc.).

    Returns:
        Dict com chaves: "diagnostico", "impacto", "projecao", "recomendacao".
        Em caso de erro, retorna fallback seguro (mesmo formato).
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY não configurada em ai_insights.")
        return {
            "diagnostico": "Configure OPENAI_API_KEY no .env para receber análises automáticas.",
            "impacto": "",
            "projecao": "",
            "recomendacao": "Adicione OPENAI_API_KEY nas variáveis de ambiente.",
        }

    # Enriquece dados com padrões calculados no backend
    dados = _enriquecer_dados(dados)

    # Enviar apenas resumo_financeiro para a IA (reduz tokens e custo)
    try:
        resumo_financeiro = _construir_resumo_financeiro(dados)
        resumo_json = json.dumps(resumo_financeiro, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as e:
        logger.warning("Dados não serializáveis para JSON em gerar_insights_financeiros: %s", e)
        return FALLBACK_RESPONSE

    prompt = (
        "Você é um analista financeiro que explica padrões de gastos.\n\n"
        "Analise os dados resumidos abaixo e gere uma análise clara.\n\n"
        "Responda em JSON no formato:\n"
        '{"diagnostico": "...", "impacto": "...", "projecao": "...", "recomendacao": "..."}\n\n'
        "Regras:\n"
        "- explicar para onde o dinheiro está indo\n"
        "- mencionar categoria dominante\n"
        "- mencionar conta mais usada\n"
        "- mencionar taxa de economia\n"
        "- linguagem simples\n"
        "- máximo 2 frases por campo\n\n"
        "Dados financeiros:\n\n"
        f"{resumo_json}"
    )

    try:
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

    # Parsing JSON robusto (ALTERAÇÃO 6: manter fallback seguro)
    try:
        if content.startswith("```"):
            parts = content.split("```")
            content = parts[1] if len(parts) > 1 else content
            if content.strip().startswith("json"):
                content = content.strip()[4:].strip()
        parsed = json.loads(content)
        return {
            "diagnostico": parsed.get("diagnostico", ""),
            "impacto": parsed.get("impacto", ""),
            "projecao": parsed.get("projecao", ""),
            "recomendacao": parsed.get("recomendacao", ""),
        }
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Resposta da OpenAI não é JSON válido em gerar_insights_financeiros: %s", e)
        return FALLBACK_RESPONSE
