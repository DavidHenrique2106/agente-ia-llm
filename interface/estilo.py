"""CSS leve aplicado a todas as telas (funciona no tema claro e no escuro)."""

from html import escape

import streamlit as st

CSS = """
<style>
/* Largura confortável de leitura */
.block-container { max-width: 860px; padding-top: 4.5rem; }

/* Cabeçalho de boas-vindas */
.hero { text-align: center; padding: 1.5rem 0 1rem; }
.hero .avatar {
    width: 84px; height: 84px; margin: 0 auto 0.75rem; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; font-size: 2.6rem;
    background: linear-gradient(135deg, #7C5CFC 0%, #4FC3F7 100%);
    box-shadow: 0 8px 24px rgba(124, 92, 252, 0.35);
}
.hero h1 { font-size: 2.1rem; margin: 0; padding: 0; }
.hero p { opacity: 0.75; font-size: 1.05rem; margin-top: 0.35rem; }

/* "Chips" com o resumo da configuração atual */
.chips { display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: center;
         margin: 0.25rem 0 1.25rem; }
.chip { font-size: 0.8rem; padding: 0.2rem 0.7rem; border-radius: 999px;
        background: rgba(124, 92, 252, 0.12); border: 1px solid rgba(124, 92, 252, 0.3); }

/* Título pequeno das telas de configuração */
.titulo-tela { margin-bottom: 0.2rem; }
.subtitulo-tela { opacity: 0.7; margin-bottom: 1.2rem; }

/* Lista de conversas na barra lateral: títulos alinhados à esquerda, em 1 linha */
.st-key-lista_conversas button[kind^="primary"], .st-key-lista_conversas button[kind^="tertiary"] {
    justify-content: flex-start; text-align: left; padding: 0.25rem 0.6rem; }
.st-key-lista_conversas button p {
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.st-key-lista_conversas [data-testid="stVerticalBlock"] { gap: 0.1rem; }

/* Botões de sugestão mais altos, com texto à esquerda */
.st-key-sugestoes button { min-height: 3.6rem; justify-content: flex-start;
                           text-align: left; }
</style>
"""


def aplicar() -> None:
    st.html(CSS)


def chips(itens: list[str]) -> None:
    st.html('<div class="chips">' + "".join(f'<span class="chip">{escape(i)}</span>' for i in itens)
            + "</div>")
