"""Histórico de conversas salvo em disco (SQLite), como a lista do ChatGPT.

Um único arquivo .db guarda duas coisas:
  - a memória do agente (checkpointer do LangGraph, com todas as mensagens,
    inclusive chamadas de ferramentas), para que ele continue lembrando da
    conversa mesmo depois de fechar e abrir o programa;
  - as tabelas "conversas" e "mensagens" abaixo, com o título de cada conversa
    e o que aparece na tela (texto, raciocínio, ferramentas usadas).

O thread_id do agente é o próprio id da conversa. Cada conversa tem um "dono"
(o visitante que a criou), para que num site público cada pessoa veja só as
próprias conversas. Rodando localmente, o dono é sempre "local".
"""

import json
import sqlite3
import time
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

_TABELAS = """
CREATE TABLE IF NOT EXISTS conversas (
    id            TEXT PRIMARY KEY,
    dono          TEXT NOT NULL DEFAULT 'local',
    titulo        TEXT NOT NULL,
    criada_em     REAL NOT NULL,
    atualizada_em REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mensagens (
    conversa_id TEXT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL,
    papel       TEXT NOT NULL,
    dados       TEXT NOT NULL,
    PRIMARY KEY (conversa_id, ordem)
);
"""


def titulo_automatico(pergunta: str, limite: int = 45) -> str:
    """Título a partir da primeira pergunta (sem gastar uma chamada ao LLM)."""
    texto = " ".join(pergunta.split())
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + "…"


class Historico:
    def __init__(self, caminho: str | Path):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        # O Streamlit atende cada sessão numa thread diferente, então a mesma
        # conexão é compartilhada entre threads. Usamos a mesma trava do
        # checkpointer para que nunca haja dois acessos ao banco ao mesmo tempo.
        self._conexao = sqlite3.connect(caminho, check_same_thread=False)
        self._conexao.execute("PRAGMA foreign_keys = ON")
        self.memoria = SqliteSaver(self._conexao)
        self.memoria.setup()
        self._trava = self.memoria.lock
        with self._trava, self._conexao:
            self._conexao.executescript(_TABELAS)
            colunas = [c[1] for c in self._conexao.execute("PRAGMA table_info(conversas)")]
            if "dono" not in colunas:  # bancos criados antes da coluna existir
                self._conexao.execute(
                    "ALTER TABLE conversas ADD COLUMN dono TEXT NOT NULL DEFAULT 'local'")

    # --- conversas ---------------------------------------------------------
    def listar(self, busca: str = "", dono: str = "local") -> list[dict]:
        """Conversas do dono, da mais recente para a mais antiga."""
        with self._trava:
            linhas = self._conexao.execute(
                "SELECT id, titulo, atualizada_em FROM conversas "
                "WHERE dono = ? AND titulo LIKE ? ORDER BY atualizada_em DESC",
                (dono, f"%{busca}%"),
            ).fetchall()
        return [{"id": i, "titulo": t, "atualizada_em": a} for i, t, a in linhas]

    def titulo(self, conversa_id: str, dono: str = "local") -> str | None:
        with self._trava:
            linha = self._conexao.execute(
                "SELECT titulo FROM conversas WHERE id = ? AND dono = ?",
                (conversa_id, dono)).fetchone()
        return linha[0] if linha else None

    def renomear(self, conversa_id: str, titulo: str, dono: str = "local") -> None:
        with self._trava, self._conexao:
            self._conexao.execute("UPDATE conversas SET titulo = ? WHERE id = ? AND dono = ?",
                                  (titulo.strip() or "Sem título", conversa_id, dono))

    def apagar(self, conversa_id: str, dono: str = "local") -> None:
        with self._trava, self._conexao:
            apagadas = self._conexao.execute(
                "DELETE FROM conversas WHERE id = ? AND dono = ?", (conversa_id, dono)).rowcount
        if apagadas:
            self.memoria.delete_thread(conversa_id)  # apaga também a memória do agente

    # --- mensagens ---------------------------------------------------------
    def mensagens(self, conversa_id: str, dono: str = "local") -> list[dict]:
        with self._trava:
            linhas = self._conexao.execute(
                "SELECT m.dados FROM mensagens m JOIN conversas c ON c.id = m.conversa_id "
                "WHERE m.conversa_id = ? AND c.dono = ? ORDER BY m.ordem",
                (conversa_id, dono),
            ).fetchall()
        return [json.loads(dados) for (dados,) in linhas]

    def adicionar(self, conversa_id: str, *mensagens: dict, dono: str = "local") -> None:
        """Salva mensagens; cria a conversa (com título automático) se for nova."""
        agora = time.time()
        with self._trava, self._conexao:
            existe = self._conexao.execute(
                "SELECT 1 FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
            if not existe:
                primeira = next((m["texto"] for m in mensagens if m["papel"] == "user"),
                                "Nova conversa")
                self._conexao.execute(
                    "INSERT INTO conversas (id, dono, titulo, criada_em, atualizada_em) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (conversa_id, dono, titulo_automatico(primeira), agora, agora))
            ordem = self._conexao.execute(
                "SELECT COALESCE(MAX(ordem), -1) FROM mensagens WHERE conversa_id = ?",
                (conversa_id,)).fetchone()[0]
            for m in mensagens:
                ordem += 1
                self._conexao.execute(
                    "INSERT INTO mensagens VALUES (?, ?, ?, ?)",
                    (conversa_id, ordem, m["papel"], json.dumps(m, ensure_ascii=False)))
            self._conexao.execute("UPDATE conversas SET atualizada_em = ? WHERE id = ?",
                                  (agora, conversa_id))
