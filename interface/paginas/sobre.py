"""Tela explicando como o agente funciona."""

import streamlit as st


def pagina() -> None:
    st.title("ℹ️ Como funciona")
    st.caption("O Assis é um agente de IA: um modelo de linguagem que conversa, "
               "lembra e decide sozinho quando usar ferramentas.")

    passos = [
        ("💬", "Você pergunta",
         "A pergunta entra no histórico da conversa, que fica salvo na memória."),
        ("🧠", "O modelo pensa",
         "O LLM recebe as instruções, o histórico e a lista de ferramentas ligadas."),
        ("🛠️", "Usa ferramentas, se precisar",
         "Ele pode pesquisar em fontes confiáveis, buscar artigos científicos, "
         "fazer contas, ver a data ou o clima (no máximo 3 por pergunta)."),
        ("✅", "Responde citando as fontes",
         "A resposta final aparece no chat, com os links das fontes consultadas."),
    ]
    for icone, titulo, texto in passos:
        with st.container(border=True):
            st.markdown(f"**{icone} {titulo}**")
            st.caption(texto)

    st.subheader("Memória")
    st.markdown(
        "Cada conversa tem um identificador (`thread_id`) e todo o histórico é "
        "reenviado ao modelo a cada pergunta. Conversas longas (mais de ~6 mil "
        "tokens) têm as mensagens antigas resumidas automaticamente. "
        "**Nova conversa** começa do zero; trocar o modelo mantém o histórico.\n\n"
        "Tudo fica salvo num banco SQLite (`dados/assis.db`): a lista de conversas "
        "na barra lateral e a memória do agente. Ao reabrir uma conversa antiga, "
        "mesmo depois de fechar o programa, ele continua lembrando do contexto."
    )

    st.subheader("Tecnologias")
    st.markdown(
        "- **LangChain + LangGraph**: orquestração do agente e memória (SqliteSaver)\n"
        "- **Groq** (nuvem) ou **Ollama** (local): modelos de pesos abertos\n"
        "- **DuckDuckGo** com filtro de domínios: busca em fontes confiáveis\n"
        "- **OpenAlex**: artigos científicos · **Wikipédia** · **Open-Meteo**: clima\n"
        "- **Streamlit**: esta interface"
    )
