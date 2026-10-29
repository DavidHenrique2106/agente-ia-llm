"""Tela principal: a conversa com o agente."""

import json
import time

import streamlit as st

from agente.ferramentas import CATALOGO
from agente.nucleo import NIVEIS_RACIOCINIO, limpar_texto
from interface import estado, estilo

AVATAR_USUARIO = ":material/person:"
AVATAR_ASSIS = ":material/smart_toy:"

SUGESTOES = [
    ("👋", "Oi! Meu nome é Ana e eu estudo Ciência da Computação."),
    ("🧮", "Quanto é a raiz de 1764 vezes 3,5?"),
    ("🛡️", "Quais os efeitos colaterais da vacina da dengue?"),
    ("🔬", "O que os estudos dizem sobre café e saúde do coração?"),
    ("🌦️", "Vai chover em São Paulo amanhã?"),
    ("📚", "Quem foi Alan Turing?"),
]


def _titulo_ferramenta(nome: str) -> str:
    info = CATALOGO.get(nome)
    return f"{info.icone} {info.titulo}" if info else f"🔧 {nome}"


def _resumo_argumentos(argumentos: dict) -> str:
    valor = str(next(iter(argumentos.values()), "")) if argumentos else ""
    return valor if len(valor) <= 70 else valor[:67] + "…"


def _duracao(segundos: float) -> str:
    segundos = round(segundos)
    return f"{segundos}s" if segundos < 60 else f"{segundos // 60}min {segundos % 60}s"


def mostrar_bastidores(msg: dict) -> None:
    """Painel recolhido "Pensou por Xs" com o raciocínio e as fontes consultadas."""
    pensamento, ferramentas = msg.get("pensamento", ""), msg.get("ferramentas", [])
    if not pensamento and not ferramentas:
        return
    rotulo = f"Pensou por {_duracao(msg.get('duracao', 0))}"
    with st.expander(rotulo, icon=":material/psychology:"):
        abas = [nome for nome, ativo in (("Raciocínio", pensamento),
                                          ("Ferramentas usadas", ferramentas)) if ativo]
        for aba, nome in zip(st.tabs(abas), abas):
            with aba:
                if nome == "Raciocínio":
                    st.caption(pensamento)
                    continue
                for f in ferramentas:
                    st.markdown(f"**{_titulo_ferramenta(f['nome'])}**")
                    st.code(json.dumps(f["argumentos"], ensure_ascii=False), language="json")
                    st.text(f["resultado"])


def _mensagem_de_erro(erro: Exception) -> str:
    texto = str(erro)
    if "rate_limit" in texto or "429" in texto:
        return ("O limite gratuito do Groq (tokens por minuto) foi atingido. Espere cerca "
                "de 1 minuto e tente de novo, ou use o raciocínio **Rápido** ou o modelo "
                "**gpt-oss-20b** em Configurações › Modelo.")
    return f"Não foi possível obter resposta: {texto}"


def responder(pergunta: str) -> dict | None:
    """Mostra o agente trabalhando em tempo real, como no ChatGPT."""
    status = st.status("Pensando…", expanded=True)
    with status:
        area_pensamento = st.empty()
        area_passos = st.container()
    area_resposta = st.empty()
    pensamento, texto, ultimo_desenho, inicio = "", "", 0.0, time.time()

    try:
        for tipo, dados in estado.obter_agente().perguntar_stream(pergunta):
            if tipo == "pensamento":
                pensamento += dados
                # Redesenhar a cada pedacinho deixaria a tela lenta.
                if time.time() - ultimo_desenho > 0.1:
                    area_pensamento.caption(pensamento[-2000:])
                    ultimo_desenho = time.time()
            elif tipo == "ferramenta":
                if texto:  # o que parecia resposta era só um comentário antes da pesquisa
                    pensamento += "\n\n" + texto
                    texto = ""
                    area_resposta.empty()
                pensamento += "\n\n"
                titulo = _titulo_ferramenta(dados["nome"])
                argumento = _resumo_argumentos(dados["argumentos"])
                status.update(label=f"{titulo}: {argumento}", state="running", expanded=True)
                area_passos.markdown(f"{titulo} · `{argumento}`")
            elif tipo == "texto":
                if not texto:
                    status.update(label=f"Pensou por {_duracao(time.time() - inicio)}",
                                  state="complete", expanded=False)
                texto += dados
                area_resposta.markdown(limpar_texto(texto) + " ▌")
            elif tipo == "fim":
                resposta = dados
    except Exception as erro:  # noqa: BLE001 - mostramos qualquer erro na tela
        status.update(label="Algo deu errado", state="error", expanded=False)
        st.error(_mensagem_de_erro(erro), icon=":material/error:")
        st.page_link(estado.PAGINAS["modelo"], label="Revisar configurações do modelo",
                     icon=":material/tune:")
        return None

    area_resposta.markdown(resposta.texto)
    if resposta.pensamento or resposta.ferramentas:
        status.update(label=f"Pensou por {_duracao(resposta.duracao)}", state="complete",
                      expanded=False)
    else:
        status.update(label=f"Respondeu em {_duracao(resposta.duracao)}", state="complete",
                      expanded=False)
    return {"papel": "assistant", "texto": resposta.texto, "ferramentas": resposta.ferramentas,
            "pensamento": resposta.pensamento, "duracao": resposta.duracao}


def boas_vindas() -> str | None:
    """Tela inicial vazia. Devolve a sugestão clicada, se houver."""
    st.html("""
        <div class="hero">
          <div class="avatar">🤖</div>
          <h1>Olá! Eu sou o Assis</h1>
          <p>Pergunte qualquer coisa. Eu lembro da conversa e consulto fontes
             confiáveis quando preciso.</p>
        </div>""")
    resumo_config()
    escolhida = None
    with st.container(key="sugestoes"):
        colunas = st.columns(2)
        for i, (icone, texto) in enumerate(SUGESTOES):
            if colunas[i % 2].button(f"{icone}  {texto}", use_container_width=True,
                                     key=f"sug{i}"):
                escolhida = texto
    return escolhida


def resumo_config() -> None:
    ativas = estado.ferramentas_ativas()
    estilo.chips([
        f"🧠 {estado.modelo_efetivo()}",
        f"💭 raciocínio {NIVEIS_RACIOCINIO[estado.cfg()['raciocinio']].lower()}",
        f"🛠️ {len(ativas)} ferramenta(s)" if ativas else "🛠️ ferramentas desligadas",
    ])


def pagina() -> None:
    mensagens = st.session_state.mensagens

    if mensagens:
        esquerda, direita = st.columns([3, 1], vertical_alignment="center")
        titulo = (estado.historico().titulo(st.session_state.thread_id or "", estado.dono())
                  or "Nova conversa")
        esquerda.markdown(f"### {titulo}")
        if direita.button("Nova conversa", icon=":material/add_comment:",
                          use_container_width=True):
            estado.nova_conversa()
            st.rerun()
        resumo_config()

    for msg in mensagens:
        with st.chat_message(msg["papel"], avatar=AVATAR_USUARIO if msg["papel"] == "user"
                             else AVATAR_ASSIS):
            if msg["papel"] == "assistant":
                mostrar_bastidores(msg)
            st.markdown(msg["texto"])

    pergunta = st.chat_input("Pergunte qualquer coisa…")
    if not mensagens and not pergunta:
        pergunta = boas_vindas()
    if not pergunta:
        return

    mensagens.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user", avatar=AVATAR_USUARIO):
        st.markdown(pergunta)

    with st.chat_message("assistant", avatar=AVATAR_ASSIS):
        resposta = responder(pergunta)
    if resposta is None:
        mensagens.pop()
        return
    mensagens.append(resposta)
    estado.salvar(mensagens[-2], resposta)
    st.rerun()
