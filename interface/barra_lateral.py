"""Barra lateral com o histórico de conversas, no estilo do ChatGPT."""

from datetime import datetime, timedelta

import streamlit as st

from interface import estado


def _grupo(momento: float) -> str:
    hoje = datetime.now().date()
    dia = datetime.fromtimestamp(momento).date()
    if dia == hoje:
        return "Hoje"
    if dia == hoje - timedelta(days=1):
        return "Ontem"
    if dia > hoje - timedelta(days=7):
        return "Últimos 7 dias"
    if dia > hoje - timedelta(days=30):
        return "Últimos 30 dias"
    return "Mais antigas"


def _abrir(conversa_id: str | None) -> None:
    if conversa_id is None:
        estado.nova_conversa()
    else:
        estado.abrir_conversa(conversa_id)
    st.switch_page(estado.PAGINAS["chat"])


def _item(conversa: dict) -> None:
    cid = conversa["id"]
    atual = cid == st.session_state.thread_id
    titulo, menu = st.columns([6, 1], vertical_alignment="center", gap="small")
    if titulo.button(conversa["titulo"], key=f"abrir_{cid}", use_container_width=True,
                     type="primary" if atual else "tertiary"):
        _abrir(cid)
    with menu.popover("", icon=":material/more_horiz:"):
        novo = st.text_input("Renomear", value=conversa["titulo"], key=f"nome_{cid}")
        if st.button("Salvar nome", key=f"renomear_{cid}", icon=":material/edit:",
                     use_container_width=True):
            estado.historico().renomear(cid, novo, estado.dono())
            st.rerun()
        if st.button("Apagar conversa", key=f"apagar_{cid}", icon=":material/delete:",
                     use_container_width=True):
            estado.apagar_conversa(cid)
            st.rerun()


def mostrar() -> None:
    with st.sidebar:
        if st.button("Nova conversa", icon=":material/edit_square:", type="primary",
                     use_container_width=True):
            _abrir(None)

        busca = st.text_input("Buscar", placeholder="Buscar conversas…",
                              label_visibility="collapsed", icon=":material/search:")
        conversas = estado.historico().listar(busca.strip(), estado.dono())
        if estado.modo_publico():
            st.caption(":material/lock: Só você vê suas conversas. Elas ficam ligadas a "
                       "este link; salve-o nos favoritos para voltar a elas.")
        if not conversas:
            st.caption("Nenhuma conversa encontrada." if busca else
                       "Suas conversas aparecem aqui.")
            return

        grupo_atual = None
        with st.container(key="lista_conversas"):
            for conversa in conversas:
                grupo = _grupo(conversa["atualizada_em"])
                if grupo != grupo_atual:
                    st.caption(f"**{grupo}**")
                    grupo_atual = grupo
                _item(conversa)
