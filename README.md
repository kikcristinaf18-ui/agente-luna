# agente-luna

API do agente **TIAGA** — assistente de IA que guia mulheres empreendedoras, passo a passo, na criação de agentes inteligentes para seus negócios.

## O que faz

- Conversa com a empreendedora em linguagem simples, sem jargão técnico
- Usa o diagnóstico de maturidade digital salvo no Supabase para personalizar cada conversa
- Segue uma metodologia em 5 etapas: conhecer o negócio → identificar dores → explicar IA → sugerir agentes → guiar a criação
- Rastreia em qual etapa cada usuária está, mesmo que ela feche e reabra o app

## Stack

| Tecnologia | Uso |
|---|---|
| [Claude (Anthropic)](https://anthropic.com) | Modelo de IA do agente TIAGA |
| [FastAPI](https://fastapi.tiangolo.com) | API REST |
| [Supabase](https://supabase.com) | Banco de dados, autenticação e perfis |
| [Railway](https://railway.app) | Deploy e hosting |

## Pré-requisitos

- Python 3.11+
- Conta na [Anthropic](https://console.anthropic.com) com API key
- Projeto no [Supabase](https://supabase.com) configurado

## Configuração local

**1. Clone o repositório**
```bash
git clone https://github.com/kikcristinaf18-ui/agente-luna.git
cd agente-luna
```

**2. Crie o ambiente virtual e instale as dependências**
```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

**3. Configure as variáveis de ambiente**
```bash
cp .env.exemplo .env
# Abra o .env e preencha ANTHROPIC_API_KEY, SUPABASE_URL e SUPABASE_SERVICE_KEY
```

**4. Execute a migration no Supabase**

Abra o SQL Editor no painel do Supabase e execute o conteúdo de:
```
migrations/001_sessoes_chat.sql
```

**5. Suba o servidor**
```bash
uvicorn api:app --reload --port 8000
```

A API estará disponível em `http://localhost:8000`.

## Endpoints

### `POST /sessao/iniciar`
Cria uma nova sessão de chat.

**Header obrigatório:** `Authorization: Bearer <supabase_access_token>`

**Body (opcional):**
```json
{
  "user_id": "uuid-da-usuária",
  "diagnostico": {
    "nome": "Maria",
    "nome_empresa": "Doces da Maria",
    "score_maturidade": 35,
    "gargalos": ["Atendimento manual no WhatsApp", "Sem controle de pedidos"]
  }
}
```

**Resposta:**
```json
{
  "sessao_id": "uuid",
  "mensagem_inicial": "Oi, Maria! Eu sou a TIAGA! 🌟...",
  "etapa_atual": 1
}
```

---

### `POST /chat`
Envia uma mensagem e recebe a resposta da TIAGA.

**Header obrigatório:** `Authorization: Bearer <supabase_access_token>`

**Body:**
```json
{
  "sessao_id": "uuid-da-sessão",
  "mensagem": "Tenho uma doceria e passo o dia inteiro respondendo WhatsApp"
}
```

**Resposta:**
```json
{
  "resposta": "Ai, entendo demais, Maria! Fica o dia todo no celular é esgotante...",
  "etapa_atual": 2,
  "sessao_id": "uuid-da-sessão"
}
```

---

### `GET /sessao/{sessao_id}/historico`
Retorna o histórico completo da conversa.

**Header obrigatório:** `Authorization: Bearer <supabase_access_token>`

---

### `DELETE /sessao/{sessao_id}`
Encerra uma sessão.

**Header obrigatório:** `Authorization: Bearer <supabase_access_token>`

---

### `GET /health`
Verifica se a API está no ar. Não requer autenticação.

---

### `GET /debug/usuario/{user_id}`
Retorna os dados do Supabase para um usuário (uso interno / desenvolvimento).

**Header obrigatório:** `Authorization: Bearer <supabase_access_token>`

## Autenticação

Todos os endpoints (exceto `/health`) exigem o token JWT do Supabase no header:

```
Authorization: Bearer <access_token>
```

O `access_token` é o token que o Supabase retorna após o login da usuária no frontend.
A API valida o token diretamente com o Supabase — não é preciso gerenciar tokens manualmente.

## Tabelas no Supabase

Além das tabelas já existentes (`profiles`, `ai_diagnostics`, etc.), a migration cria:

| Tabela | Descrição |
|---|---|
| `sessoes_chat` | Uma linha por sessão de conversa (etapa atual, ativa/encerrada) |
| `historico_chat` | Todas as mensagens de cada sessão em ordem cronológica |

## Deploy no Railway

O projeto já tem `Procfile` e `railway.toml` configurados. Para fazer o deploy:

1. Conecte o repositório no [Railway](https://railway.app)
2. Adicione as variáveis de ambiente no painel do Railway:
   - `ANTHROPIC_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
3. O Railway detecta automaticamente o `Procfile` e sobe o servidor

## Estrutura do projeto

```
agente-luna/
├── agent.py              # Lógica da TIAGA: system prompt, prompt caching, metodologia
├── api.py                # API FastAPI: endpoints, autenticação, sessões
├── supabase_context.py   # Camada de dados: perfil, diagnóstico, sessões persistidas
├── migrations/
│   └── 001_sessoes_chat.sql  # Tabelas de sessão e histórico
├── .env.exemplo          # Template de variáveis de ambiente
├── requirements.txt      # Dependências Python
├── Procfile              # Comando de start para Railway/Heroku
└── railway.toml          # Configuração do Railway
```
