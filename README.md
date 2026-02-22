# Leozera

Sistema SaaS de organização financeira com inteligência artificial integrada ao WhatsApp.

O objetivo é permitir que usuários registrem gastos, recebam insights financeiros e acompanhem sua vida financeira através de um dashboard inteligente.

---

# Funcionalidades

## Registro de transações via WhatsApp

Usuários podem registrar gastos ou receitas enviando mensagens no WhatsApp.

Exemplo:

*"Gastei 45 reais no mercado"*

A IA interpreta e registra a transação automaticamente.

## Dashboard financeiro

Interface web onde o usuário pode visualizar:

- Total de gastos
- Total de receitas
- Saldo do período
- Categoria com maior gasto
- Dia com maior gasto
- Horário com maior gasto
- Gráficos financeiros

## Insights com IA

O sistema gera automaticamente:

- análise financeira
- alertas de comportamento
- recomendações

## Relatórios automáticos

Geração de relatório financeiro mensal com análise detalhada.

## Sistema de categorias

Usuários podem:

- criar categorias
- editar categorias
- remover categorias

Cada usuário possui seu próprio conjunto de categorias.

## Sistema de planos

Controle de assinatura do usuário.

## Integração com WhatsApp

Usuários podem iniciar conversa com o assistente diretamente pelo dashboard.

## Suporte pelo WhatsApp

Botão "Leozera WPP" no dashboard.

## Página de novidades

Sistema interno para comunicação com os usuários.

Tipos de novidades:

- Nova funcionalidade
- Melhoria
- Correção de bug
- Notícia

Admins podem publicar atualizações.

Usuários podem visualizar artigos detalhados.

## Sistema de feedback da comunidade

Usuários podem:

- enviar sugestões
- relatar bugs

Esses tickets são enviados por email.

---

# Stack tecnológica

**Backend:**

- Python
- Django
- MongoDB

**Frontend:**

- HTML
- TailwindCSS
- JavaScript

**Infraestrutura:**

- PythonAnywhere
- WhatsApp API (WAHA)

**IA:**

- OpenAI

---

# Arquitetura do sistema

- Web app Django
- Banco MongoDB
- Integração com WhatsApp
- Processamento de IA para interpretação de mensagens
- Dashboard financeiro

---

# Versionamento

**Versão atual:** `v0.2.0`

## Versões

### v0.2.0

Principais mudanças:

- integração completa com WhatsApp
- dashboard financeiro
- insights automáticos com IA
- sistema de categorias por usuário
- página de novidades
- suporte via WhatsApp
- sistema de sugestões e reporte de bugs

---

## 🤖 Assistente com IA

O assistente financeiro virtual (Leozera) atua via **WhatsApp**, utilizando IA (OpenAI/LangChain) para:

- Identificar o usuário por telefone ou e-mail e verificar plano ativo.
- Registrar transações (entradas e gastos) por conversa.
- Gerar relatórios sob demanda (período passado, última semana, período customizado).
- Criar e gerenciar compromissos na agenda, com envio de lembretes e confirmações.
- Bloquear uso de ferramentas quando o plano estiver expirado, orientando a renovação.

O fluxo inclui verificação de assinatura (trial, mensal, anual), bloqueio amigável para usuários sem plano e integração com o banco de dados (MongoDB) para transações e compromissos. O envio de mensagens é feito via **WAHA** (WhatsApp HTTP API).

---

## 💳 Planos e Assinaturas

- **Trial** — 7 dias gratuitos para novos usuários; ao expirar, o usuário é rebaixado para "sem plano" e pode ser notificado (ex.: WhatsApp).
- **Mensal e anual** — Assinatura recorrente via **Mercado Pago** (preapproval); checkout iniciado a partir do dashboard (Django) e webhook para confirmação/cancelamento.
- **Downgrade automático** — Tarefas agendadas (Celery Beat) verificam trial e planos vencidos e atualizam o status no banco (sem_plano / inativa), mantendo a experiência consistente com a assinatura.

Os dados de assinatura são centralizados no objeto `assinatura` do usuário (plano, status, datas, gateway, etc.), com compatibilidade com campos legados.

---

## 🔐 Segurança

- **Autenticação** — Login por e-mail e senha; sessão Django; middleware garante que rotas protegidas tenham `user_mongo` injetado a partir do usuário logado no MongoDB.
- **Confirmação de e-mail** — Cadastro com token de verificação enviado por e-mail; link com validade limitada.
- **Recuperação de senha** — Fluxo de reset com token e link por e-mail.
- **Alteração de e-mail** — Novo e-mail só é ativado após confirmação por link (token), sem alterar o banco antes da confirmação.
- **APIs** — Endpoints de dados (dashboard, insights, transações, etc.) utilizam o `user_id` do usuário autenticado (sessão), sem confiar em parâmetros do cliente para identificação.
- **Webhook Mercado Pago** — Validação do preapproval na API do Mercado Pago antes de atualizar o status da assinatura no banco.

---

## ⚙️ Instalação

### Pré-requisitos

- Python 3.11+
- MongoDB (acesso via string de conexão)
- Redis (para Celery)
- Contas/credenciais: OpenAI, Mercado Pago, Resend (e-mail), WAHA (WhatsApp), conforme uso desejado

### Passos

1. Clone o repositório e entre na pasta do projeto.

2. Crie um ambiente virtual e ative-o:
   ```bash
   python -m venv venv
   # Windows: venv\Scripts\activate
   # Linux/macOS: source venv/bin/activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure o ambiente — crie um arquivo `.env` na raiz (ou em `dashboard/`, conforme carregamento do `load_dotenv` no `settings`) com as variáveis necessárias, por exemplo:
   - `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
   - `MONGO_USER`, `MONGO_PASS`, `MONGO_HOST`, `MONGO_DB_NAME`
   - `REDIS_URL` (ex.: `redis://localhost:6379/0`)
   - `OPENAI_API_KEY`
   - `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET` (Mercado Pago)
   - `RESEND_API_KEY`, `EMAIL_FROM`
   - `WAHA_API_URL`, `WAHA_API_KEY`, `WAHA_SESSION` (WhatsApp)

5. Execute as migrações do Django (se houver modelos que usem migrations):
   ```bash
   python manage.py migrate
   ```

6. Inicie o servidor:
   ```bash
   python manage.py runserver
   ```

7. Para lembretes e tarefas periódicas, em outro(s) terminal(is), com o Redis rodando:
   ```bash
   cd agent_ia
   celery -A celery_app.celery worker --loglevel=info
   celery -A celery_app.celery beat --loglevel=info
   ```

A aplicação estará disponível em `http://localhost:8000` (ou na porta configurada). O Celery deve usar o mesmo `REDIS_URL` e variáveis de ambiente (MongoDB, WAHA, etc.) para acessar dados e enviar mensagens.

---

## 🌎 Deploy (PythonAnywhere)

1. **Atualizar código no servidor:**
   ```bash
   git pull origin main
   ```

2. **Atualizar dependências (se necessário):**
   ```bash
   pip install -r requirements.txt
   ```

3. **Recarregar a aplicação** no painel do PythonAnywhere (Web → Reload).

Não commite arquivos `.env` ou credenciais no repositório.

---

## 📄 Licença

Este projeto é proprietário. O uso, cópia e distribuição estão sujeitos aos termos definidos pelo titular do repositório. Entre em contato para mais informações.
