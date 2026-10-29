"""Núcleo do agente: monta o LLM, as ferramentas e a memória da conversa.

Fluxo (padrão ReAct, implementado pelo LangChain/LangGraph):

    pergunta -> LLM decide -> (chama ferramenta -> lê resultado)* -> resposta

A memória fica num "checkpointer": cada conversa tem um thread_id e todo o
histórico de mensagens desse thread é reenviado ao LLM a cada pergunta. Isso é
o que permite o agente lembrar do que foi dito antes.
"""

import os
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, wrap_model_call
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from agente.ferramentas import CATALOGO, FERRAMENTAS

# Máximo de ferramentas por pergunta. Além de ser mais rápido, isso protege a
# cota gratuita do Groq (8 mil tokens por minuto): cada resultado de pesquisa
# entra no histórico e é reenviado ao modelo.
LIMITE_FERRAMENTAS = 3

PROMPT_SISTEMA = """Você é o Assis, um assistente de IA prestativo, educado e \
objetivo, criado como projeto acadêmico.

Regras:
- Responda sempre em português do Brasil, a menos que o usuário peça outro idioma.
- Use o histórico da conversa: lembre-se de nomes, preferências e do que já foi dito.
- Se não souber algo e as ferramentas não ajudarem, diga que não sabe; não invente.
- Formate respostas longas com Markdown (listas, negrito, tabelas) para facilitar a leitura."""

REGRAS_FERRAMENTAS = """

Ferramentas:
- Use no máximo {limite} ferramentas por pergunta. Em perguntas de opinião \
(ex.: "o melhor de todos"), não pesquise cada candidato: responda com o que sabe.
- Se a pergunta não tiver um número exato ou consolidado (ex.: dados somados \
do mundo inteiro), não fique pesquisando de novo: diga isso e responda com a \
melhor estimativa e o contexto que encontrou.
- Sempre que usar uma pesquisa, termine com uma seção "Fontes" listando os \
links realmente usados, no formato Markdown [título](url). Nunca invente links \
e não use marcadores como 【1†source】.
- Quando usar cada uma:
{guias}"""


def montar_prompt(ferramentas: list[BaseTool]) -> str:
    """Prompt de sistema com as orientações só das ferramentas ligadas."""
    if not ferramentas:
        return PROMPT_SISTEMA
    guias = "\n".join(
        f"  - {f.name}: {CATALOGO[f.name].guia if f.name in CATALOGO else f.description}"
        for f in ferramentas
    )
    prompt = PROMPT_SISTEMA + REGRAS_FERRAMENTAS.format(guias=guias, limite=LIMITE_FERRAMENTAS)
    pesquisas = [f.name for f in ferramentas
                 if f.name in CATALOGO and CATALOGO[f.name].grupo == "Pesquisa"]
    if len(pesquisas) > 1:
        # O CATALOGO já está em ordem de confiabilidade.
        prompt += ("\n- Para pesquisar, siga esta ordem de preferência: "
                   + " > ".join(pesquisas)
                   + ". Comece pela primeira e só passe para a seguinte se ela "
                   "não trouxer o que você precisa.")
    return prompt


PROVEDORES = {
    "Groq (nuvem, gratuito)": {
        "id": "groq",
        "modelos": [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ],
    },
    "Ollama (local)": {
        "id": "ollama",
        "modelos": ["llama3.2", "qwen2.5:7b", "llama3.1:8b", "mistral"],
    },
}


NIVEIS_RACIOCINIO = {"low": "Rápido", "medium": "Equilibrado", "high": "Profundo"}


def criar_modelo(provedor: str, modelo: str, temperatura: float = 0.3,
                 api_key: str | None = None, raciocinio: str = "medium") -> BaseChatModel:
    """Cria o LLM. Ambos os provedores servem modelos de pesos abertos.

    raciocinio ("low", "medium" ou "high") define quanto o modelo pensa antes
    de responder. Vale para os modelos gpt-oss, que devolvem o raciocínio
    separado da resposta para ser exibido na tela.
    """
    if provedor == "groq":
        from langchain_groq import ChatGroq

        chave = api_key or os.getenv("GROQ_API_KEY")
        if not chave:
            raise ValueError(
                "Chave da Groq não encontrada. Crie uma grátis em "
                "https://console.groq.com/keys e coloque no arquivo .env "
                "(GROQ_API_KEY=...) ou na tela Configurações › Modelo."
            )
        extras = {}
        if "gpt-oss" in modelo:
            extras = {"reasoning_format": "parsed", "reasoning_effort": raciocinio}
        elif "qwen3" in modelo:
            extras = {"reasoning_format": "parsed"}
        return ChatGroq(model=modelo, temperature=temperatura, api_key=chave,
                        max_retries=2, timeout=60, **extras)
    if provedor == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=modelo, temperature=temperatura,
                          base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    raise ValueError(f"Provedor desconhecido: {provedor}")


@dataclass
class Resposta:
    texto: str
    ferramentas: list[dict] = field(default_factory=list)
    pensamento: str = ""
    duracao: float = 0.0


def _mensagens_da_rodada(mensagens: list) -> list:
    """Mensagens geradas na rodada atual = tudo depois da última pergunta."""
    inicio = max((i for i, m in enumerate(mensagens) if isinstance(m, HumanMessage)),
                 default=-1)
    return mensagens[inicio + 1:]


@wrap_model_call
def limitar_ferramentas(request, handler):
    """Depois de LIMITE_FERRAMENTAS chamadas na mesma pergunta, o modelo é
    chamado sem ferramentas disponíveis, então ele é obrigado a responder."""
    rodada = _mensagens_da_rodada(request.messages)
    resultados = [m for m in rodada if isinstance(m, ToolMessage)]
    if len(resultados) >= LIMITE_FERRAMENTAS:
        # Sem ferramentas, o modelo não pode ver chamadas de ferramenta na
        # rodada atual (ele tentaria continuar o padrão e a API recusaria).
        # Então os resultados viram texto comum nas instruções.
        anteriores = request.messages[:len(request.messages) - len(rodada)]
        achados = "\n\n".join(f"[{m.name}]\n{_conteudo(m.content)}" for m in resultados)
        request = request.override(
            tools=[],
            messages=anteriores,
            system_prompt=(request.system_prompt or "") + (
                "\n\nVocê já fez todas as pesquisas permitidas para esta pergunta. "
                "Responda agora usando estes resultados:\n\n" + achados),
        )
    return handler(request)


class Agente:
    """Agente conversacional com memória e ferramentas."""

    def __init__(self, modelo: BaseChatModel,
                 ferramentas: list[BaseTool] | None = None,
                 memoria: InMemorySaver | None = None,
                 thread_id: str | None = None):
        """ferramentas=None usa todas; [] desliga as ferramentas.

        Passar a mesma memoria e thread_id de um agente anterior mantém a
        conversa, o que permite trocar de modelo sem perder o histórico.
        """
        ferramentas = FERRAMENTAS if ferramentas is None else ferramentas
        self.memoria = memoria or InMemorySaver()
        self.thread_id = thread_id or str(uuid.uuid4())
        self._grafo = create_agent(
            model=modelo,
            tools=ferramentas,
            system_prompt=montar_prompt(ferramentas),
            checkpointer=self.memoria,
            # Conversas muito longas estourariam a janela de contexto do LLM.
            # Quando o histórico passa de ~6 mil tokens, as mensagens antigas
            # são resumidas e as 20 mais recentes são mantidas na íntegra.
            middleware=[
                SummarizationMiddleware(
                    model=modelo, trigger=("tokens", 6000), keep=("messages", 20),
                ),
                # Evita que o agente fique em ciclo chamando ferramentas.
                limitar_ferramentas,
            ],
        )

    @property
    def _config(self) -> dict:
        return {"configurable": {"thread_id": self.thread_id},
                # Cada passo passa pelo modelo, pelas ferramentas e pelos
                # middlewares; o limite real de pesquisas é LIMITE_FERRAMENTAS.
                "recursion_limit": 60}

    def perguntar(self, pergunta: str) -> Resposta:
        """Envia a pergunta ao agente e devolve a resposta final."""
        estado = self._grafo.invoke(
            {"messages": [HumanMessage(pergunta)]}, config=self._config,
        )
        mensagens = estado["messages"]
        return Resposta(texto=_texto(mensagens[-1]),
                        ferramentas=_extrair_ferramentas(_mensagens_da_rodada(mensagens)))

    def perguntar_stream(self, pergunta: str) -> Iterator[tuple[str, object]]:
        """Versão em tempo real de perguntar(), no estilo do ChatGPT.

        Gera eventos (tipo, dados) conforme o agente trabalha:
          ("pensamento", texto)  trecho do raciocínio do modelo
          ("texto", texto)       trecho da resposta
          ("ferramenta", dict)   o modelo pediu uma ferramenta (nome, argumentos)
          ("resultado", dict)    a ferramenta terminou (nome, resultado)
          ("fim", Resposta)      resposta completa
        """
        inicio = time.time()
        pensamento = ""
        for modo, dados in self._grafo.stream(
            {"messages": [HumanMessage(pergunta)]}, config=self._config,
            stream_mode=["messages", "updates"],
        ):
            if modo == "messages":
                pedaco, meta = dados
                # Ignora chamadas internas (ex.: o resumo de conversas longas).
                if meta.get("langgraph_node") != "model" or not isinstance(pedaco, AIMessageChunk):
                    continue
                if raciocinio := pedaco.additional_kwargs.get("reasoning_content"):
                    pensamento += raciocinio
                    yield "pensamento", raciocinio
                if texto := _conteudo(pedaco.content):
                    yield "texto", texto
                continue
            for atualizacao in dados.values():
                for m in (atualizacao or {}).get("messages", []) if isinstance(atualizacao, dict) else []:
                    if isinstance(m, AIMessage):
                        if m.tool_calls and pensamento:
                            pensamento += "\n\n"  # separa o raciocínio de cada etapa
                        for chamada in m.tool_calls:
                            yield "ferramenta", {"nome": chamada["name"],
                                                 "argumentos": chamada["args"]}
                    elif isinstance(m, ToolMessage):
                        yield "resultado", {"nome": m.name, "resultado": m.content}

        mensagens = self.historico()
        yield "fim", Resposta(
            texto=_texto(mensagens[-1]),
            ferramentas=_extrair_ferramentas(_mensagens_da_rodada(mensagens)),
            pensamento=pensamento.strip(),
            duracao=time.time() - inicio,
        )

    def historico(self) -> list:
        estado = self._grafo.get_state(self._config)
        return estado.values.get("messages", []) if estado.values else []

    def nova_conversa(self) -> None:
        """Começa um novo thread, ou seja, o agente "esquece" a conversa."""
        self.thread_id = str(uuid.uuid4())


def _conteudo(conteudo) -> str:
    if isinstance(conteudo, list):  # alguns modelos devolvem blocos
        conteudo = "".join(b.get("text", "") if isinstance(b, dict) else str(b)
                           for b in conteudo)
    return conteudo


def limpar_texto(texto: str) -> str:
    # Alguns modelos (ex.: gpt-oss) inserem marcadores de citação como 【4†source】.
    return re.sub(r"【[^】]*】", "", texto).strip()


def _texto(mensagem) -> str:
    return limpar_texto(_conteudo(mensagem.content))


def _extrair_ferramentas(mensagens: list) -> list[dict]:
    """Junta cada chamada de ferramenta com o resultado devolvido."""
    resultados = {m.tool_call_id: m.content for m in mensagens
                  if isinstance(m, ToolMessage)}
    chamadas = []
    for m in mensagens:
        if isinstance(m, AIMessage):
            for chamada in m.tool_calls:
                chamadas.append({
                    "nome": chamada["name"],
                    "argumentos": chamada["args"],
                    "resultado": resultados.get(chamada["id"], ""),
                })
    return chamadas
