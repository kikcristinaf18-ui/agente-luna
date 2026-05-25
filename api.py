import logging
import anthropic
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import chat_com_luna, iniciar_conversa
from supabase_context import (
    buscar_contexto_completo,
    montar_diagnostico_para_luna,
    criar_sessao_db,
    buscar_sessao_db,
    salvar_mensagem_db,
    buscar_historico_db,
    atualizar_etapa_db,
    encerrar_sessao_db,
    verificar_jwt,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TIAGA API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cliente_anthropic: anthropic.Anthropic | None = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _cliente_anthropic
    if _cliente_anthropic is None:
        _cliente_anthropic = anthropic.Anthropic()
    return _cliente_anthropic


# ── Autenticação ──────────────────────────────────────────────────────────────

async def usuario_autenticado(authorization: str = Header(...)) -> str:
    """
    Extrai o Bearer token e valida com Supabase.
    Retorna o user_id autenticado.
    Uso no frontend: Authorization: Bearer <supabase_access_token>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato inválido. Use: Bearer <token>")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return verificar_jwt(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ── Modelos de request/response ───────────────────────────────────────────────

class Diagnostico(BaseModel):
    nome: str | None = None
    nome_empresa: str | None = None
    resumo_executivo: str | None = None
    score_maturidade: float | None = None
    gargalos: list[str] | None = None
    quick_wins: list[str] | None = None
    projetos_estrategicos: list[str] | None = None
    oportunidades: list[dict] | None = None
    recomendacoes: list[str] | None = None


class IniciarSessaoRequest(BaseModel):
    user_id: str | None = None
    diagnostico: Diagnostico | None = None


class ChatRequest(BaseModel):
    sessao_id: str
    mensagem: str


class ChatResponse(BaseModel):
    resposta: str
    etapa_atual: int
    sessao_id: str


class SessaoResponse(BaseModel):
    sessao_id: str
    mensagem_inicial: str
    etapa_atual: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/sessao/iniciar", response_model=SessaoResponse)
async def iniciar_sessao(
    body: IniciarSessaoRequest,
    user_id: str = Depends(usuario_autenticado),
):
    """
    Cria uma nova sessão de chat.
    - Se informar user_id no body: busca diagnóstico no Supabase.
    - Se informar diagnostico no body: usa os dados fornecidos diretamente.
    - Se não informar nenhum: inicia sem diagnóstico.
    O user_id autenticado (do JWT) é sempre usado para vincular a sessão.
    """
    diagnostico: dict | None = None

    uid_para_busca = body.user_id or user_id
    if uid_para_busca:
        try:
            ctx = buscar_contexto_completo(uid_para_busca)
            diagnostico = montar_diagnostico_para_luna(ctx)
            logger.info("Diagnóstico carregado do Supabase para user %s", uid_para_busca)
        except Exception as e:
            logger.warning("Não foi possível carregar diagnóstico do Supabase: %s", e)

    if diagnostico is None and body.diagnostico:
        diagnostico = body.diagnostico.model_dump(exclude_none=True)

    sessao_id = criar_sessao_db(user_id)
    mensagem_inicial = iniciar_conversa(diagnostico)

    salvar_mensagem_db(sessao_id, "assistant", mensagem_inicial)

    logger.info("Sessão criada: %s para user %s", sessao_id, user_id)
    return SessaoResponse(
        sessao_id=sessao_id,
        mensagem_inicial=mensagem_inicial,
        etapa_atual=1,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user_id: str = Depends(usuario_autenticado),
):
    """
    Processa uma mensagem da empreendedora e retorna a resposta da TIAGA.
    O histórico é carregado do Supabase — resistente a reinicializações do servidor.
    """
    sessao = buscar_sessao_db(body.sessao_id)

    if sessao is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    if sessao["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão.")

    if not sessao["ativa"]:
        raise HTTPException(status_code=410, detail="Sessão encerrada.")

    historico = buscar_historico_db(body.sessao_id)
    historico.append({"role": "user", "content": body.mensagem})

    try:
        uid_para_diag = sessao["user_id"]
        ctx = buscar_contexto_completo(uid_para_diag)
        diagnostico = montar_diagnostico_para_luna(ctx)
    except Exception:
        diagnostico = None

    cliente = get_anthropic_client()
    resposta_texto, etapa_detectada = chat_com_luna(
        mensagens=historico,
        cliente=cliente,
        diagnostico=diagnostico,
    )

    salvar_mensagem_db(body.sessao_id, "user", body.mensagem)
    salvar_mensagem_db(body.sessao_id, "assistant", resposta_texto)

    etapa_atual = sessao["etapa_atual"]
    if etapa_detectada and etapa_detectada >= etapa_atual:
        etapa_atual = etapa_detectada
        atualizar_etapa_db(body.sessao_id, etapa_atual)

    return ChatResponse(
        resposta=resposta_texto,
        etapa_atual=etapa_atual,
        sessao_id=body.sessao_id,
    )


@app.get("/sessao/{sessao_id}/historico")
async def historico(
    sessao_id: str,
    user_id: str = Depends(usuario_autenticado),
):
    """Retorna o histórico completo de uma sessão."""
    sessao = buscar_sessao_db(sessao_id)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if sessao["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão.")

    mensagens = buscar_historico_db(sessao_id)
    return {
        "sessao_id": sessao_id,
        "etapa_atual": sessao["etapa_atual"],
        "ativa": sessao["ativa"],
        "mensagens": mensagens,
    }


@app.delete("/sessao/{sessao_id}")
async def encerrar_sessao(
    sessao_id: str,
    user_id: str = Depends(usuario_autenticado),
):
    """Encerra uma sessão de chat."""
    sessao = buscar_sessao_db(sessao_id)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if sessao["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado a esta sessão.")

    encerrar_sessao_db(sessao_id)
    logger.info("Sessão encerrada: %s", sessao_id)
    return {"mensagem": "Sessão encerrada com sucesso."}


@app.get("/debug/usuario/{uid}")
async def debug_usuario(
    uid: str,
    user_id: str = Depends(usuario_autenticado),
):
    """Endpoint de diagnóstico — retorna dados do Supabase para um user_id."""
    try:
        ctx = buscar_contexto_completo(uid)
        diagnostico = montar_diagnostico_para_luna(ctx)
        return {"user_id": uid, "contexto": ctx, "diagnostico_luna": diagnostico}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "versao": "2.0.0"}
