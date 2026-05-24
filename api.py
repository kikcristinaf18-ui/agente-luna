"""
API FastAPI para o agente TIAGA — Guia de Agentes para Empreendedoras
Integre com sua plataforma no Lovable via fetch/axios.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import logging

from agent import chat_com_luna, iniciar_conversa, criar_cliente
from supabase_context import buscar_contexto_completo, montar_diagnostico_para_luna
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TIAGA — Agente para Empreendedoras",
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
diagnosticos: dict[str, dict] = {}  # sessao_id → diagnóstico da empreendedora

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

class Diagnostico(BaseModel):
    # Dados pessoais (vêm do profile do usuário)
    nome: Optional[str] = None
    nome_empresa: Optional[str] = None
    # Dados do payload da tabela ai_diagnostics ou invite_respondents
    resumo_executivo: Optional[str] = None
    score_maturidade: Optional[float] = None
    gargalos: Optional[list[str]] = None
    quick_wins: Optional[list[str]] = None
    projetos_estrategicos: Optional[list[str]] = None
    projetos_avancados: Optional[list[str]] = None
    recomendacoes: Optional[list[str]] = None
    oportunidades: Optional[list[dict]] = None


class IniciarSessaoRequest(BaseModel):
    user_id: Optional[str] = None       # passa isso → Tiaga busca TUDO no Supabase
    diagnostico: Optional[Diagnostico] = None  # fallback manual (sem Supabase)


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
        "status": "TIAGA está online e pronta para ajudar! 🌟",
        "api_key_configurada": chave_ok
    }


@app.post("/sessao/iniciar", response_model=IniciarSessaoResponse)
def iniciar_sessao(body: IniciarSessaoRequest = IniciarSessaoRequest()):
    """
    Cria uma nova sessão de conversa com a TIAGA.

    Passe o diagnóstico da empreendedora (vindo do Supabase) para personalizar a conversa:

        fetch('/sessao/iniciar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            diagnostico: {
              nome: "Maria Silva",
              nome_empresa: "Ateliê da Maria",
              segmento: "Moda / Costura",
              tempo_mercado: "3 anos",
              dores: ["Demora muito para responder clientes", "Perde vendas por falta de tempo"],
              nivel_tech: "iniciante",
              objetivos: ["Automatizar atendimento", "Ter mais tempo para criar peças"]
            }
          })
        })
    """
    sessao_id = str(uuid.uuid4())
    sessoes[sessao_id] = []

    diag_dict = None

    if body.user_id:
        # Busca automática de TODOS os dados da empreendedora no Supabase
        try:
            ctx = buscar_contexto_completo(body.user_id)
            diag_dict = montar_diagnostico_para_luna(ctx)
            logger.info(
                f"Sessão {sessao_id} — dados carregados do Supabase para: "
                f"{diag_dict.get('nome', '?') if diag_dict else 'sem perfil'}"
            )
        except Exception as e:
            logger.error(f"Erro ao buscar dados do Supabase: {e}")
    elif body.diagnostico:
        # Fallback: diagnóstico passado manualmente
        diag_dict = body.diagnostico.model_dump()
        logger.info(f"Sessão {sessao_id} iniciada com diagnóstico manual.")
    else:
        logger.info(f"Sessão {sessao_id} iniciada sem dados — Tiaga vai perguntar do zero.")

    if diag_dict:
        diagnosticos[sessao_id] = diag_dict

    mensagem_inicial = iniciar_conversa(diag_dict)

    return IniciarSessaoResponse(
        sessao_id=sessao_id,
        mensagem=mensagem_inicial
    )


@app.post("/chat", response_model=EnviarMensagemResponse)
def enviar_mensagem(body: EnviarMensagemRequest):
    """
    Envia uma mensagem para a TIAGA e recebe a resposta.

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
        console.log(data.resposta) // resposta da TIAGA
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

    diag = diagnosticos.get(body.sessao_id)

    try:
        resposta = chat_com_luna(historico, get_cliente(), diagnostico=diag)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Erro ao chamar a TIAGA: {e}\n{traceback.format_exc()}")
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
