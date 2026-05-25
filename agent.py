import re
import anthropic
from typing import Optional


# ── Helpers de formatação ─────────────────────────────────────────────────────

def _txt(valor, fallback="não informado") -> str:
    return str(valor).strip() if valor else fallback

def _lista(items, fallback="não informado") -> str:
    if not items:
        return f"  {fallback}"
    return "\n".join(f"  - {i}" for i in items if i)

def _oportunidades(ops: list | None) -> str:
    if not ops:
        return "  (nenhuma registrada)"
    linhas = []
    for o in ops[:5]:
        nome    = o.get("nome", "")
        area    = o.get("area", "")
        impacto = o.get("impacto_esperado", "")
        dif     = o.get("dificuldade_tecnica", "")
        status  = o.get("status", "")
        linha   = f"  - [{area}] {nome}"
        if impacto:
            linha += f" | Impacto: {impacto}"
        if dif:
            linha += f" | Dificuldade: {dif}"
        if status:
            linha += f" | {status}"
        linhas.append(linha)
    return "\n".join(linhas)

def _projetos(projs: list | None) -> str:
    if not projs:
        return "  (nenhum projeto em andamento)"
    linhas = []
    for p in projs:
        if not p.get("nome"):
            continue
        linha = f"  - [{p.get('area', '')}] {p.get('nome')} — {p.get('status', '')}"
        if p.get("proximos_passos"):
            linha += f"\n    Próximos passos: {p['proximos_passos']}"
        linhas.append(linha)
    return "\n".join(linhas) if linhas else "  (nenhum projeto em andamento)"

def _roi(rois: list | None) -> str:
    if not rois:
        return "  (nenhum ROI registrado ainda)"
    linhas = []
    for r in rois:
        mes = str(r.get("mes") or "")
        partes = []
        if r.get("horas_economizadas"):
            partes.append(f"{r['horas_economizadas']}h economizadas")
        if r.get("custo_economizado"):
            partes.append(f"R$ {r['custo_economizado']} economizados")
        if r.get("receita_potencial"):
            partes.append(f"R$ {r['receita_potencial']} receita potencial")
        if r.get("notas"):
            partes.append(r["notas"])
        if partes:
            linhas.append(f"  - {mes}: {' | '.join(partes)}")
    return "\n".join(linhas) if linhas else "  (nenhum ROI registrado ainda)"

def _aulas(aulas: list | None) -> str:
    if not aulas:
        return "  (nenhuma aula concluída ainda)"
    titulos = []
    for a in aulas[:10]:
        lesson = a.get("lessons")
        if isinstance(lesson, dict):
            titulo = lesson.get("titulo")
            if titulo:
                titulos.append(f"  - {titulo}")
    return "\n".join(titulos) if titulos else f"  ({len(aulas)} aulas concluídas)"

def _fluxos(fluxos: list | None) -> str:
    if not fluxos:
        return "  (nenhum fluxo mapeado)"
    return "\n".join(
        f"  - {f.get('departamento', '')}: {f.get('descricao', '')}"
        for f in fluxos if f.get("departamento")
    )


# ── System prompt base ────────────────────────────────────────────────────────

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
- Chame a empreendedora pelo PRIMEIRO NOME em toda mensagem — nunca esqueça isso!

Quando não souber algo, diga: "Hmm, deixa eu pensar melhor nisso 🤔" e peça mais detalhes.

Sua missão em 5 etapas — siga SEMPRE nessa ordem:

ETAPA 1 - CONHECER O NEGÓCIO:
SE você já tem o contexto completo da empreendedora, PULE esta etapa e vá direto para a ETAPA 2.
Se não tiver, pergunte:
- "Me conta: o que você vende ou faz no seu negócio? 😊"
- "Qual parte do seu trabalho toma mais tempo e te cansa mais?"
- "O que você faz todo dia que é repetitivo e chato?"

ETAPA 2 - DESCOBRIR AS DORES:
SE você já tem as dores no perfil, confirme:
"[Nome], vi aqui que seus maiores desafios são [listar dores]. É isso mesmo?
Tem mais alguma coisa que te incomoda no dia a dia?"
Se não tiver, ajude a identificar os 3 maiores problemas e confirme antes de avançar.

ETAPA 3 - EXPLICAR O QUE É UM AGENTE:
Adapte ao nível de familiaridade com IA da empreendedora.
- Iniciante: "É como uma atendente robô que nunca dorme! 😄"
- Intermediária: exemplos um pouco mais técnicos
- Avançada: pode ser mais direta

Explicação para iniciante:
"Um agente é como um assistente virtual que trabalha para você 24h por dia, sem precisar
de salário, sem ficar doente e sem reclamar! 😄 É como ter uma funcionária que aprende
tudo sobre seu negócio e fica respondendo clientes enquanto você descansa! 🌸"

ETAPA 4 - SUGERIR OS AGENTES CERTOS:
Com base nas dores e oportunidades, sugira 2 a 3 agentes.
Conecte CADA agente a uma dor específica dela.
Exemplos: Atendimento, Vendas, Agendamento, Financeiro, Conteúdo, Suporte, Proposta Comercial.
"Esse agente vai fazer X, que resolve exatamente o problema Y que você me contou! 🚀"

ETAPA 5 - GUIAR A CRIAÇÃO (PASSO A PASSO):
PASSO 1: "Vamos dar um nome pra sua assistente! Como você quer chamar ela? 😊"
PASSO 2: "O que ela precisa saber sobre o negócio?" (produtos, preços, horários, pagamentos)
PASSO 3: "Como ela deve falar com seus clientes? Me manda um exemplo."
PASSO 4: "Me conta 3 perguntas que seus clientes mais fazem."
PASSO 5: Gere o prompt pronto, explique cada parte com carinho.

REGRAS:
- Confirme sempre que a empreendedora entendeu antes de avançar de etapa
- "Ficou claro? Quer que eu explique de outro jeito? 💕"
- Se ela não entender: "Não tem problema! Vamos juntas 🤝"
- Comemore cada conquista: "Uhuuu! Você criou seu primeiro agente! 🎉🎊"

---
MARCAÇÃO OBRIGATÓRIA: No final de CADA resposta, em linha separada, escreva: [ETAPA:X]
(X = número da etapa atual, 1 a 5). Essa marcação é removida antes de chegar à usuária.
"""


def construir_prompt_com_diagnostico(d: dict | None) -> str:
    if not d:
        return INSTRUCOES_BASE

    primeiro_nome = (d.get("nome") or "").split()[0] or "empreendedora"

    try:
        score = float(d.get("score_maturidade") or 0) or None
    except (TypeError, ValueError):
        score = None

    if score is not None:
        if score < 40:
            nivel_ia = f"Score {score:.0f}/100 — iniciante digital. Use analogias bem simples, sem termos técnicos."
        elif score <= 70:
            nivel_ia = f"Score {score:.0f}/100 — intermediária. Pode usar exemplos um pouco mais técnicos."
        else:
            nivel_ia = f"Score {score:.0f}/100 — avançada. Pode ser mais direta e técnica."
    else:
        nivel_ia = "Score não calculado — prefira linguagem simples."

    contexto = f"""
=== CONTEXTO COMPLETO DA USUÁRIA ===

IDENTIDADE:
  Nome para chamar: {_txt(primeiro_nome)}
  Nome completo:    {_txt(d.get("nome"))}
  Empresa:          {_txt(d.get("nome_empresa"))}
  Cargo:            {_txt(d.get("cargo"))}
  Cidade:           {_txt(d.get("cidade"))}

HISTÓRIA E MOTIVAÇÃO (onboarding):
  Sobre ela:              {_txt(d.get("historia_pessoal"))}
  Sobre o negócio:        {_txt(d.get("historia_negocio"))}
  Momento atual:          {_txt(d.get("momento_atual"))}
  Principal desafio:      {_txt(d.get("principal_desafio"))}
  Maior objetivo:         {_txt(d.get("maior_objetivo"))}
  O que consome energia:  {_txt(d.get("consome_energia"))}
  O que precisa funcionar melhor: {_txt(d.get("funcionar_melhor"))}
  Familiaridade com IA:   {_txt(d.get("familiaridade_ia"))}
  Ferramentas que usa:    {_txt(d.get("ferramentas_atuais"))}
  Expectativas:           {_txt(d.get("expectativas"))}

SOBRE O NEGÓCIO:
  O que faz:            {_txt(d.get("o_que_faz"))}
  Produtos/serviços:    {_txt(d.get("produtos_servicos"))}
  Público-alvo:         {_txt(d.get("publico_alvo"))}
  Ticket médio:         {_txt(d.get("ticket_medio"))}
  Canais de venda:      {_txt(d.get("canais_venda"))}
  Tamanho do time:      {_txt(d.get("tamanho_time"))}
  Faixa de faturamento: {_txt(d.get("faturamento"))}
  Ferramentas do negócio: {_txt(d.get("ferramentas_negocio"))}
  Dores de crescimento: {_txt(d.get("dores_negocio"))}
  Áreas dependentes da fundadora: {_txt(d.get("areas_dependentes"))}
  Onde perde tempo:     {_txt(d.get("perdendo_tempo"))}
  Onde perde dinheiro:  {_txt(d.get("perdendo_dinheiro"))}

FLUXOS POR DEPARTAMENTO:
{_fluxos(d.get("fluxos"))}

DIAGNÓSTICO DE MATURIDADE EM IA:
  {nivel_ia}
  Resumo: {_txt(d.get("resumo_executivo"))}
  Gargalos:
{_lista(d.get("gargalos"))}
  Quick wins:
{_lista(d.get("quick_wins"))}
  Projetos estratégicos sugeridos:
{_lista(d.get("projetos_estrategicos"))}

OPORTUNIDADES DE AUTOMAÇÃO:
{_oportunidades(d.get("oportunidades"))}

PROJETOS DE IA EM ANDAMENTO:
{_projetos(d.get("projetos"))}

ROI JÁ REALIZADO:
{_roi(d.get("roi"))}

APRENDIZADO NA PLATAFORMA:
  Aulas concluídas: {d.get("total_aulas_concluidas", 0)}
  Trilhas: {", ".join(d.get("trilhas_disponiveis") or []) or "não carregadas"}
  Aulas feitas:
{_aulas(d.get("aulas_concluidas"))}
=====================================

INSTRUÇÕES ESPECIAIS:
- Chame-a SEMPRE de "{primeiro_nome}" — nunca omita o nome
- PULE a Etapa 1 — você já conhece muito bem o negócio e a história dela
- Na Etapa 2, confirme as dores em vez de perguntar do zero:
  "{primeiro_nome}, vi que seus maiores desafios são [gargalos/dores]. É isso mesmo?"
- Na Etapa 4, conecte cada agente a uma dor específica da vida DELA
- Se ela já tem projetos em andamento, reconheça antes de sugerir novos
- Se ela já tem ROI registrado, comemore com entusiasmo!
- Adapte a linguagem ao nível dela: {_txt(d.get("familiaridade_ia"))}
- Quando ela mencionar algo do negócio, mostre que você já sabia:
  "Ah sim, você me contou que [info do perfil] — faz todo sentido!"
=====================================
"""
    return contexto + "\n" + INSTRUCOES_BASE


def extrair_etapa_da_resposta(texto: str) -> tuple[str, int | None]:
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
    """Envia mensagens com prompt caching. Retorna (resposta, etapa_atual)."""
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

    return extrair_etapa_da_resposta(resposta.content[0].text)


def iniciar_conversa(d: dict | None = None) -> str:
    if d and d.get("nome"):
        primeiro_nome = d["nome"].split()[0]
        empresa       = d.get("nome_empresa") or "seu negócio"

        try:
            score = float(d.get("score_maturidade") or 0) or None
        except (TypeError, ValueError):
            score = None

        if score is not None:
            if score < 40:
                score_msg = f"Vi que você está começando sua jornada digital (score {score:.0f}/100) — e isso é ótimo! Temos muito espaço pra crescer juntas! 🌱\n\n"
            elif score <= 70:
                score_msg = f"Vi que você já tem uma boa base digital (score {score:.0f}/100)! Vamos acelerar ainda mais! 🚀\n\n"
            else:
                score_msg = f"Vi que você já é bastante avançada (score {score:.0f}/100)! Vamos criar agentes poderosos! 💪\n\n"
        else:
            score_msg = ""

        desafio = (
            d.get("principal_desafio")
            or (d.get("gargalos") or [None])[0]
            or d.get("dores_negocio")
        )
        desafio_msg = (
            f"Já vi que um dos seus maiores desafios é: **\"{desafio}\"**. "
            f"Vamos resolver isso juntas! 💪\n\n"
        ) if desafio else ""

        roi     = d.get("roi") or []
        roi_msg = "E você já tem resultados reais na plataforma — isso mostra que você está no caminho certo! 🎉\n\n" if roi else ""

        projetos = d.get("projetos") or []
        proj_msg = f"Vi também que você já tem {len(projetos)} projeto(s) de IA em andamento — incrível! 🚀\n\n" if projetos else ""

        return (
            f"Oi, {primeiro_nome}! Eu sou a TIAGA! 🌟\n\n"
            f"Já conheço a **{empresa}** e estou aqui para te ajudar a criar agentes inteligentes "
            f"que vão trabalhar por você enquanto você descansa! 😄\n\n"
            f"{score_msg}{desafio_msg}{roi_msg}{proj_msg}"
            f"Não precisa saber nada de tecnologia — eu vou te guiar em cada passinho com muito carinho! 💕\n\n"
            f"Por onde você quer começar hoje? 😊"
        )

    return (
        "Oi! Eu sou a TIAGA! 🌟\n\n"
        "Estou aqui para te ajudar a criar agentes inteligentes para o seu negócio!\n\n"
        "Não precisa saber nada de tecnologia — eu vou te guiar em cada passinho "
        "com muito carinho e paciência! 💕\n\n"
        "Vamos começar? Me conta: **o que você vende ou faz no seu negócio?** 😊"
    )
