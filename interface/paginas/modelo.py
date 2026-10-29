"""Tela de configurações do modelo de linguagem (LLM)."""

import streamlit as st

from agente import criar_modelo
from agente.nucleo import NIVEIS_RACIOCINIO, PROVEDORES
from interface import estado

DESCRICAO_PROVEDOR = {
    "groq": "Roda na nuvem da Groq, de graça e muito rápido. Precisa de uma chave de API.",
    "ollama": "Roda no seu computador, sem internet. Precisa do Ollama instalado "
              "(https://ollama.com) e do modelo baixado com `ollama pull`.",
}


def _trocou_provedor() -> None:
    # O modelo escolhido antes pode não existir no novo provedor.
    estado.cfg()["modelo"] = PROVEDORES[estado.cfg()["provedor"]]["modelos"][0]


def pagina() -> None:
    cfg = estado.cfg()
    st.title("🧠 Modelo")
    st.caption("Escolha qual modelo de linguagem responde às suas perguntas. "
               "Mudar algo aqui não apaga a conversa.")

    with st.container(border=True):
        st.markdown("##### Onde o modelo roda")
        st.radio("Provedor", list(PROVEDORES), horizontal=True,
                 label_visibility="collapsed", **estado.vincular("provedor", _trocou_provedor))
        st.caption(DESCRICAO_PROVEDOR[estado.provedor_id()])

    with st.container(border=True):
        st.markdown("##### Modelo")
        st.selectbox("Modelo de pesos abertos",
                     PROVEDORES[cfg["provedor"]]["modelos"], **estado.vincular("modelo"))
        st.text_input("Outro modelo (opcional)", placeholder="ex.: openai/gpt-oss-20b",
                      help="Se preencher, este nome substitui o modelo da lista acima.",
                      **estado.vincular("modelo_personalizado"))

    with st.container(border=True):
        st.markdown("##### Estilo das respostas")
        st.select_slider(
            "Temperatura", options=[round(i / 10, 1) for i in range(11)],
            format_func=lambda t: f"{t:.1f}", **estado.vincular("temperatura"),
        )
        st.caption("⬅️ **0.0** mais preciso e previsível · **1.0** mais criativo e variado ➡️")

    with st.container(border=True):
        st.markdown("##### Raciocínio")
        st.segmented_control(
            "Quanto o modelo pensa antes de responder", list(NIVEIS_RACIOCINIO),
            format_func=NIVEIS_RACIOCINIO.get, **estado.vincular("raciocinio"),
        )
        st.caption("O raciocínio aparece no chat em tempo real, em \"Pensando…\". "
                   "**Profundo** responde melhor perguntas difíceis, mas demora mais e "
                   "gasta mais da cota gratuita. Vale para os modelos gpt-oss.")

    if estado.provedor_id() == "groq":
        with st.container(border=True):
            st.markdown("##### Chave da API Groq")
            if estado.chave_no_env():
                st.success("Chave carregada do arquivo `.env`.", icon=":material/key:")
            else:
                st.text_input("Chave", type="password", placeholder="gsk_…",
                              help="Crie grátis em https://console.groq.com/keys",
                              **estado.vincular("api_key"))
                st.caption("Dica: coloque a chave no arquivo `.env` para não precisar "
                           "digitá-la toda vez.")

    if st.button("Testar conexão", icon=":material/wifi_tethering:"):
        with st.spinner(f"Conversando com {estado.modelo_efetivo()}…"):
            try:
                llm = criar_modelo(estado.provedor_id(), estado.modelo_efetivo(),
                                   cfg["temperatura"], cfg["api_key"] or None,
                                   cfg["raciocinio"])
                llm.invoke("Responda apenas: ok")
            except Exception as erro:  # noqa: BLE001
                st.error(f"Não funcionou: {erro}", icon=":material/error:")
            else:
                st.success("Tudo certo! O modelo respondeu.", icon=":material/check_circle:")
