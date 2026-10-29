"""Estado compartilhado entre as telas: configurações, agente e conversa.

As configurações ficam em st.session_state.cfg (um dicionário comum). Os
widgets do Streamlit perdem o valor quando a tela deles não está aberta, então
cada widget usa uma chave própria ("w_...") que é copiada de/para o cfg.
"""

import os
import re
import uuid
from pathlib import Path

import streamlit as st

from agente import Agente, criar_modelo
from agente.ferramentas import CATALOGO
from agente.historico import Historico
from agente.nucleo import PROVEDORES

# ASSIS_BANCO permite usar outro arquivo (ex.: em testes).
CAMINHO_BANCO = Path(os.getenv("ASSIS_BANCO")
                     or Path(__file__).resolve().parents[1] / "dados" / "assis.db")

# Preenchido pelo app.py com as páginas (st.Page) para permitir links entre telas.
PAGINAS: dict = {}

PADROES = {
    "provedor": next(iter(PROVEDORES)),
    "modelo": PROVEDORES[next(iter(PROVEDORES))]["modelos"][0],
    "modelo_personalizado": "",
    "temperatura": 0.3,
    "raciocinio": "medium",
    "api_key": "",
    "usar_ferramentas": True,
    "ferramentas": list(CATALOGO),
}


def iniciar() -> None:
    st.session_state.setdefault("cfg", dict(PADROES))
    for chave, valor in PADROES.items():  # configurações novas em sessões antigas
        st.session_state.cfg.setdefault(chave, valor)
    st.session_state.setdefault("mensagens", [])
    st.session_state.setdefault("thread_id", None)
    dono()


def modo_publico() -> bool:
    """Ligado no site publicado (ASSIS_MODO_PUBLICO=1 nos segredos)."""
    return os.getenv("ASSIS_MODO_PUBLICO", "").lower() in {"1", "true", "sim"}


def dono() -> str:
    """Quem é o visitante, para separar o histórico de cada pessoa.

    Localmente é sempre "local". No site público, cada navegador recebe um
    código aleatório que fica no link (?u=...): recarregar a página mantém as
    conversas, e quem não tem o código não as vê.
    """
    if not modo_publico():
        return "local"
    if "dono" not in st.session_state:
        codigo = st.query_params.get("u", "")
        st.session_state.dono = (codigo if re.fullmatch(r"[0-9a-f]{32}", codigo)
                                 else uuid.uuid4().hex)
    if st.query_params.get("u") != st.session_state.dono:  # trocar de tela pode limpar o link
        st.query_params["u"] = st.session_state.dono
    return st.session_state.dono


@st.cache_resource
def historico() -> Historico:
    """Um único banco para o app inteiro (compartilhado entre abas e sessões)."""
    return Historico(CAMINHO_BANCO)


def cfg() -> dict:
    return st.session_state.cfg


def vincular(chave: str, ao_mudar=None) -> dict:
    """Argumentos para um widget que lê e grava cfg[chave]."""
    st.session_state[f"w_{chave}"] = cfg()[chave]

    def salvar():
        if st.session_state[f"w_{chave}"] is None:  # ex.: desmarcou o seletor
            st.session_state[f"w_{chave}"] = cfg()[chave]
            return
        cfg()[chave] = st.session_state[f"w_{chave}"]
        if ao_mudar:
            ao_mudar()

    return {"key": f"w_{chave}", "on_change": salvar}


def modelo_efetivo() -> str:
    return cfg()["modelo_personalizado"].strip() or cfg()["modelo"]


def provedor_id() -> str:
    return PROVEDORES[cfg()["provedor"]]["id"]


def chave_no_env() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def ferramentas_ativas() -> list[str]:
    if not cfg()["usar_ferramentas"]:
        return []
    return [nome for nome in CATALOGO if nome in cfg()["ferramentas"]]


def _assinatura() -> tuple:
    c = cfg()
    return (provedor_id(), modelo_efetivo(), c["temperatura"], c["raciocinio"],
            c["api_key"], tuple(ferramentas_ativas()))


def obter_agente() -> Agente:
    """Recria o agente quando a configuração muda, mantendo a conversa."""
    assinatura = _assinatura()
    if st.session_state.get("assinatura") != assinatura or "agente" not in st.session_state:
        llm = criar_modelo(provedor_id(), modelo_efetivo(), cfg()["temperatura"],
                           cfg()["api_key"] or None, cfg()["raciocinio"])
        agente = Agente(
            llm,
            ferramentas=[CATALOGO[n].ferramenta for n in ferramentas_ativas()],
            memoria=historico().memoria,
            thread_id=st.session_state.thread_id,
        )
        st.session_state.thread_id = agente.thread_id
        st.session_state.agente = agente
        st.session_state.assinatura = assinatura
    return st.session_state.agente


def nova_conversa() -> None:
    st.session_state.mensagens = []
    st.session_state.thread_id = None
    st.session_state.pop("agente", None)


def abrir_conversa(conversa_id: str) -> None:
    st.session_state.mensagens = historico().mensagens(conversa_id, dono())
    st.session_state.thread_id = conversa_id
    st.session_state.pop("agente", None)  # o próximo agente usa este thread_id


def salvar(*mensagens: dict) -> None:
    """Grava as mensagens da conversa atual (cria a conversa se for nova)."""
    historico().adicionar(st.session_state.thread_id, *mensagens, dono=dono())


def apagar_conversa(conversa_id: str) -> None:
    historico().apagar(conversa_id, dono())
    if st.session_state.thread_id == conversa_id:
        nova_conversa()
