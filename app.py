"""Interface web do agente (Streamlit).

Execute com:  streamlit run app.py

Este arquivo só monta a navegação. Cada tela fica em interface/paginas/:
  chat.py        conversa com o agente
  modelo.py      provedor, modelo, temperatura e chave da API
  ferramentas.py ferramentas e fontes de pesquisa
  sobre.py       como o agente funciona
A barra lateral com o histórico de conversas fica em interface/barra_lateral.py.
"""

import streamlit as st
from dotenv import load_dotenv

from interface import barra_lateral, estado, estilo
from interface.paginas import chat, ferramentas, modelo, sobre

load_dotenv()

st.set_page_config(page_title="Assis · Agente de IA", page_icon="🤖", layout="centered",
                   initial_sidebar_state="expanded")
estilo.aplicar()
estado.iniciar()

estado.PAGINAS.update({
    "chat": st.Page(chat.pagina, title="Chat", icon=":material/chat:",
                    url_path="chat", default=True),
    "modelo": st.Page(modelo.pagina, title="Modelo", icon=":material/psychology:",
                      url_path="modelo"),
    "ferramentas": st.Page(ferramentas.pagina, title="Ferramentas e fontes",
                           icon=":material/build:", url_path="ferramentas"),
    "sobre": st.Page(sobre.pagina, title="Como funciona", icon=":material/info:",
                     url_path="sobre"),
})
p = estado.PAGINAS
navegacao = st.navigation(
    {"": [p["chat"]], "Configurações": [p["modelo"], p["ferramentas"]], "Ajuda": [p["sobre"]]},
    position="top",
)
barra_lateral.mostrar()  # histórico de conversas, visível em todas as telas
navegacao.run()
