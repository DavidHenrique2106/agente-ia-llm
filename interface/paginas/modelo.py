"""Tela de configurações do modelo de linguagem (LLM)."""

import streamlit as st

from agente import criar_modelo
from agente.nucleo import MODELOS, NIVEIS_RACIOCINIO
from interface import estado


def pagina() -> None:
    cfg = estado.cfg()
    st.title("🧠 Modelo")
    st.caption("Escolha qual modelo de linguagem responde às suas perguntas. "
               "Mudar algo aqui não apaga a conversa.")

    if not estado.chave_no_env():
        st.error("A chave da Groq não está configurada. Coloque `GROQ_API_KEY=...` no "
                 "arquivo `.env` (ou nos Secrets do Streamlit Cloud) e reinicie o app.",
                 icon=":material/key_off:")

    with st.container(border=True):
        st.markdown("##### Modelo")
        st.caption("Modelos de pesos abertos rodando na nuvem da Groq: gratuito e rápido.")
        st.selectbox("Modelo de pesos abertos", MODELOS, **estado.vincular("modelo"))
        st.text_input("Outro modelo da Groq (opcional)", placeholder="ex.: openai/gpt-oss-20b",
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

    if st.button("Testar conexão", icon=":material/wifi_tethering:"):
        with st.spinner(f"Conversando com {estado.modelo_efetivo()}…"):
            try:
                llm = criar_modelo(estado.modelo_efetivo(), cfg["temperatura"],
                                   cfg["raciocinio"])
                llm.invoke("Responda apenas: ok")
            except Exception as erro:  # noqa: BLE001
                st.error(f"Não funcionou: {erro}", icon=":material/error:")
            else:
                st.success("Tudo certo! O modelo respondeu.", icon=":material/check_circle:")
