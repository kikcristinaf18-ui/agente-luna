"""
Busca todos os dados da empreendedora no Supabase para dar contexto completo à Luna.
"""

import os
from supabase import create_client, Client

_supabase: Client | None = None


def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar configurados no Railway."
            )
        _supabase = create_client(url, key)
    return _supabase


def buscar_contexto_completo(user_id: str) -> dict:
    """
    Busca tudo sobre a empreendedora no Supabase:
    perfil, diagnóstico, trilhas em progresso, aulas concluídas.
    Retorna um dict pronto para passar à Luna.
    """
    sb = get_supabase()
    ctx: dict = {"user_id": user_id}

    # ── Perfil ────────────────────────────────────────────────────────────────
    try:
        r = sb.table("profiles").select(
            "nome_completo, nome_preferido, empresa"
        ).eq("id", user_id).maybe_single().execute()
        if r.data:
            ctx["perfil"] = r.data
    except Exception:
        pass

    # ── Diagnóstico (ai_diagnostics) ──────────────────────────────────────────
    try:
        r = sb.table("ai_diagnostics").select(
            "payload, score_maturidade"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        if r.data:
            ctx["diagnostico"] = r.data[0]
    except Exception:
        pass

    # ── Diagnóstico por convite (invite_respondents) ──────────────────────────
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

    # ── Progresso nas trilhas ─────────────────────────────────────────────────
    try:
        r = sb.table("lesson_progress").select(
            "lesson_id"
        ).eq("user_id", user_id).execute()
        ctx["aulas_concluidas"] = [row["lesson_id"] for row in (r.data or [])]
    except Exception:
        ctx["aulas_concluidas"] = []

    # ── Trilhas disponíveis ───────────────────────────────────────────────────
    try:
        r = sb.table("trails").select("id, title, slug, level").execute()
        ctx["trilhas"] = r.data or []
    except Exception:
        ctx["trilhas"] = []

    return ctx


def montar_diagnostico_para_luna(ctx: dict) -> dict | None:
    """Transforma o contexto completo no formato que a Luna entende."""
    perfil = ctx.get("perfil") or {}
    diag_raw = ctx.get("diagnostico") or {}
    payload = diag_raw.get("payload") or {}

    # Sem nenhum dado, retorna None
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
        # Contexto extra de aprendizado
        "total_aulas_concluidas": len(ctx.get("aulas_concluidas") or []),
        "trilhas_disponiveis": [t.get("title") for t in (ctx.get("trilhas") or [])],
    }
