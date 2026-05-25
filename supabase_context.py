"""
Camada de dados: busca todo o contexto da usuária no Supabase para a TIAGA.
Nomes de coluna verificados e corrigidos conforme o schema real do banco.
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
    sb = get_supabase()
    ctx: dict = {"user_id": user_id}

    # Perfil principal (profiles.id = auth.users.id)
    try:
        r = sb.table("profiles").select(
            "nome_completo, nome_preferido, empresa, cargo, cidade, "
            "email, telefone, instagram, linkedin, site, access_status, tier_id"
        ).eq("id", user_id).maybe_single().execute()
        if r.data:
            ctx["perfil"] = r.data
    except Exception:
        pass

    # Onboarding — "Quem é você"
    try:
        r = sb.table("onboarding_answers").select(
            "historia_pessoal, historia_negocio, momento_atual, "
            "principal_desafio, maior_objetivo, consome_energia, funcionar_melhor, "
            "familiaridade_tecnologia, familiaridade_ia, ferramentas_atuais, expectativas_mentoria"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        if r.data:
            ctx["onboarding"] = r.data[0]
    except Exception:
        pass

    # Perfil do negócio
    try:
        r = sb.table("business_profiles").select(
            "o_que_faz, produtos_servicos, publico_alvo, ticket_medio, "
            "canais_venda, tamanho_time, faturamento_faixa, ferramentas_usadas, "
            "dores_crescimento, areas_dependentes_fundadora, perdendo_tempo, perdendo_dinheiro"
        ).eq("user_id", user_id).maybe_single().execute()
        if r.data:
            ctx["negocio"] = r.data
    except Exception:
        pass

    # Fluxos por departamento
    try:
        r = sb.table("process_flows").select(
            "departamento, descricao, ferramentas, dores, status"
        ).eq("user_id", user_id).execute()
        ctx["fluxos"] = r.data or []
    except Exception:
        ctx["fluxos"] = []

    # Diagnóstico de IA (resumo_executivo é coluna direta)
    try:
        r = sb.table("ai_diagnostics").select(
            "payload, score_maturidade, resumo_executivo"
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
                    "resumo_executivo": None,
                }
        except Exception:
            pass

    # Oportunidades de IA (colunas corretas: impacto_esperado, dificuldade_tecnica)
    try:
        r = sb.table("ai_opportunities").select(
            "nome, area, descricao, impacto_esperado, dificuldade_tecnica, "
            "tipo_solucao, roi_estimado, status"
        ).eq("user_id", user_id).execute()
        ctx["oportunidades"] = r.data or []
    except Exception:
        ctx["oportunidades"] = []

    # Projetos de IA
    try:
        r = sb.table("ai_projects").select(
            "nome, area, descricao, status, impacto_esperado, "
            "proximos_passos, roi_esperado, roi_realizado"
        ).eq("user_id", user_id).execute()
        ctx["projetos"] = r.data or []
    except Exception:
        ctx["projetos"] = []

    # ROI realizado (colunas corretas: horas_economizadas, custo_economizado, etc.)
    try:
        r = sb.table("roi_metrics").select(
            "mes, horas_economizadas, custo_economizado, receita_potencial, notas"
        ).eq("user_id", user_id).order("mes", desc=True).execute()
        ctx["roi"] = r.data or []
    except Exception:
        ctx["roi"] = []

    # Progresso de aprendizado (completed_at: não-nulo = concluída)
    try:
        r = sb.table("lesson_progress").select(
            "lesson_id, completed_at, lessons(titulo, modules(titulo, trails(titulo)))"
        ).eq("user_id", user_id).not_.is_("completed_at", "null").execute()
        ctx["progresso_aulas"] = r.data or []
    except Exception:
        try:
            r = sb.table("lesson_progress").select(
                "lesson_id, completed_at"
            ).eq("user_id", user_id).not_.is_("completed_at", "null").execute()
            ctx["progresso_aulas"] = r.data or []
        except Exception:
            ctx["progresso_aulas"] = []

    # Trilhas disponíveis
    try:
        r = sb.table("trails").select("id, titulo, nivel").execute()
        ctx["trilhas"] = r.data or []
    except Exception:
        ctx["trilhas"] = []

    return ctx


def montar_diagnostico_para_luna(ctx: dict) -> dict:
    """Transforma o contexto bruto do Supabase no formato que a TIAGA usa."""
    perfil   = ctx.get("perfil") or {}
    onboard  = ctx.get("onboarding") or {}
    negocio  = ctx.get("negocio") or {}
    diag_raw = ctx.get("diagnostico") or {}
    payload  = diag_raw.get("payload") or {}

    aulas_concluidas = ctx.get("progresso_aulas") or []

    return {
        # Identidade
        "nome":         perfil.get("nome_preferido") or perfil.get("nome_completo"),
        "nome_empresa": perfil.get("empresa"),
        "cargo":        perfil.get("cargo"),
        "cidade":       perfil.get("cidade"),

        # Onboarding
        "historia_pessoal":   onboard.get("historia_pessoal"),
        "historia_negocio":   onboard.get("historia_negocio"),
        "momento_atual":      onboard.get("momento_atual"),
        "principal_desafio":  onboard.get("principal_desafio"),
        "maior_objetivo":     onboard.get("maior_objetivo"),
        "consome_energia":    onboard.get("consome_energia"),
        "funcionar_melhor":   onboard.get("funcionar_melhor"),
        "familiaridade_ia":   onboard.get("familiaridade_ia") or onboard.get("familiaridade_tecnologia"),
        "ferramentas_atuais": onboard.get("ferramentas_atuais"),
        "expectativas":       onboard.get("expectativas_mentoria"),

        # Negócio
        "o_que_faz":          negocio.get("o_que_faz"),
        "produtos_servicos":  negocio.get("produtos_servicos"),
        "publico_alvo":       negocio.get("publico_alvo"),
        "ticket_medio":       negocio.get("ticket_medio"),
        "canais_venda":       negocio.get("canais_venda"),
        "tamanho_time":       negocio.get("tamanho_time"),
        "faturamento":        negocio.get("faturamento_faixa"),
        "ferramentas_negocio": negocio.get("ferramentas_usadas"),
        "dores_negocio":      negocio.get("dores_crescimento"),
        "areas_dependentes":  negocio.get("areas_dependentes_fundadora"),
        "perdendo_tempo":     negocio.get("perdendo_tempo"),
        "perdendo_dinheiro":  negocio.get("perdendo_dinheiro"),

        # Fluxos
        "fluxos": ctx.get("fluxos") or [],

        # Diagnóstico
        "score_maturidade":      diag_raw.get("score_maturidade") or payload.get("score_maturidade"),
        "resumo_executivo":      diag_raw.get("resumo_executivo") or payload.get("resumo_executivo"),
        "gargalos":              payload.get("gargalos"),
        "quick_wins":            payload.get("quick_wins"),
        "projetos_estrategicos": payload.get("projetos_estrategicos"),

        # Execução
        "oportunidades": ctx.get("oportunidades") or payload.get("oportunidades") or [],
        "projetos":      ctx.get("projetos") or [],
        "roi":           ctx.get("roi") or [],

        # Aprendizado
        "total_aulas_concluidas": len(aulas_concluidas),
        "aulas_concluidas":       aulas_concluidas,
        "trilhas_disponiveis":    [t.get("titulo") for t in (ctx.get("trilhas") or []) if t.get("titulo")],
    }


# ── Sessões de chat ───────────────────────────────────────────────────────────
# Usa luna_chat_sessions + luna_chat_messages (tabelas nativas da plataforma).
# sessoes_chat é usado como tabela auxiliar para etapa_atual e status ativa.

def criar_sessao_db(user_id: str) -> str:
    sb = get_supabase()

    # Cria na tabela nativa da plataforma
    r = sb.table("luna_chat_sessions").insert({
        "user_id": user_id,
        "title": "Conversa com TIAGA",
    }).execute()
    sessao_id = r.data[0]["id"]

    # Cria na tabela auxiliar para rastrear etapa e status
    try:
        sb.table("sessoes_chat").insert({
            "id": str(sessao_id),
            "user_id": user_id,
            "etapa_atual": 1,
            "ativa": True,
        }).execute()
    except Exception:
        pass

    return str(sessao_id)


def buscar_sessao_db(sessao_id: str) -> dict | None:
    sb = get_supabase()
    try:
        r = sb.table("luna_chat_sessions").select(
            "id, user_id"
        ).eq("id", sessao_id).maybe_single().execute()
        if not r.data:
            return None

        # Busca metadados adicionais na tabela auxiliar
        etapa, ativa = 1, True
        try:
            aux = sb.table("sessoes_chat").select(
                "etapa_atual, ativa"
            ).eq("id", sessao_id).maybe_single().execute()
            if aux.data:
                etapa = aux.data.get("etapa_atual", 1)
                ativa = aux.data.get("ativa", True)
        except Exception:
            pass

        return {
            "id":          r.data["id"],
            "user_id":     r.data["user_id"],
            "etapa_atual": etapa,
            "ativa":       ativa,
        }
    except Exception:
        return None


def salvar_mensagem_db(sessao_id: str, role: str, content: str, user_id: str | None = None) -> None:
    sb = get_supabase()
    data: dict = {"session_id": sessao_id, "role": role, "content": content}
    if user_id:
        data["user_id"] = user_id
    try:
        sb.table("luna_chat_messages").insert(data).execute()
    except Exception:
        # fallback para tabela auxiliar
        try:
            sb.table("historico_chat").insert({
                "sessao_id": sessao_id, "role": role, "content": content
            }).execute()
        except Exception:
            pass


def buscar_historico_db(sessao_id: str) -> list[dict]:
    sb = get_supabase()
    try:
        r = sb.table("luna_chat_messages").select(
            "role, content"
        ).eq("session_id", sessao_id).order("created_at").execute()
        if r.data is not None:
            return [{"role": m["role"], "content": m["content"]} for m in r.data]
    except Exception:
        pass
    try:
        r = sb.table("historico_chat").select(
            "role, content"
        ).eq("sessao_id", sessao_id).order("created_at").execute()
        if r.data is not None:
            return [{"role": m["role"], "content": m["content"]} for m in r.data]
    except Exception:
        pass
    return []


def atualizar_etapa_db(sessao_id: str, etapa: int) -> None:
    sb = get_supabase()
    try:
        sb.table("sessoes_chat").update(
            {"etapa_atual": etapa}
        ).eq("id", sessao_id).execute()
    except Exception:
        pass


def encerrar_sessao_db(sessao_id: str) -> None:
    sb = get_supabase()
    try:
        sb.table("sessoes_chat").update(
            {"ativa": False}
        ).eq("id", sessao_id).execute()
    except Exception:
        pass


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
