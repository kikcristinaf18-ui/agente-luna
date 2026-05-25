"""
Gerencia conexão com Supabase: perfil de usuária, diagnóstico,
progresso em aulas e sessões de chat persistidas.
"""

import os
import uuid
from supabase import create_client, Client

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar configurados."
            )
        _supabase = create_client(url, key)
    return _supabase


# ── Perfil e diagnóstico ──────────────────────────────────────────────────────

def buscar_contexto_completo(user_id: str) -> dict:
    """
    Busca perfil, diagnóstico, trilhas e progresso de aulas da empreendedora.
    Retorna dict pronto para passar a montar_diagnostico_para_luna().
    """
    sb = get_supabase()
    ctx: dict = {"user_id": user_id}

    try:
        r = sb.table("profiles").select(
            "nome_completo, nome_preferido, empresa"
        ).eq("id", user_id).maybe_single().execute()
        if r.data:
            ctx["perfil"] = r.data
    except Exception:
        pass

    try:
        r = sb.table("ai_diagnostics").select(
            "payload, score_maturidade"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        if r.data:
            ctx["diagnostico"] = r.data[0]
    except Exception:
        pass

    if "diagnostico" not in ctx:
        try:
            r = sb.table("invite_respondents").select(
                "diagnostic_payload, diagnostic_score"
            ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
            if r.data:
                d = r.data[0]
                ctx["diagnostico"] = {
                    "payload": d.get("diagnostic_payload"),
                    "score_maturidade": d.get("diagnostic_score"),
                }
        except Exception:
            pass

    try:
        r = sb.table("lesson_progress").select(
            "lesson_id"
        ).eq("user_id", user_id).execute()
        ctx["aulas_concluidas"] = [row["lesson_id"] for row in (r.data or [])]
    except Exception:
        ctx["aulas_concluidas"] = []

    try:
        r = sb.table("trails").select("id, title, slug, level").execute()
        ctx["trilhas"] = r.data or []
    except Exception:
        ctx["trilhas"] = []

    return ctx


def montar_diagnostico_para_luna(ctx: dict) -> dict | None:
    """Transforma o contexto completo no formato que a TIAGA entende."""
    perfil = ctx.get("perfil") or {}
    diag_raw = ctx.get("diagnostico") or {}
    payload = diag_raw.get("payload") or {}

    if not perfil and not payload:
        return None

    return {
        "nome": perfil.get("nome_preferido") or perfil.get("nome_completo"),
        "nome_empresa": perfil.get("empresa"),
        "resumo_executivo": payload.get("resumo_executivo"),
        "score_maturidade": diag_raw.get("score_maturidade") or payload.get("score_maturidade"),
        "gargalos": payload.get("gargalos"),
        "quick_wins": payload.get("quick_wins"),
        "projetos_estrategicos": payload.get("projetos_estrategicos"),
        "projetos_avancados": payload.get("projetos_avancados"),
        "oportunidades": payload.get("oportunidades"),
        "recomendacoes": payload.get("recomendacoes"),
        "total_aulas_concluidas": len(ctx.get("aulas_concluidas") or []),
        "trilhas_disponiveis": [t.get("title") for t in (ctx.get("trilhas") or [])],
    }


# ── Sessões de chat persistidas ───────────────────────────────────────────────

def criar_sessao_db(user_id: str) -> str:
    """Cria uma nova sessão no banco e retorna o ID gerado."""
    sb = get_supabase()
    sessao_id = str(uuid.uuid4())
    sb.table("sessoes_chat").insert({
        "id": sessao_id,
        "user_id": user_id,
        "etapa_atual": 1,
        "ativa": True,
    }).execute()
    return sessao_id


def buscar_sessao_db(sessao_id: str) -> dict | None:
    """Retorna dados da sessão ou None se não existir."""
    sb = get_supabase()
    try:
        r = sb.table("sessoes_chat").select(
            "id, user_id, etapa_atual, ativa"
        ).eq("id", sessao_id).maybe_single().execute()
        return r.data
    except Exception:
        return None


def salvar_mensagem_db(sessao_id: str, role: str, content: str) -> None:
    """Persiste uma mensagem (user ou assistant) no histórico."""
    sb = get_supabase()
    sb.table("historico_chat").insert({
        "sessao_id": sessao_id,
        "role": role,
        "content": content,
    }).execute()


def buscar_historico_db(sessao_id: str) -> list[dict]:
    """Retorna todas as mensagens da sessão em ordem cronológica."""
    sb = get_supabase()
    try:
        r = sb.table("historico_chat").select(
            "role, content"
        ).eq("sessao_id", sessao_id).order("created_at").execute()
        return [{"role": m["role"], "content": m["content"]} for m in (r.data or [])]
    except Exception:
        return []


def atualizar_etapa_db(sessao_id: str, etapa: int) -> None:
    """Atualiza a etapa atual da sessão (1-5)."""
    sb = get_supabase()
    sb.table("sessoes_chat").update({
        "etapa_atual": etapa,
        "updated_at": "now()",
    }).eq("id", sessao_id).execute()


def encerrar_sessao_db(sessao_id: str) -> None:
    """Marca a sessão como encerrada."""
    sb = get_supabase()
    sb.table("sessoes_chat").update({
        "ativa": False,
        "updated_at": "now()",
    }).eq("id", sessao_id).execute()


# ── Autenticação ──────────────────────────────────────────────────────────────

def verificar_jwt(token: str) -> str:
    """
    Valida o JWT do Supabase e retorna o user_id.
    Lança ValueError se o token for inválido ou expirado.
    """
    sb = get_supabase()
    try:
        result = sb.auth.get_user(token)
        if not result or not result.user:
            raise ValueError("Token inválido")
        return result.user.id
    except Exception as e:
        raise ValueError(f"Token inválido: {e}") from e
