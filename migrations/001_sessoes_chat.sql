-- Migration 001: tabelas para sessões e histórico de chat persistidos
-- Execute no SQL Editor do Supabase (painel > SQL Editor > New query)

-- ── Tabela de sessões ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessoes_chat (
    id          TEXT        PRIMARY KEY,
    user_id     UUID        NOT NULL,
    etapa_atual INTEGER     NOT NULL DEFAULT 1 CHECK (etapa_atual BETWEEN 1 AND 5),
    ativa       BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Tabela de histórico de mensagens ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historico_chat (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sessao_id  TEXT        NOT NULL REFERENCES sessoes_chat(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Índices ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sessoes_user_id   ON sessoes_chat(user_id);
CREATE INDEX IF NOT EXISTS idx_sessoes_ativa      ON sessoes_chat(ativa);
CREATE INDEX IF NOT EXISTS idx_historico_sessao   ON historico_chat(sessao_id, created_at);

-- ── Trigger: atualiza updated_at automaticamente ──────────────────────────────
CREATE OR REPLACE FUNCTION atualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sessoes_updated_at ON sessoes_chat;
CREATE TRIGGER trg_sessoes_updated_at
    BEFORE UPDATE ON sessoes_chat
    FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();

-- ── Row Level Security ────────────────────────────────────────────────────────
-- O backend usa a SERVICE KEY que bypassa RLS.
-- RLS fica ativo para bloquear acesso direto via anon/authenticated key.
ALTER TABLE sessoes_chat  ENABLE ROW LEVEL SECURITY;
ALTER TABLE historico_chat ENABLE ROW LEVEL SECURITY;

-- Usuária autenticada vê apenas as próprias sessões (acesso via SDK cliente, se necessário)
CREATE POLICY IF NOT EXISTS "usuario_ve_proprias_sessoes"
    ON sessoes_chat FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY IF NOT EXISTS "usuario_ve_proprio_historico"
    ON historico_chat FOR SELECT
    USING (
        sessao_id IN (
            SELECT id FROM sessoes_chat WHERE user_id = auth.uid()
        )
    );
