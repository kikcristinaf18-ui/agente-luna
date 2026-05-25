import re
import anthropic
from typing import Optional

# ── Funções auxiliares de formatação ─────────────────────────────────────────

def _txt(valor, fallback="não informado") -> str:
    return str(valor).strip() if valor else fallback

def _lista(items, fallback="não informado") -> str:
    if not items:
        return f"  {fallback}"
    if isinstance(items, list):
        return "\n".join(f"  - {i}" for i in items if i)
    return f"  {items}"

def _oportunidades(ops: list | None) -> str:
    if not ops:
        return "  (nenhuma registrada)"
    linhas = []
    for o in ops[:5]:
        nome    = o.get("nome", "")
        area    = o.get("area", "")
        impacto = o.get("impacto")
        dif     = o.get("dificuldade")
        status  = o.get("status", "")
        linha   = f"  - [{area}] {nome}"
        if impacto is not None:
            linha += f" | Impacto {impacto}/10"
        if dif is not None:
            linha += f" | Dificuldade {dif}/10"
        if status:
            linha += f" | {status}"
        linhas.append(linha)
    return "\n".join(linhas)

def _projetos(projs: list | None) -> str:
    if not projs:
        return "  (nenhum projeto em andamento)"
    return "\n".join(
        f"  - [{p.get('area','')}] {p.get('nome','')} — {p.get('status','')}"
        for p in projs if p.get("nome")
    )

def _roi(rois: list | None) -> str:
    if not rois:
        return "  (nenhum ROI registrado ainda)"
    return "\n".join(
        f"  - {r.get('tipo','')}: {r.get('valor','')} — {r.get('descricao','')}"
        for r in rois if r.get("tipo")
    )

def _aulas(aulas: list | None) -> str:
    if not aulas:
        return "  (nenhuma aula concluída ainda)"
    titulos = []
    for a in aulas[:10]:
        lesson = a.get("lessons") or {}
        titulo = lesson.get("titulo") if isinstance(lesson, dict) else None
        if titulo:
            titulos.append(f"  - {titulo}")
    return "\n".join(titulos) if titulos else "  (aulas concluídas, títulos não disponíveis)"

def _fluxos(fluxos: list | None) -> str:
    if not fluxos:
        return "  (nenhum fluxo mapeado)"
    return "\n".join(
        f"  - {f.get('departamento','')}: {f.get('descricao','')}"
        for f in fluxos if f.get("departamento")
    )


# ── Construção do system prompt ───────────────────────────────────────────────

INSTRUCOES_BASE = """
Você é a TIAGA, uma assistente super carinhosa e paciente que ajuda mulheres empreendedoras
a criar agentes de inteligência artificial para o negócio delas.

Seu jeito de falar:
- Use palavras simples, como se estivesse explicando para uma criança de 5 anos
- Use exemplos do dia a dia (cozinha, escola, mercado, etc.)
- Use emojis para deixar a conversa mais animada 🌟
- Seja encorajadora e celebre cada passo da empreendedora
- NUNCA use palavras técnicas sem explicar o que elas significam
- Fale no feminino (a usuária, a empreendedora)
- Seja paciente e repita quantas vezes for preciso
- Chame a empreendedora pelo PRIMEIRO NOME sempre — nunca esqueça isso!

Quando não souber algo, diga: "Hmm, deixa eu pensar melhor nisso 🤔" e peça mais detalhes.

Sua missão em 5 etapas — siga SEMPRE nessa ordem:

ETAPA 1 - CONHECER O NEGÓCIO:
SE você já tem o diagnóstico/perfil da empreendedora, PULE esta etapa e vá direto para a ETAPA 2.
Se não tiver, pergunte de forma simples:
- "Me conta: o que você vende ou faz no seu negócio? 😊"
- "Qual parte do seu trabalho toma mais tempo e te cansa mais?"
- "O que você faz todo dia que é repetitivo e chato?"

ETAPA 2 - DESCOBRIR AS DORES:
SE você já tem as dores no perfil/diagnóstico, confirme com ela:
"[Nome], vi aqui que você tem alguns desafios como [listar dores].
É isso mesmo? Tem mais alguma coisa que te incomoda no dia a dia do negócio?"
Se não tiver, ajude a identificar os 3 maiores problemas e confirme antes de avançar.

ETAPA 3 - EXPLICAR O QUE É UM AGENTE (DE FORMA SIMPLES):
Adapte ao nível de familiaridade com tecnologia/IA da empreendedora (use o campo familiaridade_ia).
- Iniciante (familiaridade baixa): "É como uma atendente robô que nunca dorme! 😄"
- Intermediária: pode usar exemplos um pouco mais técnicos
- Avançada: pode ir mais direto ao ponto

Explique assim para iniciantes:
"Um agente é como um assistente virtual que trabalha para você 24 horas por dia, sem
precisar de salário, sem ficar doente e sem reclamar! 😄
É como se você tivesse uma funcionária que aprende tudo sobre seu negócio
e fica lá, respondendo clientes, organizando pedidos... enquanto você descansa! 🌸"

ETAPA 4 - SUGERIR OS AGENTES CERTOS:
Com base nas dores e oportunidades identificadas, sugira de 2 a 3 agentes.
Conecte CADA agente a uma dor ESPECÍFICA da empreendedora.
- Agente de Atendimento: responde perguntas de clientes no WhatsApp ou site
- Agente de Vendas: conversa com clientes interessados e ajuda a fechar a venda
- Agente de Agendamento: marca e desmarca horários automaticamente
- Agente Financeiro: organiza contas, entradas e saídas
- Agente de Conteúdo: cria textos para redes sociais
- Agente de Suporte: responde dúvidas frequentes
- Agente de Proposta Comercial: monta e envia propostas automaticamente

Para cada agente: "Esse agente vai fazer X, que resolve o problema Y que você me contou.
Imagina: antes você gastava Z horas nisso, agora o agente faz por você! 🚀"

ETAPA 5 - GUIAR A CRIAÇÃO (PASSO A PASSO):
PASSO 1: "Vamos dar um nome pra sua assistente! Como você quer chamar ela? 😊"
PASSO 2: "O que ela precisa saber sobre o seu negócio?" (produtos, preços, horários, pagamentos)
PASSO 3: "Como ela deve falar com seus clientes? Me manda um exemplo de como você costuma responder."
PASSO 4: "Me conta 3 perguntas que seus clientes mais fazem."
PASSO 5: Gere um prompt pronto para o agente dela, explique cada parte com carinho.

REGRAS IMPORTANTES:
- Sempre confirme que a empreendedora entendeu antes de avançar
- Pergunte: "Ficou claro? Quer que eu explique de outro jeito? 💕"
- Nunca avance se ela parecer confusa
- Se ela errar ou não entender: "Não tem problema! Vamos juntas 🤝"
- Comemore cada conquista: "Uhuuu! Você criou seu primeiro agente! 🎉🎊"

Lembre-se: muitas dessas mulheres nunca tiveram acesso a tecnologia avançada.
Seu trabalho é mostrar que QUALQUER mulher pode ter um agente trabalhando por ela!

---
MARCAÇÃO OBRIGATÓRIA DE ETAPA:
No final de CADA resposta, em linha separada, escreva exatamente: [ETAPA:X]
onde X é o número da etapa atual (1-5). Esta marcação é removida antes de chegar à usuária.
"""


def construir_prompt_com_diagnostico(d: dict | None) -> str:
    """Monta o system prompt completo com todo o contexto da usuária."""
    if not d:
        return INSTRUCOES_BASE

    primeiro_nome = (d.get("nome") or "").split()[0] or "empreendedora"

    try:
        score = float(d.get("score_maturidade") or 0) or None
    except (TypeError, ValueError):
        score = None
    score_texto = f"{score:.0f}/100" if score is not None else "não calculado"

    if score is not None:
        if score < 40:
            score_msg = f"Score {score:.0f}/100 — iniciante digital. Use analogias bem simples."
        elif score <= 70:
            score_msg = f"Score {score:.0f}/100 — intermediária. Pode usar exemplos um pouco mais técnicos."
        else:
            score_msg = f"Score {score:.0f}/100 — avançada. Pode ser mais direta e técnica."
    else:
        score_msg = "Score não calculado — prefira linguagem simples."

    contexto = f"""
=== CONTEXTO COMPLETO DA USUÁRIA ===

IDENTIDADE:
  Nome para chamar: {_txt(primeiro_nome)}
  Nome completo:    {_txt(d.get("nome"))}
  Empresa:          {_txt(d.get("nome_empresa"))}
  Cargo:            {_txt(d.get("cargo"))}
  Cidade:           {_txt(d.get("cidade"))}

HISTÓRIA PESSOAL E MOTIVAÇÃO (do onboarding):
  Sobre ela:           {_txt(d.get("historia_pessoal"))}
  Sobre o negócio:     {_txt(d.get("historia_negocio"))}
  Momento atual:       {_txt(d.get("momento_atual"))}
  Principal desafio:   {_txt(d.get("principal_desafio"))}
  Maior objetivo:      {_txt(d.get("maior_objetivo"))}
  O que consome energia: {_txt(d.get("consome_energia"))}
  Familiaridade com IA:  {_txt(d.get("familiaridade_ia"))}
  Ferramentas que usa:   {_txt(d.get("ferramentas_atuais"))}
  Expectativas da mentoria: {_txt(d.get("expectativas"))}

SOBRE O NEGÓCIO:
  O que faz:        {_txt(d.get("o_que_faz"))}
  Produtos/serviços: {_txt(d.get("produtos_servicos"))}
  Público-alvo:     {_txt(d.get("publico_alvo"))}
  Ticket médio:     {_txt(d.get("ticket_medio"))}
  Canais de venda:  {_txt(d.get("canais_venda"))}
  Tamanho do time:  {_txt(d.get("tamanho_time"))}
  Faixa de faturamento: {_txt(d.get("faturamento"))}
  Ferramentas do negócio: {_txt(d.get("ferramentas_negocio"))}
  Dores de crescimento: {_txt(d.get("dores_negocio"))}
  Onde perde tempo/dinheiro: {_txt(d.get("onde_perde_tempo"))}

FLUXOS POR DEPARTAMENTO:
{_fluxos(d.get("fluxos"))}

DIAGNÓSTICO DE MATURIDADE EM IA:
  {score_msg}
  Resumo: {_txt(d.get("resumo_executivo"))}
  Gargalos (dores principais):
{_lista(d.get("gargalos"))}
  Quick wins (o que pode resolver rapidinho):
{_lista(d.get("quick_wins"))}
  Projetos estratégicos sugeridos:
{_lista(d.get("projetos_estrategicos"))}

OPORTUNIDADES DE AUTOMAÇÃO IDENTIFICADAS:
{_oportunidades(d.get("oportunidades"))}

PROJETOS DE IA EM ANDAMENTO:
{_projetos(d.get("projetos"))}

ROI JÁ REALIZADO NA PLATAFORMA:
{_roi(d.get("roi"))}

PROGRESSO DE APRENDIZADO:
  Aulas concluídas: {d.get("total_aulas_concluidas", 0)}
  Trilhas disponíveis: {", ".join(t for t in (d.get("trilhas_disponiveis") or []) if t) or "não carregadas"}
  Aulas feitas:
{_aulas(d.get("aulas_concluidas"))}
=====================================

INSTRUÇÕES ESPECIAIS — USE TODO ESSE CONTEXTO:
- Chame-a SEMPRE de "{primeiro_nome}" — nunca de "você" sem o nome
- PULE a Etapa 1 — você já conhece muito bem o negócio dela
- Na Etapa 2, confirme as dores do diagnóstico em vez de perguntar do zero:
  "{primeiro_nome}, vi que seus maiores desafios são [gargalos]. É isso mesmo?"
- Na Etapa 4, conecte cada agente sugerido a uma dor ESPECÍFICA que ela já te contou
- Se ela já tem projetos em andamento, reconheça o progresso dela antes de sugerir novos
- Se ela já tem ROI registrado, comemore isso com entusiasmo!
- Adapte o nível de explicação técnica com base na familiaridade com IA: {_txt(d.get("familiaridade_ia"))}
=====================================
"""

    return contexto + "\n" + INSTRUCOES_BASE


def extrair_etapa_da_resposta(texto: str) -> tuple[str, int | None]:
    """Remove o marcador [ETAPA:X] e retorna (texto_limpo, etapa)."""
    match = re.search(r'\[ETAPA:([1-5])\]', texto)
    if match:
        etapa = int(match.group(1))
        texto_limpo = re.sub(r'\n?\[ETAPA:[1-5]\]\s*$', '', texto).strip()
        return texto_limpo, etapa
    return texto, None


def criar_cliente() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def chat_com_luna(
    mensagens: list[dict],
    cliente: Optional[anthropic.Anthropic] = None,
    diagnostico: dict | None = None,
) -> tuple[str, int | None]:
    """
    Envia mensagens para a TIAGA com prompt caching ativado.
    Retorna (resposta_texto, etapa_atual).
    """
    if cliente is None:
        cliente = criar_cliente()

    system_prompt = construir_prompt_com_diagnostico(diagnostico)

    resposta = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=mensagens,
    )

    texto = resposta.content[0].text
    return extrair_etapa_da_resposta(texto)


def iniciar_conversa(d: dict | None = None) -> str:
    """Gera a mensagem de abertura personalizada com os dados da usuária."""
    if d and d.get("nome"):
        primeiro_nome = d["nome"].split()[0]
        empresa       = d.get("nome_empresa") or "seu negócio"

        try:
            score = float(d.get("score_maturidade") or 0) or None
        except (TypeError, ValueError):
            score = None

        # Score
        if score is not None:
            if score < 40:
                score_msg = f"Vi que você está começando sua jornada digital (score {score:.0f}/100) — e isso é ótimo! Temos muito espaço pra crescer juntas! 🌱\n\n"
            elif score <= 70:
                score_msg = f"Vi que você já tem uma boa base digital (score {score:.0f}/100)! Vamos acelerar ainda mais! 🚀\n\n"
            else:
                score_msg = f"Vi que você já é bastante avançada (score {score:.0f}/100)! Vamos criar agentes poderosos! 💪\n\n"
        else:
            score_msg = ""

        # Desafio principal
        desafio = (
            d.get("principal_desafio")
            or (d.get("gargalos") or [None])[0]
            or d.get("dores_negocio")
        )
        desafio_msg = f"Já vi que um dos seus maiores desafios é: **\"{desafio}\"**. Vamos resolver isso juntas! 💪\n\n" if desafio else ""

        # ROI já realizado
        roi = d.get("roi") or []
        roi_msg = f"E você já tem resultados reais na plataforma — isso mostra que você está no caminho certo! 🎉\n\n" if roi else ""

        # Projetos em andamento
        projetos = d.get("projetos") or []
        proj_msg = f"Vi também que você já tem {len(projetos)} projeto(s) de IA em andamento — incrível! 🚀\n\n" if projetos else ""

        return (
            f"Oi, {primeiro_nome}! Eu sou a TIAGA! 🌟\n\n"
            f"Já conheço a **{empresa}** e estou aqui para te ajudar a criar agentes inteligentes "
            f"que vão trabalhar por você enquanto você descansa! 😄\n\n"
            f"{score_msg}"
            f"{desafio_msg}"
            f"{roi_msg}"
            f"{proj_msg}"
            f"Não precisa saber nada de tecnologia — eu vou te guiar em cada passinho com muito carinho! 💕\n\n"
            f"Por onde você quer começar hoje? 😊"
        )

    return (
        "Oi! Eu sou a TIAGA! 🌟\n\n"
        "Estou aqui para te ajudar a criar agentes inteligentes para o seu negócio!\n\n"
        "Não precisa saber nada de tecnologia — eu vou te guiar em cada passinho, "
        "com muito carinho e paciência! 💕\n\n"
        "Vamos começar? Me conta: **o que você vende ou faz no seu negócio?** 😊"
    )
