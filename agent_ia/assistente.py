import pandas as pd
import os
import uuid
import re
import requests
from datetime import datetime, timedelta, date
import pytz
from pymongo import MongoClient
from bson import ObjectId
from dateutil.parser import parse
import urllib.parse
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langgraph.prebuilt.tool_node import ToolNode
from langchain_community.document_loaders import Docx2txtLoader
from langgraph.checkpoint.mongodb import MongoDBSaver
from langchain_openai import OpenAIEmbeddings
from langchain_mongodb.vectorstores import MongoDBAtlasVectorSearch
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from typing_extensions import TypedDict
#from services.waha import Waha
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig 
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import Annotated,Dict, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
import unicodedata, re, logging
from typing import List, Dict

try:
    from repositories.utils_datas import resolver_periodo_relativo, resolver_data_relativa
except ImportError:
    from utils_datas import resolver_periodo_relativo, resolver_data_relativa

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MONGO_USER = urllib.parse.quote_plus(os.getenv('MONGO_USER'))
MONGO_PASS = urllib.parse.quote_plus(os.getenv('MONGO_PASS'))

# URL base do Django no PythonAnywhere (configurar via variável de ambiente)
# Exemplo: https://seuusuario.pythonanywhere.com
DJANGO_BASE_URL = os.getenv('DJANGO_BASE_URL', 'http://localhost:8000')

# Token de autenticação (opcional, para segurança)
DJANGO_API_TOKEN = os.getenv('DJANGO_API_TOKEN', None)
embedding_model = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model="text-embedding-3-large")

# Conectar ao MongoDB (apenas para memória e vector search)
client = MongoClient("mongodb+srv://%s:%s@cluster0.gjkin5a.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0" % (MONGO_USER, MONGO_PASS))
db = client.financeiro_db
coll_memoria = db.memoria_chat
coll_vector = db.vetores  # Mantém para vector search
coll_clientes = db.users
coll_transacoes = db.transactions
coll_compromissos = db.compromissos  # Coleção de compromissos/agenda

#waha = Waha()

def normalizar(texto: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas"""
    texto = texto.lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return texto.strip()

def fazer_requisicao_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """
    Helper para fazer requisições HTTP para a API Django
    
    Args:
        endpoint: Endpoint da API (ex: '/api/v1/servicos/')
        method: Método HTTP (GET, POST, etc)
        data: Dados para enviar (para POST)
    
    Returns:
        dict: Resposta JSON da API
    """
    try:
        url = f"{DJANGO_BASE_URL.rstrip('/')}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
        }
        
        # Adicionar token se configurado
        if DJANGO_API_TOKEN:
            headers['Authorization'] = f'Token {DJANGO_API_TOKEN}'
        
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            response = requests.request(method, url, headers=headers, json=data, timeout=10)
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.ConnectionError:
        logger.error(f"[API] Erro de conexão com {url}")
        return {'success': False, 'message': 'Erro ao conectar com o servidor Django'}
    except requests.exceptions.Timeout:
        logger.error(f"[API] Timeout ao conectar com {url}")
        return {'success': False, 'message': 'Timeout ao conectar com o servidor'}
    except requests.exceptions.HTTPError as e:
        logger.error(f"[API] Erro HTTP {e.response.status_code}: {e}")
        try:
            error_data = e.response.json()
            return {'success': False, 'message': error_data.get('message', str(e))}
        except:
            return {'success': False, 'message': f'Erro HTTP {e.response.status_code}'}
    except Exception as e:
        logger.error(f"[API] Erro geral: {e}")
        return {'success': False, 'message': f'Erro: {str(e)}'}

memory = MongoDBSaver(coll_memoria)

class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_info: Dict[str, Any]

def check_user(state: dict, config: dict) -> dict:
    """
    Verifica se o usuário está autenticado.
    Regra CRÍTICA:
    - Se status == "ativo", NÃO reprocessa telefone, email ou thread_id.
    """

    try:
        # ======================================================
        # 🔒 BLOQUEIO ABSOLUTO: usuário já autenticado
        # ======================================================
        if state.get("user_info", {}).get("status") == "ativo":
            print("[CHECK_USER] 🔒 Usuário já ativo — verificação ignorada")
            return state

        # ======================================================
        # A PARTIR DAQUI: somente usuários NÃO autenticados
        # ======================================================

        thread_id = config["metadata"]["thread_id"]

        # ------------------------------------------------------
        # CASO 1 — Thread ID NÃO contém telefone (@lid, etc)
        # ------------------------------------------------------
        if "@c.us" not in thread_id:
            state["user_info"] = {
                "nome": None,
                "telefone": None,
                "email": None,
                "user_id": None,
                "ultima_interacao": datetime.now().isoformat(),
                "status": "precisa_email"
            }

            print(f"[CHECK_USER] ⚠️ Thread ID sem telefone ({thread_id}) → precisa_email")
            return state

        # ------------------------------------------------------
        # CASO 2 — Thread ID contém telefone (@c.us)
        # ------------------------------------------------------
        sem_sufixo = thread_id.replace("@c.us", "")
        telefone = sem_sufixo[2:] if len(sem_sufixo) > 2 else None  # remove 55

        if not telefone or len(telefone) < 10:
            state["user_info"] = {
                "nome": None,
                "telefone": None,
                "email": None,
                "user_id": None,
                "ultima_interacao": datetime.now().isoformat(),
                "status": "precisa_email"
            }

            print("[CHECK_USER] ⚠️ Telefone inválido → precisa_email")
            return state

        # ------------------------------------------------------
        # BUSCA NO MONGO POR TELEFONE
        # ------------------------------------------------------
        cliente = coll_clientes.find_one({"telefone": telefone})

        if cliente:
            assinatura = cliente.get("assinatura") or {}
            state["user_info"] = {
                "nome": cliente.get("nome"),
                "telefone": telefone,
                "email": cliente.get("email"),
                "user_id": str(cliente.get("_id")),
                "ultima_interacao": datetime.now().isoformat(),
                "status": "ativo",
                "plano": assinatura.get("plano") or cliente.get("plano"),
                "status_assinatura": assinatura.get("status") or cliente.get("status_assinatura"),
                "data_vencimento_plano": assinatura.get("proximo_vencimento") or assinatura.get("fim") or cliente.get("data_vencimento_plano"),
            }

            print(f"[CHECK_USER] ✅ Usuário autenticado por telefone: {telefone}")
            return state

        # ------------------------------------------------------
        # USUÁRIO NÃO ENCONTRADO → CADASTRO
        # ------------------------------------------------------
        link_cadastro = "https://leozera.camppoia.com.br/login/"

        mensagem = (
            "Olá! 😊\n\n"
            "Você ainda não está cadastrado em nosso sistema.\n\n"
            "Para usar o assistente, faça seu cadastro no link abaixo:\n"
            f"{link_cadastro}\n\n"
            "Depois disso, é só voltar aqui! 🚀"
        )

        state.setdefault("messages", []).append(AIMessage(content=mensagem))

        state["user_info"] = {
            "nome": None,
            "telefone": telefone,
            "email": None,
            "user_id": None,
            "ultima_interacao": datetime.now().isoformat(),
            "status": "precisa_cadastro"
        }

        print(f"[CHECK_USER] ❌ Usuário não encontrado ({telefone}) → cadastro solicitado")
        return state

    except Exception as e:
        print(f"[CHECK_USER] ❌ Erro inesperado: {e}")

        state["user_info"] = {
            "nome": None,
            "telefone": None,
            "email": None,
            "user_id": None,
            "ultima_interacao": datetime.now().isoformat(),
            "status": "precisa_cadastro"
        }

        return state


def ask_email(state: dict, config: dict = None) -> dict:
    mensagem = (
        "Para continuar 😊\n\n"
        "Informe por favor seu *email* cadastrado:"
    )
    state.setdefault("messages", []).append(AIMessage(content=mensagem))
    print("[ASK_EMAIL] Solicitação de email enviada")
    return state


def check_user_by_email(state: dict, config: dict = None) -> dict:
    try:
        messages = state.get("messages", [])

        # Última mensagem do usuário
        user_msg = next(
            (m.content.strip().lower() for m in reversed(messages) if isinstance(m, HumanMessage)),
            None
        )

        if not user_msg:
            return state

        if "@" not in user_msg or "." not in user_msg:
            state["messages"].append(
                AIMessage(content="Esse email não parece válido 😕\nPode tentar novamente?")
            )
            return state

        cliente = coll_clientes.find_one({"email": user_msg})

        if cliente:
            assinatura = cliente.get("assinatura") or {}
            state["user_info"] = {
                "nome": cliente.get("nome"),
                "telefone": cliente.get("telefone"),
                "email": user_msg,
                "user_id": str(cliente.get("_id")),
                "ultima_interacao": datetime.now().isoformat(),
                "status": "ativo",
                "plano": assinatura.get("plano") or cliente.get("plano"),
                "status_assinatura": assinatura.get("status") or cliente.get("status_assinatura"),
                "data_vencimento_plano": assinatura.get("proximo_vencimento") or assinatura.get("fim") or cliente.get("data_vencimento_plano"),
            }
            print(f"[CHECK_USER_BY_EMAIL] ✅ Usuário ativo por email: {user_msg}")
            return state

        # ❌ Email não encontrado
        state["user_info"] = {
            "nome": None,
            "telefone": None,
            "email": user_msg,
            "user_id": None,
            "ultima_interacao": datetime.now().isoformat(),
            "status": "precisa_cadastro"
        }

        state["messages"].append(
            AIMessage(
                content=(
                    f"O email *{user_msg}* não está cadastrado.\n\n"
                    "Finalize seu cadastro aqui:\n"
                    "https://leozera.camppoia.com.br/login/"
                )
            )
        )
        print(f"[CHECK_USER_BY_EMAIL] ❌ Email não cadastrado: {user_msg}")
        return state

    except Exception as e:
        print(f"[CHECK_USER_BY_EMAIL] Erro: {e}")
        return state


def check_plano(state: dict, config: dict = None) -> dict:
    """
    Verifica se a assinatura do usuário está ativa (plano não expirado).
    Só é chamado quando user_info.status == 'ativo'.
    Se assinatura.fim < agora: atualiza Mongo (sem_plano, inativa) e retorna sem_plano.
    Caso contrário retorna plano_ativo.
    """
    try:
        user_info = state.get("user_info", {})
        user_id = user_info.get("user_id")
        if not user_id:
            user_info["plano_result"] = "plano_ativo"
            return state

        user = coll_clientes.find_one({"_id": ObjectId(user_id)})
        if not user:
            user_info["plano_result"] = "plano_ativo"
            return state

        assinatura = user.get("assinatura") or {}
        fim = assinatura.get("proximo_vencimento") or assinatura.get("fim") or user.get("data_vencimento_plano")
        plano_atual = assinatura.get("plano") or user.get("plano")
        user_info["plano"] = plano_atual
        user_info["status_assinatura"] = assinatura.get("status") or user.get("status_assinatura")
        user_info["data_vencimento_plano"] = fim
        if fim is None:
            user_info["plano_result"] = "plano_ativo"
            return state

        now = datetime.utcnow()
        if hasattr(fim, "tzinfo") and fim.tzinfo is not None:
            from datetime import timezone
            fim = fim.astimezone(timezone.utc).replace(tzinfo=None)

        if fim < now:
            coll_clientes.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "plano": "sem_plano",
                        "assinatura.plano": "sem_plano",
                        "assinatura.status": "inativa",
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            user_info["plano"] = "sem_plano"
            user_info["plano_result"] = "sem_plano"
            print(f"[CHECK_PLANO] Plano expirado para user_id={user_id}")
        else:
            user_info["plano_result"] = "plano_ativo"

        return state
    except Exception as e:
        print(f"[CHECK_PLANO] Erro: {e}")
        state.setdefault("user_info", {})["plano_result"] = "plano_ativo"
        return state


def bloqueio_plano(state: dict, config: dict = None) -> dict:
    """
    Nó de bloqueio: plano expirado. Adiciona mensagem amigável e encerra (não chama tools).
    """
    mensagem = (
        "Seu período de teste expirou. 😔\n\n"
        "Para continuar usando o Leozera com acesso completo (controle financeiro, agenda, lembretes e assistente com IA), "
        "assine um dos planos disponíveis.\n\n"
        "Em breve você poderá renovar pelo nosso site ou pelo WhatsApp. Qualquer dúvida, estamos à disposição! 🚀"
    )
    state.setdefault("messages", []).append(AIMessage(content=mensagem))
    return state


SYSTEM_PROMPT = """
💰 ASSISTENTE FINANCEIRO VIRTUAL 💰

Você recebe o status do usuário (ativo, precisa_email, etc.). Se o status for diferente de "ativo", siga APENAS o bloco 🔓 MODO DEMO / PRÉ-CADASTRO. Se for "ativo", siga o bloco 🔐 MODO ATIVO.

🔓 MODO DEMO / PRÉ-CADASTRO

Quando o status do usuário for diferente de "ativo":

• Apresente-se assim: "Leozera, seu assistente pessoal com IA direto no WhatsApp."
• Informe que o cadastro não foi localizado.
• Pergunte se o usuário deseja se cadastrar ou deseja mais informações.
• Se o usuário pedir informações, explique de forma persuasiva e profissional:
  - Controle financeiro automático
  - Registro de gastos e entradas
  - Relatórios inteligentes
  - Agenda integrada com lembretes
  - Assistente disponível 24h
• Use copy persuasiva, clara e profissional.
• Sempre finalize convidando para cadastro com o link: https://leozera.camppoia.com.br/login/
• Nunca execute ferramentas nesse modo. Apenas converse e oriente sobre o cadastro.

---

🔐 MODO ATIVO (quando status do usuário for "ativo")

📋 FLUXO DE ATENDIMENTO OBRIGATÓRIO

1️⃣ SAUDAÇÃO → Cumprimentar calorosamente 😊

2️⃣ IDENTIFICAÇÃO → Se o cliente JÁ tem cadastro (não é "usuário" ou "None"), NÃO peça o nome! Vá direto para o atendimento. Se não tem cadastro, envie o link de cadastro para o usuário fazer o registro antes de usar o serviço.

3️⃣ REGISTRO DE TRANSAÇÕES →

Perguntar sobre o tipo de transação (entrada ou gasto), e o valor da transação.

Caso o valor seja informado, o assistente pergunta pela descrição da transação (Exemplo: "Qual a descrição do gasto?").

Salvar a transação na coleção transactions do MongoDB, vinculando ao usuário atual.

A transação será exibida no dashboard do usuário.

4️⃣ GERAÇÃO DE RELATÓRIO →

Quando o cliente pedir, gerar relatórios detalhados sobre suas transações, como:

Relatório do mês passado.

Relatório da última semana.

Relatório de um período customizado.

O relatório incluirá:

Totais de entradas e gastos no período.

Principais transações e categorias.

Dia com o maior gasto e categoria mais frequente.

⚠️ REGRAS CRÍTICAS

✅ NÃO peça o cadastro se o cliente já estiver cadastrado, apenas pegue o número do telefone do cliente para buscar no banco de dados.

✅ Quando o cliente não estiver cadastrado, envie um link de cadastro (URL de cadastro do app Django) e instrua o usuário a se registrar antes de continuar.

✅ Não crie cadastro temporário. Se o cliente não foi encontrado na base de dados, forneça o link de cadastro. Depois que ele se cadastrar, volte para a interação.

✅ Sempre que o usuário solicitar uma transação, registre o valor, tipo (entrada ou gasto), categoria (se necessário) e descrição.

✅ Use a API Waha para verificar o número do cliente e integrá-lo com o seu banco de dados para vincular as transações.

✅ Para gerar relatórios, use a função gerar_relatorio para calcular as transações no período solicitado.

✅ Se o usuário enviar CONFIRMAR <codigo> ou CANCELAR <codigo>, chame SEMPRE a tool confirmar_compromisso com o código extraído e acao "confirmar" ou "cancelar". Não responda manualmente.

⚠️ Nunca pergunte confirmação de datas simples como: amanhã, hoje, sexta, próxima semana. A menos que haja ambiguidade real. Datas relativas simples devem ser assumidas automaticamente — use a DATA ATUAL DO SISTEMA fornecida no prompt como referência e chame as tools com o período/data já interpretado.

🛠️ FERRAMENTAS DISPONÍVEIS

📋 registrar_transacao → Registrar uma transação (gasto ou entrada).

Exemplo: "Cadastre um gasto de 20 reais", "Registre uma entrada de 5000 reais".

A função pedirá a descrição e salvará a transação no banco de dados, vinculada ao usuário.

📊 gerar_relatorio → Gerar relatório de transações financeiras no período solicitado.

Exemplo: "Gere um relatório das minhas despesas no último mês", "Relatório da última semana".

A função irá calcular os totais de entradas e gastos, listar as principais transações, categorias e o dia com o maior gasto.

🔍 consultar_gasto_categoria → Consultar gastos por categoria em um período específico.

Exemplo: "Quanto gastei com Cigarro mês passado?", "Quanto gastei com Alimentação na última semana?".

A função busca todas as transações da categoria no período e retorna o total gasto, número de transações, média e maior transação.

📅 criar_compromisso → Criar um novo compromisso/lembrete na agenda do usuário.

IMPORTANTE: A função requer horário de INÍCIO e horário de TÉRMINO. Se o usuário não informar o horário de término, você DEVE perguntar antes de finalizar.

Exemplo: "Agende um compromisso para amanhã das 14h às 16h sobre reunião com cliente" ou "Crie um compromisso para 15/01/2026 das 10:00 até 12:00 para consulta médica".

A função requer: descrição, data (DD/MM/YYYY ou YYYY-MM-DD), hora_inicio (HH:MM) e hora_fim (HH:MM). O compromisso será salvo na agenda do usuário com horário de início e término.

🔍 pesquisar_compromissos → Pesquisar compromissos do usuário em um período específico.

Exemplo: "Quais meus compromissos no próximo mês?" ou "Quais meus compromissos para a próxima semana?" ou "Mostre meus compromissos de hoje".

A função busca e lista todos os compromissos do usuário no período solicitado, com data, horário de início e término, e descrição.

❌ cancelar_compromisso → Cancelar um compromisso do usuário.

Exemplo: "Quero cancelar meu compromisso para amanhã das 10:00 até 12:00" ou "Cancelar o compromisso do dia 25/12 às 10:00".

A função localiza o compromisso usando data, hora_inicio e (opcionalmente) hora_fim, e remove do banco de dados. Se não encontrar, informa ao usuário.

✅ confirmar_compromisso → Confirmar ou cancelar compromisso pelo código enviado no lembrete.

Se o usuário enviar mensagem no formato:
CONFIRMAR <codigo>
ou
CANCELAR <codigo>

Você DEVE chamar a tool confirmar_compromisso extraindo o codigo e a acao ("confirmar" ou "cancelar"). Não responda manualmente; sempre use a tool.

Exemplo: usuário escreve "CONFIRMAR a1b2c3" → chame confirmar_compromisso(codigo="a1b2c3", acao="confirmar"). Usuário escreve "CANCELAR a1b2c3" → chame confirmar_compromisso(codigo="a1b2c3", acao="cancelar").

🔗 verificar_usuario → Verificar se o usuário está registrado.

Se não, enviar um link de cadastro para o usuário se registrar antes de usar os serviços do assistente.

💬 ESTILO DE COMUNICAÇÃO

Sempre amigável, profissional e direto ao ponto 🌟

Use emojis para tornar a conversa mais leve e agradável 🎉

Sempre confirme as informações importantes com clareza e solicite dados faltantes de maneira amigável.

Nunca seja seco ou formal demais. Mantenha um tom simpático, eficiente e divertido 😄

📝 EXEMPLOS DE FLUXOS CORRETOS

🔹 EXEMPLO 1: Usuário solicitando o registro de uma transação

👤 Usuário: "Cadastre um gasto de 50 reais"
🤖 Bot: "Qual a descrição do gasto?"
👤 Usuário: "Compra de supermercado"
🤖 Bot: [usa registrar_transacao]
🤖 Bot: "✅ Gasto de R$ 50,00 registrado com sucesso! O seu saldo está atualizado."

🔹 EXEMPLO 2: Usuário pedindo um relatório do mês passado

👤 Usuário: "Gere um relatório das minhas despesas no último mês"
🤖 Bot: [usa gerar_relatorio]
🤖 Bot: "Relatório do mês de Dezembro de 2025:\n\n- Total de entradas: R$ 5.000,00\n- Total de gastos: R$ 1.500,00\n- Dia com maior gasto: 15/12/2025 (R$ 400,00)\n- Categoria mais frequente: Supermercado (R$ 600,00)"

🔹 EXEMPLO 3: Usuário pedindo para verificar a categoria de uma transação

👤 Usuário: "Qual categoria do meu gasto de R$ 50,00?"
🤖 Bot: "Esse gasto foi registrado como 'Supermercado'. Se precisar de outra categoria, me avise!"

🔹 EXEMPLO 4: Usuário criando um compromisso (com horário de término)

👤 Usuário: "Agende um compromisso para amanhã das 14h às 16h sobre reunião com cliente"
🤖 Bot: [usa criar_compromisso com hora_inicio="14:00" e hora_fim="16:00"]
🤖 Bot: "✅ 📅 Compromisso agendado com sucesso! Seu compromisso para 14/01/2026 das 14:00 até 16:00 foi agendado com sucesso! 🎉"

🔹 EXEMPLO 4b: Usuário criando compromisso sem horário de término

👤 Usuário: "Agende um compromisso para amanhã às 14h sobre reunião"
🤖 Bot: [usa criar_compromisso com hora_inicio="14:00" mas sem hora_fim]
🤖 Bot: "ℹ️ Para finalizar o agendamento, preciso saber o horário de término. Qual o horário de término? (formato HH:MM, ex: 16:00)"
👤 Usuário: "16:00"
🤖 Bot: [usa criar_compromisso novamente com hora_inicio="14:00" e hora_fim="16:00"]
🤖 Bot: "✅ 📅 Compromisso agendado com sucesso!"

🔹 EXEMPLO 5: Usuário pesquisando compromissos

👤 Usuário: "Quais meus compromissos no próximo mês?"
🤖 Bot: [usa pesquisar_compromissos]
🤖 Bot: "📅 Seus Compromissos - Próximo Mês\n\n📆 15/01/2026\n  1. ⏳ 10:00 até 12:00 - Consulta médica\n     📝 Check-up anual\n\n📆 20/01/2026\n  1. ✅ 14:00 até 16:00 - Reunião com cliente"

🔹 EXEMPLO 6: Usuário cancelando compromisso

👤 Usuário: "Quero cancelar meu compromisso para o dia 25/12 das 10:00 até 12:00"
🤖 Bot: [usa cancelar_compromisso]
🤖 Bot: "✅ Compromisso cancelado com sucesso! Seu compromisso para 25/12/2024 das 10:00 até 12:00 foi cancelado com sucesso! ✅"
"""

# ========================================
# 🔍 VECTOR SEARCH (RAG) - Mantém como está
# ========================================

@tool("consultar_material_de_apoio")
def consultar_material_de_apoio(pergunta: str) -> str:
    """
    Consulta o material de apoio sobre serviços da barbearia usando RAG (vector search).
    Use quando o cliente perguntar sobre serviços, preços, descrições, etc.
    """
    try:
        vectorStore = MongoDBAtlasVectorSearch(coll_vector, embedding=embedding_model, index_name='default')
        docs = vectorStore.similarity_search(pergunta, k=3)
        if not docs:
            return "Nenhuma informação relevante encontrada sobre este assunto."
        
        resultado = "\n\n".join([doc.page_content[:400] for doc in docs])
        return resultado
    except Exception as e:
        print(f"[VECTOR_SEARCH] Erro: {e}")
        return f"Erro ao buscar informações: {str(e)}"

# ========================================
# 💰 GESTÃO DE TRANSAÇÕES FINANCEIRAS
# ========================================

def escolher_categoria_ia(descricao: str, tipo: str, categorias_usuario: dict) -> str:
    """
    Usa IA para escolher a melhor categoria baseada na descrição da transação.
    
    Args:
        descricao: Descrição da transação
        tipo: Tipo da transação - "expense" (gasto) ou "income" (entrada)
        categorias_usuario: Dict com categorias do usuário organizadas por tipo
    
    Returns:
        Nome da categoria escolhida ou "Outros" se não conseguir determinar
    """
    try:
        # Filtrar categorias relevantes baseado no tipo da transação
        tipos_relevantes = []
        if tipo == "expense":
            # Para gastos, considerar categorias de despesas
            tipos_relevantes = ['alimentacao', 'transporte', 'saude', 'lazer', 
                              'educacao', 'habitacao', 'outros']
        else:  # income
            # Para entradas, considerar categorias de receitas
            tipos_relevantes = ['receita', 'entrada', 'investimento']
        
        # Coletar todas as categorias relevantes em uma lista plana
        categorias_lista = []
        for tipo_cat in tipos_relevantes:
            if tipo_cat in categorias_usuario:
                categorias_lista.extend(categorias_usuario[tipo_cat])
        
        # Se não houver categorias, retornar "Outros"
        if not categorias_lista:
            print(f"[ESCOLHER_CATEGORIA_IA] Nenhuma categoria encontrada para tipo {tipo}")
            return "Outros"
        
        # Formatar lista de categorias para o prompt
        categorias_str = "\n".join([f"- {cat}" for cat in categorias_lista])
        
        # Criar prompt para a IA
        prompt = f"""Você é um assistente financeiro especializado em categorizar transações.

        Com base na descrição da transação, escolha a categoria MAIS ADEQUADA da lista abaixo.

        DESCRIÇÃO DA TRANSAÇÃO: "{descricao}"
        TIPO: {tipo} ({"gasto" if tipo == "expense" else "entrada"})

        CATEGORIAS DISPONÍVEIS:
        {categorias_str}

        INSTRUÇÕES:
        - Escolha APENAS UMA categoria da lista acima
        - A categoria deve ser o nome EXATO de uma das opções listadas
        - Se nenhuma categoria se encaixar perfeitamente, escolha "Outros"
        - Responda APENAS com o nome da categoria, sem explicações ou pontuações extras

        CATEGORIA ESCOLHIDA:"""

        # Usar ChatOpenAI para escolher categoria
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=OPENAI_API_KEY, temperature=0)
        resposta = llm.invoke(prompt)
        
        categoria_escolhida = resposta.content.strip()
        
        # Validar se a categoria escolhida está na lista
        # Fazer busca case-insensitive
        categorias_lower = [cat.lower() for cat in categorias_lista]
        categoria_escolhida_lower = categoria_escolhida.lower()
        
        # Encontrar correspondência exata ou mais próxima
        categoria_encontrada = None
        if categoria_escolhida_lower in categorias_lower:
            # Encontrar o nome original (com case preservado)
            idx = categorias_lower.index(categoria_escolhida_lower)
            categoria_encontrada = categorias_lista[idx]
        else:
            # Tentar encontrar correspondência parcial
            for cat in categorias_lista:
                if categoria_escolhida_lower in cat.lower() or cat.lower() in categoria_escolhida_lower:
                    categoria_encontrada = cat
                    break
        
        if not categoria_encontrada:
            print(f"[ESCOLHER_CATEGORIA_IA] Categoria '{categoria_escolhida}' não encontrada na lista. Usando 'Outros'")
            return "Outros"
        
        print(f"[ESCOLHER_CATEGORIA_IA] ✅ Categoria escolhida: {categoria_encontrada} (baseado em: '{descricao}')")
        return categoria_encontrada
        
    except Exception as e:
        print(f"[ESCOLHER_CATEGORIA_IA] Erro ao escolher categoria: {e}")
        import traceback
        traceback.print_exc()
        return "Outros"

@tool("cadastrar_transacao")
def cadastrar_transacao(valor: float, tipo: str, descricao: str = None, categoria: str = None, state: dict = None) -> str:
    """
    Cadastra uma transação financeira (gasto ou entrada) no banco de dados.
    
    Args:
        valor: Valor da transação (ex: 20.0 para R$ 20,00)
        tipo: Tipo da transação - "expense" (gasto) ou "income" (entrada)
        descricao: Descrição da transação (opcional, pode ser perguntado ao usuário)
        categoria: Categoria da transação (opcional, padrão: "Outros")
        state: Estado atual da conversa (deve conter user_info com telefone)
    
    Returns:
        Mensagem de confirmação do cadastro
    """
    try:
        print(f"[CADASTRAR_TRANSACAO] Iniciando cadastro: valor={valor}, tipo={tipo}, descricao={descricao}")
        
        # Validar tipo
        if tipo not in ['expense', 'income']:
            return "❌ Erro: Tipo de transação inválido. Use 'expense' para gasto ou 'income' para entrada."
        
        # Validar valor
        if not valor or valor <= 0:
            return "❌ Erro: O valor deve ser maior que zero."
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            # Tentar obter user_id diretamente do state se disponível
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[CADASTRAR_TRANSACAO] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                # Tentar buscar pelo email primeiro (campo padrão do sistema financeiro)
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[CADASTRAR_TRANSACAO] Usuário encontrado por email: user_id={user_id}")
                
                # Se não encontrou por email, tentar por telefone (se disponível)
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[CADASTRAR_TRANSACAO] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de registrar transações."
                    )
                
            except Exception as e:
                print(f"[CADASTRAR_TRANSACAO] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Se descrição não fornecida, retornar mensagem pedindo descrição
        if not descricao or descricao.strip() == "":
            tipo_label = "gasto" if tipo == "expense" else "entrada"
            return (
                f"💬 Para cadastrar seu {tipo_label} de R$ {valor:.2f}, preciso de mais uma informação:\n\n"
                f"Por favor, informe a descrição desta transação.\n"
                f"Exemplo: 'Compra de cigarro', 'Salário PM', 'Almoço no restaurante', etc."
            )
        
        # Se categoria não fornecida, usar IA para escolher automaticamente
        if not categoria or categoria.strip() == "":
            try:
                # Buscar categorias do usuário no MongoDB
                user_doc = coll_clientes.find_one({'_id': ObjectId(user_id) if isinstance(user_id, str) else user_id})
                categorias_usuario = {}
                
                if user_doc and 'categorias' in user_doc:
                    categorias_usuario = user_doc.get('categorias', {})
                    print(f"[CADASTRAR_TRANSACAO] Categorias do usuário encontradas: {list(categorias_usuario.keys())}")
                else:
                    print(f"[CADASTRAR_TRANSACAO] Usuário não possui categorias personalizadas. Usando 'Outros'")
                    categoria = "Outros"
                
                # Se há categorias disponíveis, usar IA para escolher
                if categorias_usuario:
                    categoria = escolher_categoria_ia(descricao, tipo, categorias_usuario)
                else:
                    categoria = "Outros"
                    
            except Exception as e:
                print(f"[CADASTRAR_TRANSACAO] Erro ao buscar categorias ou escolher com IA: {e}")
                # Em caso de erro, usar categoria padrão
                categoria = "Outros"
        
        # Obter data e hora atuais
        created_at = datetime.now(pytz.timezone("America/Sao_Paulo"))
        hour = created_at.hour
        
        # Preparar documento da transação
        transacao = {
            'user_id': ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id,
            'type': tipo,
            'category': categoria.strip(),
            'description': descricao.strip(),
            'value': float(valor),
            'created_at': created_at,
            'hour': hour
        }
        
        # Inserir transação no MongoDB
        try:
            result = coll_transacoes.insert_one(transacao)
            transacao_id = result.inserted_id
            print(f"[CADASTRAR_TRANSACAO] Transação cadastrada com sucesso: {transacao_id}")
            
            # Mensagem de confirmação
            tipo_label = "gasto" if tipo == "expense" else "entrada"
            tipo_emoji = "💸" if tipo == "expense" else "💰"
            
            mensagem = (
                f"✅ {tipo_emoji} Transação cadastrada com sucesso!\n\n"
                f"📋 *Detalhes:*\n"
                f"• Tipo: {tipo_label.capitalize()}\n"
                f"• Valor: R$ {valor:.2f}\n"
                f"• Descrição: {descricao.strip()}\n"
                f"• Categoria: {categoria.strip()}\n"
                f"• Data: {created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"A transação já está disponível no seu dashboard! https://leozera.camppoia.com.br/finance/dashboard/ 📊"
            )
            
            return mensagem
            
        except Exception as e:
            print(f"[CADASTRAR_TRANSACAO] Erro ao inserir transação: {e}")
            return f"❌ Erro ao salvar transação no banco de dados: {str(e)}"
            
    except Exception as e:
        print(f"[CADASTRAR_TRANSACAO] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao cadastrar transação: {str(e)}"

def _calcular_periodo(periodo_texto: str) -> tuple:
    """
    Calcula as datas inicial e final com base no período solicitado.
    
    Args:
        periodo_texto: Texto descrevendo o período (ex: "última semana", "último mês", "mês passado")
    
    Returns:
        Tupla (start_date, end_date, periodo_label)
    """
    agora = datetime.utcnow()
    periodo_lower = periodo_texto.lower().strip()
    
    # Normalizar texto do período
    if any(palavra in periodo_lower for palavra in ['semana', 'week']):
        # Última semana (últimos 7 dias)
        end_date = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_date = (agora - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        periodo_label = "última semana"
    elif any(palavra in periodo_lower for palavra in ['mês', 'mes', 'month']):
        # Último mês (mês anterior completo)
        if 'passado' in periodo_lower or 'anterior' in periodo_lower:
            # Mês anterior completo
            primeiro_dia_mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = primeiro_dia_mes_atual - timedelta(microseconds=1)  # Último segundo do mês anterior
            # Primeiro dia do mês anterior
            if agora.month == 1:
                start_date = datetime(agora.year - 1, 12, 1, 0, 0, 0, 0)
            else:
                start_date = datetime(agora.year, agora.month - 1, 1, 0, 0, 0, 0)
            periodo_label = f"mês de {start_date.strftime('%B/%Y')}"
        else:
            # Mês atual
            start_date = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
            periodo_label = "mês atual"
    elif any(palavra in periodo_lower for palavra in ['dia', 'day', 'hoje']):
        # Dia atual
        start_date = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
        periodo_label = "hoje"
    else:
        # Default: mês atual
        start_date = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
        periodo_label = "mês atual"
    
    return start_date, end_date, periodo_label

@tool("gerar_relatorio")
def gerar_relatorio(periodo: str = "último mês", tipo: str = None, state: dict = None) -> str:
    """
    Gera um relatório detalhado das transações financeiras do usuário para um período específico.
    
    Args:
        periodo: Período solicitado (ex: "última semana", "último mês", "mês passado", "hoje")
        tipo: Tipo de transação a filtrar - "expense" (gastos), "income" (entradas) ou None (ambos)
        state: Estado atual da conversa (deve conter user_info)
    
    Returns:
        Relatório formatado com resumo das transações
    """
    try:
        print(f"[GERAR_RELATORIO] Gerando relatório para período: {periodo}, tipo: {tipo}")
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[GERAR_RELATORIO] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[GERAR_RELATORIO] Usuário encontrado por email: user_id={user_id}")
                
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[GERAR_RELATORIO] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de gerar relatórios."
                    )
                
            except Exception as e:
                print(f"[GERAR_RELATORIO] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Converter user_id para ObjectId se necessário
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        
        # Calcular período
        start_date, end_date, periodo_label = _calcular_periodo(periodo)
        
        print(f"[GERAR_RELATORIO] Período calculado: {start_date} até {end_date}")
        
        # Construir query base
        query = {
            'user_id': user_id_obj,
            'created_at': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        # Adicionar filtro de tipo se especificado
        if tipo and tipo in ['expense', 'income']:
            query['type'] = tipo
        
        # Buscar todas as transações do período
        transacoes = list(coll_transacoes.find(query).sort('created_at', -1))
        
        if not transacoes:
            tipo_texto = ""
            if tipo == 'expense':
                tipo_texto = " de gastos"
            elif tipo == 'income':
                tipo_texto = " de entradas"
            
            return (
                f"📊 *Relatório {tipo_texto} - {periodo_label.capitalize()}*\n\n"
                f"📅 Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n\n"
                f"ℹ️ Nenhuma transação encontrada neste período."
            )
        
        # Calcular totais
        total_entradas = sum(t.get('value', 0) for t in transacoes if t.get('type') == 'income')
        total_gastos = sum(t.get('value', 0) for t in transacoes if t.get('type') == 'expense')
        saldo = total_entradas - total_gastos
        
        # Encontrar maior gasto e maior entrada
        gastos = [t for t in transacoes if t.get('type') == 'expense']
        entradas = [t for t in transacoes if t.get('type') == 'income']
        
        maior_gasto = max(gastos, key=lambda x: x.get('value', 0)) if gastos else None
        maior_entrada = max(entradas, key=lambda x: x.get('value', 0)) if entradas else None
        
        # Encontrar dia com mais gasto usando agregação
        pipeline_dia = [
            {'$match': {
                'user_id': user_id_obj,
                'type': 'expense',
                'created_at': {'$gte': start_date, '$lte': end_date}
            }},
            {'$group': {
                '_id': {
                    '$dateToString': {
                        'format': '%Y-%m-%d',
                        'date': '$created_at'
                    }
                },
                'total': {'$sum': '$value'},
                'transacoes': {'$push': '$$ROOT'}
            }},
            {'$sort': {'total': -1}},
            {'$limit': 1}
        ]
        
        resultado_dia = list(coll_transacoes.aggregate(pipeline_dia))
        dia_maior_gasto = None
        if resultado_dia:
            dia_data = resultado_dia[0]
            data_str = dia_data['_id']
            try:
                data_obj = datetime.strptime(data_str, '%Y-%m-%d')
                # Buscar a transação de maior valor desse dia
                transacoes_dia = [t for t in dia_data.get('transacoes', [])]
                maior_transacao_dia = max(transacoes_dia, key=lambda x: x.get('value', 0)) if transacoes_dia else None
                dia_maior_gasto = {
                    'data': data_obj,
                    'total': dia_data['total'],
                    'maior_transacao': maior_transacao_dia
                }
            except:
                pass
        
        # Encontrar categoria com maior gasto
        pipeline_categoria = [
            {'$match': {
                'user_id': user_id_obj,
                'type': 'expense',
                'created_at': {'$gte': start_date, '$lte': end_date}
            }},
            {'$group': {
                '_id': '$category',
                'total': {'$sum': '$value'}
            }},
            {'$sort': {'total': -1}},
            {'$limit': 1}
        ]
        
        resultado_categoria = list(coll_transacoes.aggregate(pipeline_categoria))
        categoria_maior_gasto = resultado_categoria[0] if resultado_categoria else None
        
        # Encontrar horário com maior gasto
        pipeline_horario = [
            {'$match': {
                'user_id': user_id_obj,
                'type': 'expense',
                'created_at': {'$gte': start_date, '$lte': end_date}
            }},
            {'$group': {
                '_id': '$hour',
                'total': {'$sum': '$value'}
            }},
            {'$sort': {'total': -1}},
            {'$limit': 1}
        ]
        
        resultado_horario = list(coll_transacoes.aggregate(pipeline_horario))
        horario_maior_gasto = resultado_horario[0] if resultado_horario else None
        
        # Construir relatório formatado
        relatorio = f"📊 *Relatório Financeiro - {periodo_label.capitalize()}*\n\n"
        relatorio += f"📅 *Período:* {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n\n"
        
        relatorio += f"💰 *Totais:*\n"
        relatorio += f"• Total de Entradas: R$ {total_entradas:.2f}\n"
        relatorio += f"• Total de Gastos: R$ {total_gastos:.2f}\n"
        relatorio += f"• Saldo: R$ {saldo:.2f}\n\n"
        
        if maior_gasto:
            relatorio += f"💸 *Maior Gasto:*\n"
            relatorio += f"• R$ {maior_gasto.get('value', 0):.2f} - {maior_gasto.get('description', 'N/A')}\n"
            relatorio += f"  Categoria: {maior_gasto.get('category', 'N/A')}\n"
            relatorio += f"  Data: {maior_gasto.get('created_at', datetime.now(pytz.timezone('America/Sao_Paulo'))).strftime('%d/%m/%Y %H:%M')}\n\n"
        
        if maior_entrada:
            relatorio += f"💰 *Maior Entrada:*\n"
            relatorio += f"• R$ {maior_entrada.get('value', 0):.2f} - {maior_entrada.get('description', 'N/A')}\n"
            relatorio += f"  Categoria: {maior_entrada.get('category', 'N/A')}\n"
            relatorio += f"  Data: {maior_entrada.get('created_at', datetime.now(pytz.timezone('America/Sao_Paulo'))).strftime('%d/%m/%Y %H:%M')}\n\n"
        
        if dia_maior_gasto:
            relatorio += f"📆 *Dia com Mais Gasto:*\n"
            relatorio += f"• {dia_maior_gasto['data'].strftime('%d/%m/%Y')} - R$ {dia_maior_gasto['total']:.2f}\n"
            if dia_maior_gasto.get('maior_transacao'):
                trans = dia_maior_gasto['maior_transacao']
                relatorio += f"  Maior transação: {trans.get('description', 'N/A')} - R$ {trans.get('value', 0):.2f}\n"
            relatorio += "\n"
        
        if categoria_maior_gasto:
            relatorio += f"🏷️ *Categoria com Maior Gasto:*\n"
            relatorio += f"• {categoria_maior_gasto['_id']} - R$ {categoria_maior_gasto['total']:.2f}\n\n"
        
        if horario_maior_gasto:
            relatorio += f"🕐 *Horário com Maior Gasto:*\n"
            relatorio += f"• {horario_maior_gasto['_id']} horas - R$ {horario_maior_gasto['total']:.2f}\n\n"
        
        relatorio += f"📈 Total de transações analisadas: {len(transacoes)}\n"
        
        print(f"[GERAR_RELATORIO] Relatório gerado com sucesso para {len(transacoes)} transações")
        return relatorio
        
    except Exception as e:
        print(f"[GERAR_RELATORIO] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao gerar relatório: {str(e)}"

@tool("consultar_gasto_categoria")
def consultar_gasto_categoria(categoria: str, periodo: str = "último mês", state: dict = None) -> str:
    """
    Consulta o total gasto por categoria em um período específico.
    
    Use quando o usuário perguntar sobre gastos em uma categoria específica.
    Exemplo: "Quanto gastei com Cigarro mês passado?" ou "Quanto gastei com Alimentação na última semana?"
    
    Args:
        categoria: Nome da categoria (ex: "Cigarro", "Alimentação", "Outros")
        periodo: Período para consulta (ex: "mês passado", "última semana", "últimos 30 dias", "hoje")
        state: Estado atual da conversa (deve conter user_info)
    
    Returns:
        Resumo do gasto total na categoria no período solicitado
    """
    try:
        print(f"[CONSULTAR_GASTO_CATEGORIA] Consultando categoria: {categoria}, período: {periodo}")
        
        # Validar categoria
        if not categoria or categoria.strip() == "":
            return "❌ Erro: Por favor, informe a categoria que deseja consultar."
        
        categoria = categoria.strip()
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[CONSULTAR_GASTO_CATEGORIA] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[CONSULTAR_GASTO_CATEGORIA] Usuário encontrado por email: user_id={user_id}")
                
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[CONSULTAR_GASTO_CATEGORIA] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de consultar gastos."
                    )
                
            except Exception as e:
                print(f"[CONSULTAR_GASTO_CATEGORIA] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Converter user_id para ObjectId se necessário
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        
        # Calcular período usando a função auxiliar
        start_date, end_date, periodo_label = _calcular_periodo(periodo)
        
        print(f"[CONSULTAR_GASTO_CATEGORIA] Período calculado: {start_date} até {end_date}")
        
        # Buscar transações do tipo "expense" (gastos) na categoria especificada
        query = {
            'user_id': user_id_obj,
            'type': 'expense',  # Apenas gastos
            'category': {'$regex': f'^{categoria}$', '$options': 'i'},  # Case-insensitive
            'created_at': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        transacoes = list(coll_transacoes.find(query).sort('created_at', -1))
        
        if not transacoes:
            return (
                f"ℹ️ Não foram encontrados registros de gasto com a categoria *{categoria}* "
                f"no período de {periodo_label} ({start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')})."
            )
        
        # Calcular total gasto
        total_gasto = sum(t.get('value', 0) for t in transacoes)
        
        # Contar número de transações
        num_transacoes = len(transacoes)
        
        # Encontrar maior transação individual
        maior_transacao = max(transacoes, key=lambda x: x.get('value', 0))
        
        # Construir resposta formatada
        resposta = (
            f"💰 *Gastos com {categoria} - {periodo_label.capitalize()}*\n\n"
            f"📅 *Período:* {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n\n"
            f"💵 *Total gasto:* R$ {total_gasto:.2f}\n"
            f"📊 *Número de transações:* {num_transacoes}\n"
            f"📈 *Média por transação:* R$ {total_gasto / num_transacoes:.2f}\n\n"
        )
        
        # Adicionar informação sobre maior transação
        if maior_transacao:
            resposta += (
                f"💸 *Maior transação:*\n"
                f"• R$ {maior_transacao.get('value', 0):.2f} - {maior_transacao.get('description', 'N/A')}\n"
                f"  Data: {maior_transacao.get('created_at', datetime.now(pytz.timezone('America/Sao_Paulo'))).strftime('%d/%m/%Y %H:%M')}\n\n"
            )
        
        # Se houver poucas transações (até 5), listar todas
        if num_transacoes <= 5:
            resposta += f"📋 *Transações:*\n"
            for i, trans in enumerate(transacoes, 1):
                data_trans = trans.get('created_at', datetime.now(pytz.timezone("America/Sao_Paulo")))
                resposta += (
                    f"{i}. R$ {trans.get('value', 0):.2f} - {trans.get('description', 'N/A')} "
                    f"({data_trans.strftime('%d/%m/%Y')})\n"
                )
        
        print(f"[CONSULTAR_GASTO_CATEGORIA] Consulta realizada: {num_transacoes} transações, total R$ {total_gasto:.2f}")
        return resposta
        
    except Exception as e:
        print(f"[CONSULTAR_GASTO_CATEGORIA] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao consultar gastos para a categoria {categoria}: {str(e)}"

# ========================================
# 📅 COMPROMISSOS / AGENDA
# ========================================

@tool("criar_compromisso")
def criar_compromisso(descricao: str, data: str, hora_inicio: str, hora_fim: str = None, titulo: str = None, state: dict = None) -> str:
    """
    Cria um novo compromisso para o usuário no banco de dados.
    Considera horário de início e término.
    
    Use quando o usuário quiser agendar um compromisso ou lembrete.
    Exemplo: "Agende um compromisso para amanhã das 14h às 16h sobre reunião com cliente"
    ou "Crie um compromisso para 15/01/2026 das 10:00 até 12:00 para consulta médica"
    
    IMPORTANTE: Se o usuário não informar o horário de término (hora_fim), 
    você DEVE perguntar antes de finalizar o agendamento.
    
    Args:
        descricao: Descrição do compromisso (obrigatório)
        data: Data do compromisso no formato YYYY-MM-DD ou DD/MM/YYYY (obrigatório)
        hora_inicio: Horário de início no formato HH:MM (obrigatório)
        hora_fim: Horário de término no formato HH:MM (opcional, mas recomendado)
        titulo: Título do compromisso (opcional, se não informado, usa a descrição)
        state: Estado atual da conversa (deve conter user_info)
    
    Returns:
        Mensagem de confirmação do compromisso criado ou solicitação de hora_fim se não informado
    """
    try:
        print(f"[CRIAR_COMPROMISSO] Iniciando: descricao={descricao}, data={data}, hora_inicio={hora_inicio}, hora_fim={hora_fim}")
        
        # Validar campos obrigatórios
        if not descricao or descricao.strip() == "":
            return "❌ Erro: Por favor, informe a descrição do compromisso."
        
        if not data or data.strip() == "":
            return "❌ Erro: Por favor, informe a data do compromisso."
        
        if not hora_inicio or hora_inicio.strip() == "":
            return "❌ Erro: Por favor, informe o horário de início do compromisso."
        
        # Se não tiver hora_fim, solicitar ao usuário
        if not hora_fim or hora_fim.strip() == "":
            return (
                "ℹ️ Para finalizar o agendamento, preciso saber o horário de término.\n\n"
                f"Você informou:\n"
                f"• Data: {data}\n"
                f"• Horário de início: {hora_inicio}\n"
                f"• Descrição: {descricao}\n\n"
                f"⏰ Qual o horário de término? (formato HH:MM, ex: 12:00)"
            )
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[CRIAR_COMPROMISSO] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[CRIAR_COMPROMISSO] Usuário encontrado por email: user_id={user_id}")
                
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[CRIAR_COMPROMISSO] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de criar compromissos."
                    )
                
            except Exception as e:
                print(f"[CRIAR_COMPROMISSO] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Converter user_id para ObjectId se necessário
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        
        # Processar e validar data (aceita data relativa: amanhã, quarta que vem, etc.)
        data_str = data.strip()
        data_obj = None
        # Tentar primeiro como período relativo
        data_resolvida = resolver_data_relativa(data_str)
        if data_resolvida is not None:
            data_obj = datetime.combine(data_resolvida, datetime.min.time())
        if data_obj is None:
            try:
                if '/' in data_str:
                    parts = data_str.split('/')
                    if len(parts) == 3:
                        dia, mes, ano = parts
                        data_obj = datetime(int(ano), int(mes), int(dia))
                    else:
                        raise ValueError("Formato de data inválido")
                elif '-' in data_str:
                    data_obj = datetime.strptime(data_str, '%Y-%m-%d')
                else:
                    raise ValueError("Formato de data inválido")
            except Exception as e:
                return f"❌ Erro: Formato de data inválido. Use DD/MM/YYYY, YYYY-MM-DD ou termos como amanhã, quarta que vem. Erro: {str(e)}"
        
        # Validar que a data não é no passado (opcional, pode remover se quiser permitir)
        if data_obj.date() < datetime.now().date():
            return "❌ Erro: Não é possível criar compromissos para datas passadas."
        
        # Processar e validar hora_inicio
        hora_inicio_str = hora_inicio.strip()
        try:
            # Validar formato HH:MM
            hora_parts = hora_inicio_str.split(':')
            if len(hora_parts) != 2:
                raise ValueError("Formato de hora inválido")
            hora_inicio_int = int(hora_parts[0])
            minuto_inicio_int = int(hora_parts[1])
            
            if not (0 <= hora_inicio_int <= 23):
                raise ValueError("Hora deve estar entre 0 e 23")
            if not (0 <= minuto_inicio_int <= 59):
                raise ValueError("Minuto deve estar entre 0 e 59")
            
            # Criar string de hora_inicio no formato HH:MM
            hora_inicio_formatada = f"{hora_inicio_int:02d}:{minuto_inicio_int:02d}"
            
        except Exception as e:
            return f"❌ Erro: Formato de horário de início inválido. Use HH:MM (ex: 14:30). Erro: {str(e)}"
        
        # Processar e validar hora_fim
        hora_fim_str = hora_fim.strip()
        try:
            # Validar formato HH:MM
            hora_parts = hora_fim_str.split(':')
            if len(hora_parts) != 2:
                raise ValueError("Formato de hora inválido")
            hora_fim_int = int(hora_parts[0])
            minuto_fim_int = int(hora_parts[1])
            
            if not (0 <= hora_fim_int <= 23):
                raise ValueError("Hora deve estar entre 0 e 23")
            if not (0 <= minuto_fim_int <= 59):
                raise ValueError("Minuto deve estar entre 0 e 59")
            
            # Criar string de hora_fim no formato HH:MM
            hora_fim_formatada = f"{hora_fim_int:02d}:{minuto_fim_int:02d}"
            
            # Validar que hora_fim é depois de hora_inicio
            inicio_minutos = hora_inicio_int * 60 + minuto_inicio_int
            fim_minutos = hora_fim_int * 60 + minuto_fim_int
            
            if fim_minutos <= inicio_minutos:
                return "❌ Erro: O horário de término deve ser posterior ao horário de início."
            
        except Exception as e:
            return f"❌ Erro: Formato de horário de término inválido. Use HH:MM (ex: 16:30). Erro: {str(e)}"
        
        # Usar descrição como título se título não foi informado
        titulo_final = titulo.strip() if titulo and titulo.strip() else descricao.strip()
        
        # Verificar se já existe compromisso no mesmo horário
        try:
            compromisso_existente = coll_compromissos.find_one({
                'user_id': user_id_obj,
                'data': data_obj,
                'hora': hora_inicio_formatada
            })
            
            if compromisso_existente:
                return (
                    f"⚠️ Já existe um compromisso agendado para {data_obj.strftime('%d/%m/%Y')} "
                    f"às {hora_inicio_formatada}.\n\n"
                    f"Por favor, escolha outro horário ou cancele o compromisso existente primeiro."
                )
        except Exception as e:
            print(f"[CRIAR_COMPROMISSO] Erro ao verificar compromisso existente: {e}")
            # Continuar mesmo se houver erro na verificação
        
        # Criar documento do compromisso
        compromisso = {
            'user_id': user_id_obj,
            'titulo': titulo_final,
            'descricao': descricao.strip(),
            'data': data_obj,
            'hora': hora_inicio_formatada,  # Mantém compatibilidade (horário de início)
            'hora_inicio': hora_inicio_formatada,
            'hora_fim': hora_fim_formatada,
            'tipo': None,
            'status': 'pendente',
            'lembrete_12h_enviado': False,
            'lembrete_1h_enviado': False,
            'confirmacao_enviada': False,
            'confirmado_usuario': False,
            'created_at': datetime.now(pytz.timezone("America/Sao_Paulo")),
            'updated_at': datetime.now(pytz.timezone("America/Sao_Paulo"))
        }
        
        # Inserir compromisso no MongoDB
        try:
            result = coll_compromissos.insert_one(compromisso)
            compromisso_id = result.inserted_id
            print(f"[CRIAR_COMPROMISSO] Compromisso criado com sucesso: {compromisso_id}")
            
            # Formatar data e hora para exibição
            data_formatada = data_obj.strftime('%d/%m/%Y')
            
            mensagem = (
                f"✅ 📅 Compromisso agendado com sucesso!\n\n"
                f"📋 *Detalhes:*\n"
                f"• Título: {titulo_final}\n"
                f"• Descrição: {descricao.strip()}\n"
                f"• Data: {data_formatada}\n"
                f"• Horário: {hora_inicio_formatada} até {hora_fim_formatada}\n\n"
                f"Seu compromisso para {data_formatada} das {hora_inicio_formatada} até {hora_fim_formatada} foi agendado com sucesso! 🎉"
            )
            
            return mensagem
            
        except Exception as e:
            print(f"[CRIAR_COMPROMISSO] Erro ao inserir compromisso: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Erro ao salvar compromisso no banco de dados: {str(e)}"
            
    except Exception as e:
        print(f"[CRIAR_COMPROMISSO] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao criar compromisso: {str(e)}"


@tool("pesquisar_compromissos")
def pesquisar_compromissos(periodo: str = "próximo mês", state: dict = None) -> str:
    """
    Pesquisa compromissos de um usuário em um período específico.
    
    Use quando o usuário perguntar sobre seus compromissos.
    Exemplo: "Quais meus compromissos no próximo mês?" ou "Quais meus compromissos para a próxima semana?"
    ou "Mostre meus compromissos de hoje"
    
    Args:
        periodo: Período para pesquisa (ex: "próximo mês", "próxima semana", "hoje", "esta semana", "próximos 7 dias")
        state: Estado atual da conversa (deve conter user_info)
    
    Returns:
        Lista formatada de compromissos encontrados
    """
    try:
        print(f"[PESQUISAR_COMPROMISSOS] Iniciando pesquisa: periodo={periodo}")
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[PESQUISAR_COMPROMISSOS] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[PESQUISAR_COMPROMISSOS] Usuário encontrado por email: user_id={user_id}")
                
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[PESQUISAR_COMPROMISSOS] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de pesquisar compromissos."
                    )
                
            except Exception as e:
                print(f"[PESQUISAR_COMPROMISSOS] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Converter user_id para ObjectId se necessário
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        
        # Resolver período: tentar primeiro período relativo (hoje, amanhã, próxima semana, etc.)
        intervalo = resolver_periodo_relativo(periodo)
        if intervalo is not None:
            start_date, end_date = intervalo
            start_date = datetime.combine(start_date, datetime.min.time())
            end_date = datetime.combine(end_date, datetime.max.time()).replace(hour=23, minute=59, second=59, microsecond=0)
            periodo_label = periodo.strip()
        else:
            # Fallback: calcular período baseado no texto (compatibilidade)
            periodo_lower = periodo.lower().strip()
            hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if "hoje" in periodo_lower:
                start_date = hoje
                end_date = hoje.replace(hour=23, minute=59, second=59)
                periodo_label = "hoje"
            elif "amanhã" in periodo_lower or "amanha" in periodo_lower:
                start_date = hoje + timedelta(days=1)
                end_date = start_date.replace(hour=23, minute=59, second=59)
                periodo_label = "amanhã"
            elif "semana" in periodo_lower or "7 dias" in periodo_lower:
                start_date = hoje
                end_date = hoje + timedelta(days=7)
                periodo_label = "próximos 7 dias"
            elif "mês" in periodo_lower or "mes" in periodo_lower:
                start_date = hoje
                end_date = hoje + timedelta(days=30)
                periodo_label = "próximo mês"
            elif "15 dias" in periodo_lower:
                start_date = hoje
                end_date = hoje + timedelta(days=15)
                periodo_label = "próximos 15 dias"
            else:
                start_date = hoje
                end_date = hoje + timedelta(days=30)
                periodo_label = "próximo mês"
        
        print(f"[PESQUISAR_COMPROMISSOS] Período calculado: {start_date} até {end_date}")
        
        # Buscar compromissos no período
        query = {
            'user_id': user_id_obj,
            'data': {
                '$gte': start_date,
                '$lte': end_date
            }
        }
        
        compromissos = list(coll_compromissos.find(query).sort('data', 1).sort('hora', 1))
        
        if not compromissos:
            return (
                f"ℹ️ Você não tem compromissos agendados para o período solicitado ({periodo_label}).\n\n"
                f"📅 Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
            )
        
        # Formatar resposta
        resposta = (
            f"📅 *Seus Compromissos - {periodo_label.capitalize()}*\n\n"
            f"📆 *Período:* {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}\n"
            f"📊 *Total:* {len(compromissos)} compromisso(s)\n\n"
        )
        
        # Agrupar por data
        compromissos_por_data = {}
        for comp in compromissos:
            data_comp = comp.get('data')
            if isinstance(data_comp, datetime):
                data_key = data_comp.strftime('%d/%m/%Y')
            else:
                data_key = str(data_comp)
            
            if data_key not in compromissos_por_data:
                compromissos_por_data[data_key] = []
            compromissos_por_data[data_key].append(comp)
        
        # Listar compromissos agrupados por data
        for data_key in sorted(compromissos_por_data.keys()):
            comps_do_dia = compromissos_por_data[data_key]
            resposta += f"📆 *{data_key}*\n"
            
            for i, comp in enumerate(comps_do_dia, 1):
                titulo = comp.get('titulo', 'Sem título')
                descricao = comp.get('descricao', '')
                # Priorizar hora_inicio e hora_fim, mas manter compatibilidade com 'hora'
                hora_inicio = comp.get('hora_inicio') or comp.get('hora', '00:00')
                hora_fim = comp.get('hora_fim', '')
                status = comp.get('status', 'pendente')
                
                # Emoji de status
                status_emoji = {
                    'pendente': '⏳',
                    'confirmado': '✅',
                    'concluido': '✔️',
                    'cancelado': '❌'
                }.get(status, '📌')
                
                # Formatar horário
                if hora_fim:
                    horario_str = f"{hora_inicio} até {hora_fim}"
                else:
                    horario_str = hora_inicio
                
                resposta += (
                    f"  {i}. {status_emoji} *{horario_str}* - {titulo}\n"
                )
                if descricao and descricao != titulo:
                    resposta += f"     📝 {descricao}\n"
                resposta += "\n"
        
        print(f"[PESQUISAR_COMPROMISSOS] {len(compromissos)} compromissos encontrados")
        return resposta
        
    except Exception as e:
        print(f"[PESQUISAR_COMPROMISSOS] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao pesquisar compromissos: {str(e)}"


@tool("cancelar_compromisso")
def cancelar_compromisso(data: str, hora_inicio: str, hora_fim: str = None, state: dict = None) -> str:
    """
    Cancela um compromisso do usuário no banco de dados.
    Considera o horário de início e término para localizar o compromisso.
    
    Use quando o usuário quiser cancelar um compromisso.
    Exemplo: "Quero cancelar meu compromisso para amanhã das 10:00 até 12:00"
    ou "Cancelar o compromisso do dia 25/12 às 10:00"
    
    Args:
        data: Data do compromisso no formato YYYY-MM-DD ou DD/MM/YYYY (obrigatório)
        hora_inicio: Horário de início no formato HH:MM (obrigatório)
        hora_fim: Horário de término no formato HH:MM (opcional, mas recomendado para maior precisão)
        state: Estado atual da conversa (deve conter user_info)
    
    Returns:
        Mensagem de confirmação do cancelamento ou erro se não encontrado
    """
    try:
        print(f"[CANCELAR_COMPROMISSO] Iniciando: data={data}, hora_inicio={hora_inicio}, hora_fim={hora_fim}")
        
        # Validar campos obrigatórios
        if not data or data.strip() == "":
            return "❌ Erro: Por favor, informe a data do compromisso a ser cancelado."
        
        if not hora_inicio or hora_inicio.strip() == "":
            return "❌ Erro: Por favor, informe o horário de início do compromisso a ser cancelado."
        
        # Obter informações do usuário do state
        user_id = None
        telefone = None
        email = None
        
        if state and "user_info" in state:
            user_info = state["user_info"]
            telefone = user_info.get("telefone")
            email = user_info.get("email")
            user_id = user_info.get("user_id") or user_info.get("_id")
            print(f"[CANCELAR_COMPROMISSO] Info do state: telefone={telefone}, email={email}, user_id={user_id}")
        
        # Se não tiver user_id, buscar no MongoDB
        if not user_id:
            try:
                if email:
                    user = coll_clientes.find_one({'email': email.lower().strip()})
                    if user:
                        user_id = user.get('_id')
                        print(f"[CANCELAR_COMPROMISSO] Usuário encontrado por email: user_id={user_id}")
                
                if not user_id and telefone:
                    user = coll_clientes.find_one({
                        '$or': [
                            {'telefone': telefone},
                            {'phone': telefone}
                        ]
                    })
                    if user:
                        user_id = user.get('_id')
                        print(f"[CANCELAR_COMPROMISSO] Usuário encontrado por telefone: user_id={user_id}")
                
                if not user_id:
                    return (
                        "❌ Erro: Usuário não encontrado no sistema. "
                        "Por favor, faça o cadastro primeiro antes de cancelar compromissos."
                    )
                
            except Exception as e:
                print(f"[CANCELAR_COMPROMISSO] Erro ao buscar usuário: {e}")
                return f"❌ Erro ao buscar usuário no banco de dados: {str(e)}"
        
        # Converter user_id para ObjectId se necessário
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        
        # Processar e validar data
        data_str = data.strip()
        try:
            # Tentar formato DD/MM/YYYY primeiro
            if '/' in data_str:
                parts = data_str.split('/')
                if len(parts) == 3:
                    dia, mes, ano = parts
                    data_obj = datetime(int(ano), int(mes), int(dia))
                else:
                    raise ValueError("Formato de data inválido")
            # Tentar formato YYYY-MM-DD
            elif '-' in data_str:
                data_obj = datetime.strptime(data_str, '%Y-%m-%d')
            else:
                raise ValueError("Formato de data inválido")
        except Exception as e:
            return f"❌ Erro: Formato de data inválido. Use DD/MM/YYYY ou YYYY-MM-DD. Erro: {str(e)}"
        
        # Processar e validar hora_inicio
        hora_inicio_str = hora_inicio.strip()
        try:
            hora_parts = hora_inicio_str.split(':')
            if len(hora_parts) != 2:
                raise ValueError("Formato de hora inválido")
            hora_inicio_int = int(hora_parts[0])
            minuto_inicio_int = int(hora_parts[1])
            
            if not (0 <= hora_inicio_int <= 23):
                raise ValueError("Hora deve estar entre 0 e 23")
            if not (0 <= minuto_inicio_int <= 59):
                raise ValueError("Minuto deve estar entre 0 e 59")
            
            hora_inicio_formatada = f"{hora_inicio_int:02d}:{minuto_inicio_int:02d}"
            
        except Exception as e:
            return f"❌ Erro: Formato de horário de início inválido. Use HH:MM (ex: 10:00). Erro: {str(e)}"
        
        # Processar hora_fim se informado
        hora_fim_formatada = None
        if hora_fim and hora_fim.strip():
            hora_fim_str = hora_fim.strip()
            try:
                hora_parts = hora_fim_str.split(':')
                if len(hora_parts) != 2:
                    raise ValueError("Formato de hora inválido")
                hora_fim_int = int(hora_parts[0])
                minuto_fim_int = int(hora_parts[1])
                
                if not (0 <= hora_fim_int <= 23):
                    raise ValueError("Hora deve estar entre 0 e 23")
                if not (0 <= minuto_fim_int <= 59):
                    raise ValueError("Minuto deve estar entre 0 e 59")
                
                hora_fim_formatada = f"{hora_fim_int:02d}:{minuto_fim_int:02d}"
                
            except Exception as e:
                return f"❌ Erro: Formato de horário de término inválido. Use HH:MM (ex: 12:00). Erro: {str(e)}"
        
        # Construir query para buscar o compromisso
        query = {
            'user_id': user_id_obj,
            'data': data_obj,
            '$or': [
                {'hora': hora_inicio_formatada},  # Compatibilidade com campo antigo
                {'hora_inicio': hora_inicio_formatada}
            ]
        }
        
        # Se hora_fim foi informado, adicionar à query para maior precisão
        if hora_fim_formatada:
            query = {
                'user_id': user_id_obj,
                'data': data_obj,
                '$or': [
                    {'hora': hora_inicio_formatada},
                    {'hora_inicio': hora_inicio_formatada}
                ],
                'hora_fim': hora_fim_formatada
            }
        
        # Buscar compromisso
        try:
            compromisso = coll_compromissos.find_one(query)
            
            if not compromisso:
                # Tentar busca mais flexível (apenas por data e hora_inicio)
                query_simples = {
                    'user_id': user_id_obj,
                    'data': data_obj,
                    '$or': [
                        {'hora': hora_inicio_formatada},
                        {'hora_inicio': hora_inicio_formatada}
                    ]
                }
                compromisso = coll_compromissos.find_one(query_simples)
                
                if not compromisso:
                    data_formatada = data_obj.strftime('%d/%m/%Y')
                    if hora_fim_formatada:
                        return (
                            f"❌ Não encontramos um compromisso agendado para "
                            f"{data_formatada} das {hora_inicio_formatada} até {hora_fim_formatada}.\n\n"
                            f"Verifique se a data e os horários estão corretos."
                        )
                    else:
                        return (
                            f"❌ Não encontramos um compromisso agendado para "
                            f"{data_formatada} às {hora_inicio_formatada}.\n\n"
                            f"Verifique se a data e o horário estão corretos. "
                            f"Se o compromisso tiver horário de término, informe também para maior precisão."
                        )
            
            # Compromisso encontrado, remover do banco
            compromisso_id = compromisso.get('_id')
            result = coll_compromissos.delete_one({'_id': compromisso_id})
            
            if result.deleted_count > 0:
                data_formatada = data_obj.strftime('%d/%m/%Y')
                hora_fim_display = hora_fim_formatada or compromisso.get('hora_fim', '')
                
                if hora_fim_display:
                    mensagem = (
                        f"✅ Compromisso cancelado com sucesso!\n\n"
                        f"📋 *Detalhes do compromisso cancelado:*\n"
                        f"• Data: {data_formatada}\n"
                        f"• Horário: {hora_inicio_formatada} até {hora_fim_display}\n"
                        f"• Descrição: {compromisso.get('descricao', 'N/A')}\n\n"
                        f"Seu compromisso para {data_formatada} das {hora_inicio_formatada} até {hora_fim_display} foi cancelado com sucesso! ✅"
                    )
                else:
                    mensagem = (
                        f"✅ Compromisso cancelado com sucesso!\n\n"
                        f"📋 *Detalhes do compromisso cancelado:*\n"
                        f"• Data: {data_formatada}\n"
                        f"• Horário: {hora_inicio_formatada}\n"
                        f"• Descrição: {compromisso.get('descricao', 'N/A')}\n\n"
                        f"Seu compromisso para {data_formatada} às {hora_inicio_formatada} foi cancelado com sucesso! ✅"
                    )
                
                print(f"[CANCELAR_COMPROMISSO] Compromisso cancelado: {compromisso_id}")
                return mensagem
            else:
                return "❌ Erro: Não foi possível cancelar o compromisso. Tente novamente."
                
        except Exception as e:
            print(f"[CANCELAR_COMPROMISSO] Erro ao buscar/cancelar compromisso: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Erro ao cancelar compromisso: {str(e)}"
            
    except Exception as e:
        print(f"[CANCELAR_COMPROMISSO] Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erro ao cancelar compromisso: {str(e)}"


@tool("confirmar_compromisso")
def confirmar_compromisso(codigo: str, acao: str, state: dict = None) -> str:
    """
    Confirma ou cancela um compromisso usando o código recebido no lembrete por WhatsApp.
    Use quando o usuário enviar CONFIRMAR <codigo> ou CANCELAR <codigo>.
    Args:
        codigo: Código de 6 caracteres do lembrete (ex: a1b2c3).
        acao: "confirmar" ou "cancelar".
        state: Estado atual (deve conter user_info com user_id).
    Returns:
        Mensagem de sucesso ou erro.
    """
    if not codigo or not codigo.strip():
        return "❌ Código inválido ou já processado."
    codigo = codigo.strip()
    acao = (acao or "").strip().lower()
    if acao not in ("confirmar", "cancelar"):
        return "❌ Ação inválida. Use confirmar ou cancelar."

    if not state or not state.get("user_info"):
        return "❌ Código inválido ou já processado."
    user_id = state["user_info"].get("user_id")
    if not user_id:
        return "❌ Código inválido ou já processado."

    try:
        user_id_obj = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        compromisso = coll_compromissos.find_one({
            "codigo_confirmacao": codigo,
            "user_id": user_id_obj,
            "confirmacao_pendente": True,
        })
        if not compromisso:
            return "❌ Código inválido ou já processado."

        if acao == "confirmar":
            coll_compromissos.update_one(
                {"_id": compromisso["_id"]},
                {
                    "$set": {
                        "status": "confirmado",
                        "confirmado_usuario": True,
                        "confirmacao_pendente": False,
                        "confirmado_em": datetime.now(pytz.timezone("America/Sao_Paulo")),
                    }
                },
            )
            return "✅ Compromisso confirmado com sucesso!"
        else:
            coll_compromissos.update_one(
                {"_id": compromisso["_id"]},
                {"$set": {"status": "cancelado", "confirmacao_pendente": False}},
            )
            return "❌ Compromisso cancelado com sucesso."
    except Exception as e:
        print(f"[CONFIRMAR_COMPROMISSO] Erro: {e}")
        return "❌ Código inválido ou já processado."


# ========================================
# 🛠️ LISTA DE FERRAMENTAS
# ========================================

tools = [
    # Transações Financeiras
    cadastrar_transacao,
    gerar_relatorio,
    consultar_gasto_categoria,
    # Compromissos / Agenda
    criar_compromisso,
    pesquisar_compromissos,
    cancelar_compromisso,
    confirmar_compromisso,
    # Consultas
    consultar_material_de_apoio
]

# ========================================
# 🤖 CLASSE AGENT
# ========================================

class AgentAssistente:
    def __init__(self):
        self.memory = self._init_memory()
        self.model = self._build_agent()

    # ------------------------------------
    # Utils
    # ------------------------------------
    def _convert_datetime_to_string(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_datetime_to_string(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetime_to_string(i) for i in obj]
        return obj

    def _prepare_safe_state(self, state: State) -> dict:
        try:
            safe_state = {}
            for key, value in state.items():
                if key == "messages":
                    continue
                safe_state[key] = self._convert_datetime_to_string(value)
            return safe_state
        except Exception as e:
            print(f"[PREPARE_SAFE_STATE] Erro: {e}")
            return {"user_info": state.get("user_info", {})}

    def _init_memory(self):
        return MongoDBSaver(coll_memoria)

    # ------------------------------------
    # Build Agent
    # ------------------------------------
    def _build_agent(self):
        graph_builder = StateGraph(State)

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=OPENAI_API_KEY,
            streaming=True
        )

        llm_with_tools = llm.bind_tools(tools=tools)

        # --------------------------------
        # Chatbot node
        # --------------------------------
        def chatbot(state: State, config: RunnableConfig) -> State:
            user_info = state.get("user_info", {})
            nome = user_info.get("nome")
            telefone = user_info.get("telefone")
            plano = user_info.get("plano")
            status_assinatura = user_info.get("status_assinatura")
            data_vencimento_plano = user_info.get("data_vencimento_plano")

            # Trial expirado: atualizar banco e tratar como sem_plano
            if plano == "trial" and data_vencimento_plano and getattr(data_vencimento_plano, "year", None):
                now = datetime.utcnow()
                venc = data_vencimento_plano
                if getattr(venc, "tzinfo", None) is not None:
                    from datetime import timezone as tz
                    venc = venc.astimezone(tz.utc).replace(tzinfo=None)
                if venc < now:
                    user_id = user_info.get("user_id")
                    if user_id:
                        try:
                            coll_clientes.update_one(
                                {"_id": ObjectId(user_id)},
                                {"$set": {
                                    "plano": "sem_plano",
                                    "status_assinatura": "vencida",
                                    "assinatura.plano": "sem_plano",
                                    "assinatura.status": "vencida",
                                    "updated_at": datetime.utcnow(),
                                }}
                            )
                        except Exception:
                            pass
                    user_info["plano"] = "sem_plano"
                    user_info["status_assinatura"] = "vencida"
                    plano = "sem_plano"
                    status_assinatura = "vencida"

            bloqueado = (
                plano == "sem_plano"
                or status_assinatura in ("vencida", "inativa")
            )
            link_planos = os.getenv("LINK_PLANOS", (DJANGO_BASE_URL or "").rstrip("/") + "/planos/")

            if nome:
                instrucao = (
                    f"\n\n🚨 INSTRUÇÃO CRÍTICA: "
                    f"O usuário {nome} JÁ ESTÁ IDENTIFICADO. "
                    f"NÃO peça nome nem email."
                )
            else:
                instrucao = (
                    "\n\n🚨 INSTRUÇÃO CRÍTICA: "
                    "O usuário NÃO está identificado. "
                    "Siga o fluxo de identificação."
                )

            sem_plano_instrucao = ""
            if bloqueado:
                sem_plano_instrucao = (
                    "\n\n🚨 INSTRUÇÃO CRÍTICA: "
                    "O usuário está sem plano ativo (teste ou assinatura expirados). NÃO execute ferramentas. "
                    "Responda de forma natural e amigável, incluindo esta informação: "
                    "Seu período de teste ou assinatura expirou 😕 "
                    "Para continuar utilizando todas as funcionalidades do Leozera, escolha um plano no link: " + link_planos + " "
                    "Enquanto isso, posso te explicar como funciona ou tirar dúvidas. "
                    "Mantenha o tom humanizado, sem parecer bloqueio técnico."
                )

            data_atual = datetime.now().strftime("%d/%m/%Y")
            system_prompt = SystemMessage(
                content=(
                    SYSTEM_PROMPT +
                    f"\n\nDATA ATUAL DO SISTEMA: {data_atual}\n"
                    "Use essa data como referência ao interpretar termos como: hoje, amanhã, ontem, próxima semana, quarta que vem, mês que vem, sexta, etc.\n"
                    f"\n\nUSUÁRIO ATUAL:"
                    f"\n- Nome: {nome}"
                    f"\n- Telefone: {telefone}"
                    f"\n- Status: {user_info.get('status')}"
                    f"\n- Plano: {plano}"
                    f"\n- Status assinatura: {status_assinatura}"
                    f"{instrucao}"
                    f"{sem_plano_instrucao}"
                )
            )

            state["user_info"] = self._convert_datetime_to_string(user_info)
            if bloqueado:
                response = llm.invoke([system_prompt] + state["messages"])
            else:
                response = llm_with_tools.invoke([system_prompt] + state["messages"])

            return {
                **state,
                "messages": state["messages"] + [response]
            }

        # --------------------------------
        # Tool node seguro
        # --------------------------------
        def safe_tool_node(state: State) -> State:
            from langchain_core.messages import ToolMessage

            messages = state.get("messages", [])
            if not messages:
                return state

            last_message = messages[-1]
            if not getattr(last_message, "tool_calls", None):
                return state

            tool_messages = []
            user_status = state.get("user_info", {}).get("status")
            user_plano = state.get("user_info", {}).get("plano")

            for call in last_message.tool_calls:
                if user_status != "ativo":
                    tool_messages.append(
                        ToolMessage(
                            content="🔒 Para utilizar essa funcionalidade é necessário cadastro.\nPosso te explicar como funciona ou enviar o link para se registrar.",
                            tool_call_id=call["id"],
                            name=call["name"]
                        )
                    )
                    continue
                if user_plano == "sem_plano":
                    tool_messages.append(
                        ToolMessage(
                            content="Para usar essa funcionalidade é necessário ter um plano ativo. Seu período de teste terminou. Escolha um dos planos disponíveis para continuar usando o Leozera.",
                            tool_call_id=call["id"],
                            name=call["name"]
                        )
                    )
                    continue

                tool_func = next((t for t in tools if t.name == call["name"]), None)
                if not tool_func:
                    continue

                try:
                    safe_state = self._prepare_safe_state(state)
                    if "state" in tool_func.func.__code__.co_varnames:
                        call["args"]["state"] = safe_state

                    result = tool_func.invoke(call["args"])

                    tool_messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=call["id"],
                            name=call["name"]
                        )
                    )
                except Exception as e:
                    tool_messages.append(
                        ToolMessage(
                            content=f"Erro: {e}",
                            tool_call_id=call["id"],
                            name=call["name"]
                        )
                    )

            return {
                **state,
                "messages": state["messages"] + tool_messages
            }

        # --------------------------------
        # Roteadores
        # --------------------------------
        def rotear_apos_check_user(state: State) -> str:
            status = state.get("user_info", {}).get("status")
            if status == "ativo":
                return "check_plano"
            if status == "precisa_email":
                return "ask_email"
            return "chatbot"

        def rotear_apos_check_plano(state: State) -> str:
            return state.get("user_info", {}).get("plano_result", "plano_ativo")

        def rotear_apos_check_email(state: State) -> str:
            return "chatbot"

        # --------------------------------
        # Nodes
        # --------------------------------
        graph_builder.add_node("entrada_usuario", RunnableLambda(lambda s: s))
        graph_builder.add_node("check_user_role", RunnableLambda(check_user))
        graph_builder.add_node("check_plano", RunnableLambda(check_plano))
        graph_builder.add_node("bloqueio_plano", RunnableLambda(bloqueio_plano))
        graph_builder.add_node("ask_email", RunnableLambda(ask_email))
        graph_builder.add_node("check_user_by_email", RunnableLambda(check_user_by_email))
        graph_builder.add_node("chatbot", chatbot)
        graph_builder.add_node("tools", safe_tool_node)

        # --------------------------------
        # Fluxo
        # --------------------------------
        graph_builder.set_entry_point("entrada_usuario")
        graph_builder.add_edge("entrada_usuario", "check_user_role")

        graph_builder.add_conditional_edges(
            "check_user_role",
            rotear_apos_check_user,
            {
                "check_plano": "check_plano",
                "chatbot": "chatbot",
                "ask_email": "ask_email",
            }
        )

        graph_builder.add_conditional_edges(
            "check_plano",
            rotear_apos_check_plano,
            {
                "plano_ativo": "chatbot",
                "sem_plano": "bloqueio_plano",
            }
        )

        graph_builder.add_edge("bloqueio_plano", END)

        graph_builder.add_edge("ask_email", "check_user_by_email")

        graph_builder.add_conditional_edges(
            "check_user_by_email",
            rotear_apos_check_email,
            {
                "chatbot": "chatbot",
            }
        )

        graph_builder.add_conditional_edges(
            "chatbot",
            tools_condition,
            {"tools": "tools", "__end__": END}
        )

        graph_builder.add_edge("tools", "chatbot")

        return graph_builder.compile(checkpointer=self.memory)

    def memory_agent(self):
        return self.model
