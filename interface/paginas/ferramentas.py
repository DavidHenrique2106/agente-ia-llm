"""Tela para escolher quais ferramentas e fontes o agente pode usar."""

import streamlit as st

from agente.ferramentas import CATALOGO, FONTES_CONFIAVEIS
from interface import estado


def _alternar(nome: str) -> None:
    ligadas = estado.cfg()["ferramentas"]
    if st.session_state[f"w_tool_{nome}"]:
        ligadas.append(nome)
    else:
        ligadas.remove(nome)


def _cartao(nome: str, desabilitado: bool) -> None:
    info = CATALOGO[nome]
    with st.container(border=True):
        texto, chave = st.columns([5, 1], vertical_alignment="center")
        texto.markdown(f"**{info.icone} {info.titulo}**")
        texto.caption(info.descricao)
        st.session_state[f"w_tool_{nome}"] = nome in estado.cfg()["ferramentas"]
        chave.toggle(info.titulo, key=f"w_tool_{nome}", on_change=_alternar, args=(nome,),
                     disabled=desabilitado, label_visibility="collapsed")


def pagina() -> None:
    st.title("🛠️ Ferramentas e fontes")
    st.caption("Ferramentas são o que fazem do Assis um *agente*: ele decide sozinho "
               "quando precisa consultar uma fonte ou fazer uma conta.")

    with st.container(border=True):
        st.toggle("Permitir que o agente use ferramentas",
                  help="Desligado, o modelo responde só com o que aprendeu no treino.",
                  **estado.vincular("usar_ferramentas"))
    desligado = not estado.cfg()["usar_ferramentas"]

    st.subheader("🔎 Onde pesquisar")
    st.caption("Do mais confiável para o menos confiável. O agente é instruído a "
               "preferir as fontes do topo.")
    for nome, info in CATALOGO.items():
        if info.grupo == "Pesquisa":
            _cartao(nome, desligado)

    with st.expander("Quais sites contam como “fonte confiável”?",
                     icon=":material/verified:"):
        st.markdown(
            "A busca na web descarta qualquer resultado fora desta lista. "
            "Também valem universidades federais e PUCs (`uf*.br`, `puc*.br`)."
        )
        for tipo, dominios in FONTES_CONFIAVEIS.items():
            st.markdown(f"**{tipo.capitalize()}:** " + ", ".join(f"`{d}`" for d in dominios))

    st.subheader("🧰 Utilidades")
    for nome, info in CATALOGO.items():
        if info.grupo == "Utilidades":
            _cartao(nome, desligado)
