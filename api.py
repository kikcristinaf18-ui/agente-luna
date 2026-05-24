"""
API FastAPI para o agente LUNA — Guia de Agentes para Empreendedoras
Integre com sua plataforma no Lovable via fetch/axios.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import logging

from agent import chat_com_luna, iniciar_conversa, criar_cliente

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LUNA — Agente para Empreendedoras",
    description="API do agente que ajuda mulheres empreendedoras a criar seus agentes",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessoes: dict[str, list[dict]] = {}

# Cliente criado sob demanda para não travar se a chave não estiver configurada
_cliente_anthropic = None

def get_cliente():
    global _cliente_anthropic
    if _cliente_anthropic is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY não configurada. Adicione a variável no Railway."
            )
        _cliente_anthropic = criar_cliente()
    return _cliente_anthropic


# ── Modelos de dados ──────────────────────────────────────────────────────────

class IniciarSessaoResponse(BaseModel):
    sessao_id: str
    mensagem: str


class EnviarMensagemRequest(BaseModel):
    sessao_id: str
    mensagem: str


class EnviarMensagemResponse(BaseModel):
    resposta: str
    sessao_id: str


class HistoricoResponse(BaseModel):
    sessao_id: str
    mensagens: list[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def raiz():
    chave_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {
        "status": "LUNA está online e pronta para ajudar! 🌟",
        "api_key_configurada": chave_ok
    }


@app.post("/sessao/iniciar", response_model=IniciarSessaoResponse)
def iniciar_sessao():
    """
    Cria uma nova sessão de conversa com a LUNA.
    Chame isso quando uma empreendedora entrar no chat pela primeira vez.
    """
    sessao_id = str(uuid.uuid4())
    sessoes[sessao_id] = []

    mensagem_inicial = iniciar_conversa()

    return IniciarSessaoResponse(
        sessao_id=sessao_id,
        mensagem=mensagem_inicial
    )


@app.post("/chat", response_model=EnviarMensagemResponse)
def enviar_mensagem(body: EnviarMensagemRequest):
    """
    Envia uma mensagem para a LUNA e recebe a resposta.

    Exemplo de uso no Lovable (JavaScript):

        const res = await fetch('https://sua-api.com/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessao_id: 'id-da-sessao',
            mensagem: 'Vendo roupas femininas'
          })
        })
        const data = await res.json()
        console.log(data.resposta) // resposta da LUNA
    """
    # Se a sessão não existe (ex: servidor reiniciou), cria uma nova automaticamente
    if body.sessao_id not in sessoes:
        logger.warning(f"Sessão {body.sessao_id} não encontrada — criando nova automaticamente.")
        sessoes[body.sessao_id] = []

    historico = sessoes[body.sessao_id]

    historico.append({
        "role": "user",
        "content": body.mensagem
    })

    try:
        resposta = chat_com_luna(historico, get_cliente())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao chamar a LUNA: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar mensagem: {str(e)}"
        )

    historico.append({
        "role": "assistant",
        "content": resposta
    })

    sessoes[body.sessao_id] = historico

    return EnviarMensagemResponse(
        resposta=resposta,
        sessao_id=body.sessao_id
    )


@app.get("/sessao/{sessao_id}/historico", response_model=HistoricoResponse)
def ver_historico(sessao_id: str):
    """Retorna todo o histórico de conversa de uma sessão."""
    if sessao_id not in sessoes:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    return HistoricoResponse(
        sessao_id=sessao_id,
        mensagens=sessoes[sessao_id]
    )


@app.delete("/sessao/{sessao_id}")
def encerrar_sessao(sessao_id: str):
    """Encerra e apaga uma sessão."""
    if sessao_id not in sessoes:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    del sessoes[sessao_id]
    return {"mensagem": "Sessão encerrada com sucesso."}
