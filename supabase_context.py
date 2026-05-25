"""
Camada de dados: busca todo o contexto da usuária no Supabase para a TIAGA.
Cobre perfil, onboarding, negócio, diagnóstico, projetos de IA, ROI e aprendizado.

ATENÇÃO: verifique os nomes de coluna no Supabase caso alguma busca retorne None.
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
            raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY devem estar configurados.")
        _supabase = create_client(url, key)
    return _supabase


# ── Contexto completo da usuária ──────────────────────────────────────────────

def buscar_contexto_completo(user_id: str) -> dict:
    """
    Busca tudo que a plataforma sabe sobre a usuária:
    perfil, onboarding, negócio, fluxos, diagnóstico, oportunidades,
    projetos, ROI e progresso de aprendizado.
    """
    sb = get_supabase()
    ctx: dict = {"user_id": user_id}

    # ── Perfil principal ──────────────────────────────────────────────────────
    try:
        r = sb.table("profiles").select(
            "nome_completo, nome_preferido, email, empresa, cargo, cidade, "
            "tier_id, status_acesso, linkedin, instagram, site"
        ).eq("id", user_id).maybe_single().execute()
        if r.data:
            ctx["perfil"] = r.data
    except Exception:
        pass

    # ── Onboarding ("Quem é você") ────────────────────────────────────────────
    try:
        r = sb.table("onboarding_answers").select("*").eq(
            "user_id", user_id
        ).order("created_at", desc=True).limit(1).execute()
        if r.data:
            ctx["onboarding"] = r.data[0]
    except Exception:
        pass

    # ── Perfil do negócio ─────────────────────────────────────────────────────
    try:
        r = sb.table("business_profiles").select("*").eq(
            "user_id", user_id
        ).maybe_single().execute()
        if r.data:
            ctx["negocio"] = r.data
    except Exception:
        pass

    # ── Fluxos por departamento ───────────────────────────────────────────────
    try:
        r = sb.table("process_flows").select(
            "departamento, descricao, ferramentas, dores, status"
        ).eq("user_id", user_id).execute()
        ctx["fluxos"] = r.data or []
    except Exception:
        ctx["fluxos"] = []

    # ── Diagnóstico de IA ─────────────────────────────────────────────────────
    try:
        r = sb.table("ai_diagnostics").select(
            "payload, score_maturidade"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        if r.data:
            ctx["diagnostico"] = r.data[0]
    except Exception:
        pass

    # Fallback: diagnóstico via link público
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

    # ── Oportunidades de IA identificadas ─────────────────────────────────────
    try:
        r = sb.table("ai_opportunities").select(
            "nome, area, descricao, impacto, dificuldade, status"
        ).eq("user_id", user_id).execute()
        ctx["oportunidades"] = r.data or []
    except Exception:
        ctx["oportunidades"] = []

    # ── Projetos de IA em execução ────────────────────────────────────────────
    try:
        r = sb.table("ai_projects").select(
            "nome, area, descricao, status"
        ).eq("user_id", user_id).execute()
        ctx["projetos"] = r.data or []
    except Exception:
        ctx["projetos"] = []

    # ── ROI realizado ─────────────────────────────────────────────────────────
    try:
        r = sb.table("roi_metrics").select(
            "tipo, valor, descricao"
        ).eq("user_id", user_id).execute()
        ctx["roi"] = r.data or []
    except Exception:
        ctx["roi"] = []

    # ── Progresso de aprendizado (com títulos das aulas) ─────────────────────
    try:
        r = sb.table("lesson_progress").select(
            "lesson_id, completed, lessons(titulo, modulo_id, modules(titulo, trail_id, trails(titulo)))"
        ).eq("user_id", user_id).execute()
        ctx["progresso_aulas"] = r.data or []
    except Exception:
        # fallback sem join
        try:
            r = sb.table("lesson_progress").select("lesson_id").eq("user_id", user_id).execute()
            ctx["progresso_aulas"] = r.data or []
        except Exception:
            ctx["progresso_aulas"] = []

    # ── Trilhas disponíveis ───────────────────────────────────────────────────
    try:
        r = sb.table("trails").select("id, titulo, nivel").execute()
        ctx["trilhas"] = r.data or []
    except Exception:
        ctx["trilhas"] = []

    return ctx


def montar_diagnostico_para_luna(ctx: dict) -> dict:
    """
    Transforma o contexto bruto do Supabase em um dicionário rico
    que o agente TIAGA usa para personalizar a conversa.
    """
    perfil   = ctx.get("perfil") or {}
    onboard  = ctx.get("onboarding") or {}
    negocio  = ctx.get("negocio") or {}
    diag_raw = ctx.get("diagnostico") or {}
    payload  = diag_raw.get("payload") or {}

    # Progresso formatado
    aulas_concluidas = [
        a for a in ctx.get("progresso_aulas", [])
        if a.get("completed") or a.get("concluida")
    ]

    return {
        # Identidade
        "nome":          perfil.get("nome_preferido") or perfil.get("nome_completo"),
        "nome_empresa":  perfil.get("empresa"),
        "cargo":         perfil.get("cargo"),
        "cidade":        perfil.get("cidade"),

        # Onboarding
        "historia_pessoal":   onboard.get("historia_pessoal"),
        "historia_negocio":   onboard.get("historia_negocio"),
        "momento_atual":      onboard.get("momento_atual"),
        "principal_desafio":  onboard.get("principal_desafio"),
        "maior_objetivo":     onboard.get("maior_objetivo"),
        "consome_energia":    onboard.get("consome_energia"),
        "familiaridade_ia":   onboard.get("familiaridade_ia") or onboard.get("familiaridade_tecnologia"),
        "ferramentas_atuais": onboard.get("ferramentas_atuais"),
        "expectativas":       onboard.get("expectativas"),

        # Negócio
        "o_que_faz":         negocio.get("o_que_faz"),
        "produtos_servicos": negocio.get("produtos_servicos") or negocio.get("produtos"),
        "publico_alvo":      negocio.get("publico_alvo") or negocio.get("publico"),
        "ticket_medio":      negocio.get("ticket_medio"),
        "canais_venda":      negocio.get("canais_venda") or negocio.get("canais"),
        "tamanho_time":      negocio.get("tamanho_time") or negocio.get("time"),
        "faturamento":       negocio.get("faixa_faturamento") or negocio.get("faturamento"),
        "ferramentas_negocio": negocio.get("ferramentas_usadas") or negocio.get("ferramentas"),
        "dores_negocio":     negocio.get("dores_crescimento") or negocio.get("dores"),
        "onde_perde_tempo":  negocio.get("onde_perde_tempo"),

        # Fluxos por departamento
        "fluxos": ctx.get("fluxos") or [],

        # Diagnóstico IA
        "score_maturidade":    diag_raw.get("score_maturidade") or payload.get("score_maturidade"),
        "resumo_executivo":    payload.get("resumo_executivo"),
        "gargalos":            payload.get("gargalos"),
        "quick_wins":          payload.get("quick_wins"),
        "projetos_estrategicos": payload.get("projetos_estrategicos"),

        # Execução
        "oportunidades": ctx.get("oportunidades") or payload.get("oportunidades") or [],
        "projetos":      ctx.get("projetos") or [],
        "roi":           ctx.get("roi") or [],

        # Aprendizado
        "total_aulas_concluidas": len(aulas_concluidas),
        "aulas_concluidas":       aulas_concluidas,
        "trilhas_disponiveis":    [t.get("titulo") or t.get("title") for t in (ctx.get("trilhas") or [])],
    }


# ── Sessões de chat ───────────────────────────────────────────────────────────
# Usa as tabelas luna_chat_sessions / luna_chat_messages que já existem
# na plataforma. Colunas assumidas: id, user_id, created_at | session_id, role, content, created_at

def criar_sessao_db(user_id: str) -> str:
    sb = get_supabase()
    sessao_id = str(uuid.uuid4())
    try:
        sb.table("luna_chat_sessions").insert({
            "id": sessao_id,
            "user_id": user_id,
        }).execute()
    except Exception:
        # fallback para tabela alternativa criada na migration
        sb.table("sessoes_chat").insert({
            "id": sessao_id,
            "user_id": user_id,
            "etapa_atual": 1,
            "ativa": True,
        }).execute()
    return sessao_id


def buscar_sessao_db(sessao_id: str) -> dict | None:
    sb = get_supabase()
    for tabela in ("luna_chat_sessions", "sessoes_chat"):
        try:
            r = sb.table(tabela).select("*").eq("id", sessao_id).maybe_single().execute()
            if r.data:
                data = r.data
                # normaliza campos para interface comum
                return {
                    "id":          data.get("id"),
                    "user_id":     data.get("user_id"),
                    "etapa_atual": data.get("etapa_atual", 1),
                    "ativa":       data.get("ativa", True),
                    "_tabela":     tabela,
                }
        except Exception:
            continue
    return None


def salvar_mensagem_db(sessao_id: str, role: str, content: str) -> None:
    sb = get_supabase()
    for tabela, fk in (("luna_chat_messages", "session_id"), ("historico_chat", "sessao_id")):
        try:
            sb.table(tabela).insert({
                fk: sessao_id,
                "role": role,
                "content": content,
            }).execute()
            return
        except Exception:
            continue


def buscar_historico_db(sessao_id: str) -> list[dict]:
    sb = get_supabase()
    for tabela, fk in (("luna_chat_messages", "session_id"), ("historico_chat", "sessao_id")):
        try:
            r = sb.table(tabela).select("role, content").eq(
                fk, sessao_id
            ).order("created_at").execute()
            if r.data is not None:
                return [{"role": m["role"], "content": m["content"]} for m in r.data]
        except Exception:
            continue
    return []


def atualizar_etapa_db(sessao_id: str, etapa: int) -> None:
    sb = get_supabase()
    for tabela in ("luna_chat_sessions", "sessoes_chat"):
        try:
            sb.table(tabela).update({"etapa_atual": etapa}).eq("id", sessao_id).execute()
            return
        except Exception:
            continue


def encerrar_sessao_db(sessao_id: str) -> None:
    sb = get_supabase()
    for tabela in ("luna_chat_sessions", "sessoes_chat"):
        try:
            sb.table(tabela).update({"ativa": False}).eq("id", sessao_id).execute()
            return
        except Exception:
            continue


# ── Autenticação ──────────────────────────────────────────────────────────────

def verificar_jwt(token: str) -> str:
    """Valida o JWT do Supabase e retorna o user_id. Lança ValueError se inválido."""
    sb = get_supabase()
    try:
        result = sb.auth.get_user(token)
        if not result or not result.user:
            raise ValueError("Token inválido")
        return result.user.id
    except Exception as e:
        raise ValueError(f"Token inválido: {e}") from e
