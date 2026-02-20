from flask import Flask, request, jsonify
from services.waha import Waha
from services.agent_restaurante import AgentRestaurante, atualizar_status_pedido
#from services.agent_barber import AgentBarber
from services.agent_financeiro import AgentAssistente
import time
import random
from langchain_core.prompts.chat import AIMessage,HumanMessage
from langchain_core.messages import ToolMessage
import logging
import datetime
import os
import urllib.parse
from dotenv import load_dotenv,find_dotenv
from pymongo import MongoClient
import tempfile
import requests
from openai import OpenAI

load_dotenv(find_dotenv())

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
WAHA_API_KEY = os.getenv('WAHA_API_KEY')
WAHA_BASE_URL = os.getenv('WAHA_BASE_URL', 'http://localhost:3000')
MONGO_USER = urllib.parse.quote_plus(os.getenv('MONGO_USER'))
MONGO_PASS = urllib.parse.quote_plus(os.getenv('MONGO_PASS'))

# Configura cliente OpenAI
client_openai = OpenAI(api_key=OPENAI_API_KEY)

client = MongoClient("mongodb+srv://%s:%s@cluster0.gjkin5a.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0" % (MONGO_USER, MONGO_PASS))
db_restaurante = client.restaurante_db
coll3_restaurante = db_restaurante.pedidos
db_financeiro = client.financeiro_db
coll_financeiro = db_financeiro.financeiro
coll_usuarios = db_financeiro.users

def formatar_mensagem_whatsapp(texto: str) -> str:
    """
    Ajusta a formatação para o padrão do WhatsApp.
    - Transforma **negrito** (markdown) em *negrito* (WhatsApp)
    - Remove excesso de espaços ou caracteres inválidos, se quiser expandir
    """
    return texto.replace("**", "*")

def gerar_mensagem_status(pedido_id: str, cliente_nome: str, status_anterior: str, 
                         novo_status: str, valor_total: float, tipo_entrega: str) -> str:
    """
    Gera mensagem personalizada baseada no status do pedido
    """
    # Emojis e mensagens para cada status
    status_messages = {
        "Recebido": {
            "emoji": "📝",
            "message": "Seu pedido foi *recebido* e está sendo processado!"
        },
        "Confirmado": {
            "emoji": "✅", 
            "message": "Seu pedido foi *confirmado* e está sendo preparado!"
        },
        "Enviado para cozinha": {
            "emoji": "👨‍🍳",
            "message": "Seu pedido foi *enviado para a cozinha* e está sendo preparado!"
        },
        "Em preparo": {
            "emoji": "🔥",
            "message": "Seu pedido está *em preparo*! Nossa equipe está trabalhando para você!"
        },
        "Pronto": {
            "emoji": "🍔",
            "message": "Seu pedido está *pronto*! 🎉"
        },
        "Saiu para entrega": {
            "emoji": "🚚",
            "message": "Seu pedido *saiu para entrega*! Em breve estará com você!"
        },
        "Entregue": {
            "emoji": "🎊",
            "message": "Seu pedido foi *entregue*! Aproveite sua refeição! 🍽️"
        },
        "Cancelado": {
            "emoji": "❌",
            "message": "Seu pedido foi *cancelado*. Entre em contato conosco se precisar de ajuda."
        }
    }
    
    # Busca informações do status
    status_info = status_messages.get(novo_status, {
        "emoji": "📋",
        "message": f"Status do seu pedido foi atualizado para: *{novo_status}*"
    })
    
    # Formata valor total
    valor_formatado = f"R$ {valor_total:.2f}".replace(".", ",")
    
    # Determina tipo de entrega
    entrega_texto = "delivery" if tipo_entrega == "entrega" else "retirada no local"
    
    # Monta a mensagem
    mensagem = f"""
{status_info['emoji']} *Atualização do Pedido #{pedido_id}*

Olá *{cliente_nome}*! 

{status_info['message']}

📋 *Detalhes do pedido:*
• Valor total: {valor_formatado}
• Tipo: {entrega_texto}
• Status anterior: {status_anterior}
• Novo status: *{novo_status}*

Obrigado por escolher o Pirão Burger! 🍔🔥
    """.strip()
    
    return mensagem

app = Flask(__name__)

# Config Mercado Pago assinatura recorrente
_back_url = os.getenv("BACK_URL", os.getenv("BASE_URL", "")).rstrip("/")
if _back_url and not _back_url.startswith("http"):
    _back_url = "https://" + _back_url
import mercadopago_assinatura as mp_assinatura  # noqa: E402
mp_assinatura.MONGO_USER = MONGO_USER
mp_assinatura.MONGO_PASS = MONGO_PASS
mp_assinatura.MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
mp_assinatura.MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET")
mp_assinatura.BACK_URL_BASE = _back_url

agent_4 = AgentRestaurante()
model_4 = agent_4.memory_agent()

#agent_barber = AgentBarber()
#model_barber = agent_barber.memory_agent()

agent_financeiro = AgentAssistente()
model_financeiro = agent_financeiro.memory_agent()

def agent_memory(agent_model, input: str, thread_id: str, date: str = None):
    try:
        if not thread_id:
            raise ValueError("thread_id é obrigatório no config.")

        # 1) Prepara as entradas e o config
        inputs = {"messages": [{"role": "user", "content": input}]}
        config = {"configurable": {"thread_id": thread_id}}

        print(f"Entradas para o modelo: {inputs}")
        print(">>> [DEBUG] config que será passado para invoke:", config)

        # 2) Executa o grafo
        result = agent_model.invoke(inputs, config)
        print(f"Resultado bruto do grafo: {result}")

        # 3) Extrai a lista interna
        raw = result.get("messages") if isinstance(result, dict) else result

        # 4) Converte cada mensagem em dict simples
        msgs = []
        for m in raw:
            if isinstance(m, (HumanMessage, AIMessage, ToolMessage)):
                msgs.append({"role": m.type, "content": m.content})
            elif isinstance(m, dict):
                msgs.append(m)
            else:
                msgs.append({"role": getattr(m, "role", "assistant"), "content": str(m)})

        # 5) Retorna o conteúdo da última mensagem útil
        ultima = msgs[-1] if msgs else {"content": "⚠️ Nenhuma resposta gerada."}
        return ultima["content"]

    except Exception as e:
        logging.error(f"Erro ao invocar o agente: {str(e)}")
        raise

# ---------- Assinatura recorrente Mercado Pago ----------
@app.route("/api/assinar/<plano>", methods=["POST"])
def api_assinar_plano(plano):
    return mp_assinatura.assinar_plano(plano)


@app.route("/api/webhook/mercadopago", methods=["POST"])
def api_webhook_mercadopago():
    return mp_assinatura.webhook_mercadopago()


@app.route('/chatbot/webhook/restaurante/', methods=['POST'])
def webhook_4():
    return process_message(model_4, "AGENT4", 'restaurante')

#@app.route('/chatbot/webhook/barber/', methods=['POST'])
#def webhook_barber():
#    return process_message(model_barber, "AGENT_BARBER", 'barber')

@app.route('/chatbot/webhook/assistente/', methods=['POST'])
def webhook_financeiro():
    return process_message(model_financeiro, "AGENT_ASSISTANT", 'assistente')

@app.route('/webhook/atualizar-status/', methods=['POST'])
def atualizar_status():
    """
    Processa webhook de atualização de status do pedido e envia notificação para o cliente
    """
    try:
        data = request.json
        print("Webhook de atualização de status:", data)
        
        # Validação dos dados obrigatórios
        required_fields = ['event', 'pedido_id', 'cliente_nome', 'cliente_telefone', 'status_anterior', 'novo_status']
        for field in required_fields:
            if field not in data:
                print(f"❌ Campo obrigatório ausente: {field}")
                return jsonify({"status": "error", "message": f"Campo obrigatório ausente: {field}"}), 400
        
        # Extrai dados do webhook
        pedido_id = data['pedido_id']
        cliente_nome = data['cliente_nome']
        cliente_telefone = data['cliente_telefone']
        status_anterior = data['status_anterior']
        novo_status = data['novo_status']
        valor_total = data.get('valor_total', 0)
        tipo_entrega = data.get('tipo_entrega', 'entrega')
        
        # Formata telefone para padrão internacional
        telefone_formatado = cliente_telefone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        if not telefone_formatado.startswith("55"):
            telefone_formatado = "55" + telefone_formatado
        
        # Gera mensagem personalizada baseada no status
        mensagem = gerar_mensagem_status(
            pedido_id=pedido_id,
            cliente_nome=cliente_nome,
            status_anterior=status_anterior,
            novo_status=novo_status,
            valor_total=valor_total,
            tipo_entrega=tipo_entrega
        )
        
        # Envia mensagem via WhatsApp
        waha = Waha()
        session = "restaurante"
        chat_id = telefone_formatado + "@c.us"
        
        # Simula digitação
        waha.start_typing(chat_id=chat_id, session=session)
        time.sleep(random.randint(2, 4))
        
        # Envia mensagem formatada
        mensagem_formatada = formatar_mensagem_whatsapp(mensagem)
        waha.send_message(chat_id, mensagem_formatada, session)
        
        # Para digitação
        waha.stop_typing(chat_id=chat_id, session=session)
        
        print(f"✅ Notificação de status enviada para {cliente_nome} ({chat_id})")
        print(f"📱 Mensagem: {mensagem_formatada}")
        
        return jsonify({"status": "success", "message": "Notificação enviada com sucesso"}), 200
        
    except Exception as e:
        print(f"❌ Erro ao processar webhook de status: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook/asaas/', methods=['POST'])
def asaas_webhook():
    data = request.json
    print("Webhook do Asaas recebido:", data)

    # Só processa pagamento confirmado
    if data.get("event") != "PAYMENT_RECEIVED":
        return jsonify({"status": "ignored"}), 200

    description = data["payment"].get("description", "")

    # Exemplo: "Pedido #d815e354 - Vinícius - (11)91234-5678 - Pirão Burger"
    import re
    padrao = r"Pedido\s+#(\w+)\s*-\s*(.*?)\s*-\s*(.*?)\s*-"
    match = re.search(padrao, description)

    if not match:
        print("⚠️ Formato inesperado de description:", description)
        return jsonify({"status": "error", "message": "Formato inválido de description"}), 400

    id_pedido = match.group(1).strip()
    nome_cliente = match.group(2).strip()
    telefone = match.group(3).strip()

    # Aqui você pode normalizar o telefone para padrão internacional (ex: 55DDDNUMERO)
    telefone_formatado = telefone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
    if not telefone_formatado.startswith("55"):
        telefone_formatado = "55" + telefone_formatado  # adiciona DDI Brasil

    # Mensagem personalizada
    mensagem = (
        f"*Pagamento confirmado!* 🎉\n\n"
        f"✅ Pedido *#{id_pedido}*\n"
        f"👤 Cliente: *{nome_cliente}*\n"
        f"📞 Telefone: {telefone}\n\n"
        f"Obrigado por comprar no Pirão Burger, Seu pedido já foi encaminhado para cozinha 🍔🔥"
    )

    try:
        atualizar_status_pedido(id_pedido, "Enviado para cozinha")
        waha = Waha()
        session = "restaurante"  # ajuste conforme sua sessão do Waha
        chat_id = telefone_formatado + "@c.us"

        waha.start_typing(chat_id=chat_id, session=session)
        time.sleep(random.randint(2, 5))
        waha.send_message(chat_id, mensagem, session)
        waha.stop_typing(chat_id=chat_id, session=session)

        print(f"Mensagem enviada para {chat_id}: {mensagem}")

    except Exception as e:
        print("❌ Erro ao enviar mensagem no WhatsApp:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success"}), 200
 
def process_message(agent, agent_name, session):
    data = request.json
    print(f'EVENTO RECEBIDO ({agent_name}): {data}')

    hoje = datetime.date.today().isoformat()

    # 🔥 NOVO PADRÃO COMPATÍVEL COM TODAS AS ENGINES
    event = data.get("event")
    payload = data.get("data") or data.get("payload") or {}

    if not payload:
        print("❌ Payload vazio")
        return jsonify({'status': 'ignored'}), 200

    chat_id = payload.get("from")

    # 🔥 CORREÇÃO PARA NOWEB (@lid)
    if chat_id and chat_id.endswith("@lid"):
        alt = payload.get("_data", {}).get("key", {}).get("remoteJidAlt")
        if alt:
            numero = alt.replace("@s.whatsapp.net", "")
            chat_id = numero + "@c.us"

    received_message = (
        payload.get("body")
        or payload.get("text", {}).get("body")
        or payload.get("conversation")
    )

    msg_type = payload.get("type")

    # 🔥 Se não vier type mas tiver mensagem, assume texto
    if not msg_type and received_message:
        msg_type = "chat"
    location_data = payload.get("location")
    media_info = payload.get("media")

    if not chat_id:
        print("❌ chat_id ausente")
        return jsonify({'status': 'ignored'}), 200

    # Ignorar grupos e status
    if '@g.us' in chat_id or 'status@broadcast' in chat_id:
        return jsonify({'status': 'ignored'}), 200

    # =============================
    # 📍 LOCALIZAÇÃO
    # =============================
    if location_data:
        try:
            lat = location_data.get('latitude')
            lon = location_data.get('longitude')
            address = location_data.get('address', '')

            if lat and lon:
                mensagem_localizacao = (
                    f"Calcule a entrega para esta localização: "
                    f"latitude {lat}, longitude {lon}, endereço: {address}"
                )

                resposta = agent_memory(
                    agent_model=agent,
                    input=mensagem_localizacao,
                    thread_id=chat_id,
                    date=hoje
                )
            else:
                resposta = "❌ Não foi possível obter a localização."
        except Exception as e:
            resposta = f"❌ Erro ao processar localização: {str(e)}"

    # =============================
    # 🎧 ÁUDIO
    # =============================
    elif media_info and payload.get("hasMedia"):
        try:
            audio_url = media_info.get('url')

            if audio_url:
                audio_url = audio_url.replace("http://localhost:3000", WAHA_BASE_URL)

            headers = {"X-Api-Key": WAHA_API_KEY} if WAHA_API_KEY else {}

            with tempfile.NamedTemporaryFile(suffix=".oga", delete=True) as temp_audio:
                r = requests.get(audio_url, headers=headers, timeout=30)
                r.raise_for_status()
                temp_audio.write(r.content)
                temp_audio.flush()

                with open(temp_audio.name, "rb") as audio_file:
                    transcript = client_openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )

            texto_transcrito = transcript.text.strip()

            if texto_transcrito:
                resposta = agent_memory(
                    agent_model=agent,
                    input=texto_transcrito,
                    thread_id=chat_id,
                    date=hoje
                )
            else:
                resposta = "❌ Não consegui entender o áudio."

        except Exception as e:
            print(f"Erro áudio: {e}")
            resposta = "❌ Erro ao processar áudio."

    # =============================
    # 💬 TEXTO NORMAL
    # =============================
    else:
        if msg_type not in ['chat', 'text'] or not received_message:
            return jsonify({'status': 'ignored'}), 200

        try:
            resposta = agent_memory(
                agent_model=agent,
                input=received_message,
                thread_id=chat_id,
                date=hoje
            )
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # =============================
    # 📤 ENVIO DA RESPOSTA
    # =============================
    print(f"📤 Enviando resposta para {chat_id}: {resposta}")

    waha = Waha()
    waha.start_typing(chat_id=chat_id, session=session)

    resposta_format = formatar_mensagem_whatsapp(resposta)
    time.sleep(random.randint(2, 5))

    waha.send_message(chat_id, resposta_format, session)
    waha.stop_typing(chat_id=chat_id, session=session)

    print(f"✅ Mensagem enviada com sucesso para {chat_id}")

    return jsonify({'status': 'success'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
