# Leozera

## 🚀 Sobre o Projeto

**Leozera** é um SaaS de gestão financeira pessoal com assistente inteligente via WhatsApp. A plataforma combina controle de receitas e despesas, relatórios, agenda com lembretes e um assistente com IA para atendimento 24h, voltado a usuários que desejam organizar suas finanças com praticidade.

O sistema oferece período de teste gratuito, planos mensal e anual com pagamento recorrente via Mercado Pago, e downgrade automático ao fim do trial ou da assinatura, mantendo o usuário sempre ciente do status da conta.

---

## ✨ Funcionalidades

- **Dashboard financeiro** — Visão consolidada por período (diário, semanal, mensal): totais de despesas e receitas, resultado do período, dia/categoria/horário de maior gasto, gráficos por categoria, dia da semana e horário, tabela de transações com paginação.
- **Insights com IA** — Análise automática dos dados do período com insight estratégico, alertas e recomendações (endpoint `/finance/api/insights/`).
- **Relatório inteligente** — Relatório textual detalhado do período selecionado, com resumo e metadados; preparado para impressão.
- **Transações** — Registro de entradas e gastos com categoria, descrição e data; listagem filtrada por período e paginada.
- **Categorias** — Categorias pré-definidas e personalizadas por tipo (receita, despesa, etc.); gerenciamento via interface.
- **Agenda e compromissos** — Calendário (dia/semana/mês), criação e edição de compromissos com data e hora; integração com sistema de lembretes.
- **Configurações de perfil** — Edição de nome, telefone e foto de perfil; alteração de senha com validação; alteração de e-mail com confirmação por link.
- **Página de planos** — Exibição de planos disponíveis e fluxo de assinatura (checkout Mercado Pago).

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

- **Trial** — 7 dias gratuitos para novos usuários; ao expirar, o usuário é rebaixado para “sem plano” e pode ser notificado (ex.: WhatsApp).
- **Mensal e anual** — Assinatura recorrente via **Mercado Pago** (preapproval); checkout iniciado a partir do dashboard (Django) e webhook para confirmação/cancelamento.
- **Downgrade automático** — Tarefas agendadas (Celery Beat) verificam trial e planos vencidos e atualizam o status no banco (sem_plano / inativa), mantendo a experiência consistente com a assinatura.

Os dados de assinatura são centralizados no objeto `assinatura` do usuário (plano, status, datas, gateway, etc.), com compatibilidade com campos legados.

---

## 🔔 Sistema de Lembretes

- **Celery Worker + Celery Beat** — Execução de tarefas assíncronas e agendadas com **Redis** como broker e backend.
- **Lembretes de compromissos** — Verificação periódica (ex.: a cada 5 minutos) para enviar:
  - Lembrete 12h antes e/ou pedido de confirmação.
  - Lembrete 1h antes.
- **Trial expirado** — Notificação ao usuário quando o período de teste termina (com opção de envio via WhatsApp).
- **Planos vencidos** — Rebaixamento automático de usuários com data de vencimento ultrapassada.

O envio de mensagens utiliza o serviço centralizado **WAHA** (WhatsApp).

---

## 🏗️ Arquitetura

- **Backend** — Django 4.2 (apps `core` e `finance`), autenticação via sessão e middleware que injeta o usuário do MongoDB (`user_mongo`). APIs REST sob `/finance/api/` e `/api/`.
- **Banco de dados** — **MongoDB** (dados de usuários, transações, compromissos, assinaturas); acesso via repositórios e, onde configurado, MongoEngine. SQLite usado apenas para sessões do Django, se aplicável.
- **Filas** — **Redis** como broker/backend do Celery; workers no app `agent_ia` (tasks de lembretes, trial e planos vencidos).
- **Assinaturas** — Módulo `mercadopago_assinatura` (Flask-compatível) para criação de preapproval e tratamento de webhook; usuários identificados por `gateway_subscription_id` ou campos legados.
- **E-mail** — Serviço de e-mail (ex.: Resend) para confirmação de cadastro, recuperação de senha e confirmação de novo e-mail.
- **Frontend** — Templates Django (HTML/JS/CSS), dashboard com Chart.js, consumo das APIs de dashboard, gráficos, transações, insights e relatório.

---

## 🔐 Segurança

- **Autenticação** — Login por e-mail e senha; sessão Django; middleware garante que rotas protegidas tenham `user_mongo` injetado a partir do usuário logado no MongoDB.
- **Confirmação de e-mail** — Cadastro com token de verificação enviado por e-mail; link com validade limitada.
- **Recuperação de senha** — Fluxo de reset com token e link por e-mail.
- **Alteração de e-mail** — Novo e-mail só é ativado após confirmação por link (token), sem alterar o banco antes da confirmação.
- **APIs** — Endpoints de dados (dashboard, insights, transações, etc.) utilizam o `user_id` do usuário autenticado (sessão), sem confiar em parâmetros do cliente para identificação.
- **Webhook Mercado Pago** — Validação do preapproval na API do Mercado Pago antes de atualizar o status da assinatura no banco.

---

## 🧩 Tecnologias Utilizadas

| Camada        | Tecnologia |
|---------------|------------|
| Backend       | Python 3.11, Django 4.2, Django REST Framework |
| Banco de dados| MongoDB (PyMongo, MongoEngine), SQLite (sessões) |
| Filas         | Celery 5.3, Redis 7 |
| Pagamentos    | Mercado Pago (assinatura recorrente) |
| IA            | OpenAI (gpt-4o-mini), LangChain (assistente) |
| E-mail        | Resend (ou provedor configurável) |
| WhatsApp      | WAHA (WhatsApp HTTP API) |
| Frontend      | HTML/CSS/JS, Chart.js, Tailwind CSS (onde aplicado) |
| Servidor      | Gunicorn |
| Ambiente      | Docker, Docker Compose |

Variáveis sensíveis (chaves de API, conexões MongoDB, Redis, etc.) vêm do ambiente (`.env`); nenhuma chave deve ser commitada.

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

## 🐳 Docker

O projeto inclui `Dockerfile` e `docker-compose.yml` para rodar a aplicação, Redis e Celery em containers.

### Serviços

- **web** — Aplicação Django (Gunicorn) na porta 8000.
- **redis** — Redis 7 (broker e backend do Celery).
- **celery_worker** — Worker Celery (tasks de lembretes, trial, planos vencidos).
- **celery_beat** — Agendador Celery (agenda das tarefas periódicas).

### Uso

1. Configure o `.env` na raiz com as mesmas variáveis da instalação local (MongoDB, Redis, APIs, etc.).

2. Suba os serviços:
   ```bash
   docker-compose up -d
   ```

3. A aplicação estará em `http://localhost:8000`. O worker e o beat usarão o Redis e o MongoDB definidos no `.env`.

Para desenvolvimento com volume montado (código local refletido no container), o `docker-compose` já monta o diretório atual em `/app`.

---

## 🌎 Deploy

Para produção:

- Defina `DEBUG=False` e um `SECRET_KEY` forte.
- Configure `ALLOWED_HOSTS` com o(s) domínio(s) da aplicação.
- Use um servidor de aplicação (Gunicorn) atrás de um proxy reverso (Nginx, Cloudflare, etc.).
- Garanta MongoDB e Redis acessíveis a partir do ambiente de produção.
- Configure variáveis de ambiente (incluindo chaves de API e URLs de webhook do Mercado Pago) no provedor de deploy (VPS, PaaS, etc.).
- Se o assistente e os lembretes rodarem no mesmo projeto, garanta que o Celery worker e o beat tenham acesso ao mesmo Redis e MongoDB e às mesmas variáveis de ambiente.

Não commite arquivos `.env` ou credenciais no repositório.

---

## 📌 Roadmap

- Evolução do relatório (exportação PDF, mais períodos).
- Ampliação dos insights de IA no dashboard (mais métricas e sugestões).
- Notificações in-app além do WhatsApp.
- Melhorias de acessibilidade e responsividade na interface.
- Testes automatizados (unitários e de integração) para core e finance.

---

## 📄 Licença

Este projeto é proprietário. O uso, cópia e distribuição estão sujeitos aos termos definidos pelo titular do repositório. Entre em contato para mais informações.
