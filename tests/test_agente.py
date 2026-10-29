"""Testes que rodam sem internet e sem chave de API (usam um LLM falso)."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agente import Agente
from agente.ferramentas import (_resumo_openalex, calculadora, calcular_expressao,
                                classificar_fonte, data_hora_atual)
from agente.nucleo import montar_prompt


class LLMFalso(BaseChatModel):
    """Simula um LLM: na pergunta com 'conta' pede a calculadora; nas demais
    responde quantas mensagens do usuário recebeu e qual foi a primeira."""

    @property
    def _llm_type(self) -> str:
        return "falso"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        humanas = [m for m in messages if isinstance(m, HumanMessage)]
        ultima = messages[-1]
        if isinstance(ultima, HumanMessage) and "conta" in ultima.content:
            resposta = AIMessage("", tool_calls=[{
                "name": "calculadora", "args": {"expressao": "2+3*4"}, "id": "c1",
            }])
        elif isinstance(ultima, ToolMessage):
            resposta = AIMessage(f"Resultado: {ultima.content}")
        else:
            resposta = AIMessage(f"{len(humanas)}|{humanas[0].content}")
        return ChatResult(generations=[ChatGeneration(message=resposta)])


def test_memoria_mantem_contexto():
    agente = Agente(LLMFalso())
    assert agente.perguntar("Meu nome é Ana").texto == "1|Meu nome é Ana"
    # A segunda pergunta chega ao LLM junto com o histórico anterior.
    assert agente.perguntar("Qual é meu nome?").texto == "2|Meu nome é Ana"
    assert len(agente.historico()) == 4


def test_nova_conversa_esquece():
    agente = Agente(LLMFalso())
    agente.perguntar("Meu nome é Ana")
    agente.nova_conversa()
    assert agente.perguntar("Oi").texto == "1|Oi"


def test_agente_usa_ferramenta():
    resposta = Agente(LLMFalso()).perguntar("faz uma conta")
    assert resposta.texto == "Resultado: 2+3*4 = 14"
    assert resposta.ferramentas == [{
        "nome": "calculadora", "argumentos": {"expressao": "2+3*4"},
        "resultado": "2+3*4 = 14",
    }]


def test_calculadora():
    assert calcular_expressao("sqrt(144) + 2^10 / 4") == 268
    assert calcular_expressao("3,5 * 2") == 7
    assert "divisão por zero" in calculadora.invoke({"expressao": "1/0"})
    # Não executa código arbitrário
    assert "Erro" in calculadora.invoke({"expressao": "__import__('os')"})


def test_data_hora():
    assert "/20" in data_hora_atual.invoke({})
    assert "inválido" in data_hora_atual.invoke({"fuso_horario": "Lugar/Nenhum"})


def test_agente_sem_ferramentas():
    assert "tools" in Agente(LLMFalso())._grafo.nodes
    assert "tools" not in Agente(LLMFalso(), ferramentas=[])._grafo.nodes


def test_trocar_modelo_mantem_conversa():
    primeiro = Agente(LLMFalso())
    primeiro.perguntar("Meu nome é Ana")
    # Novo agente (ex.: outro modelo) com a mesma memória e o mesmo thread.
    segundo = Agente(LLMFalso(), ferramentas=[], memoria=primeiro.memoria,
                     thread_id=primeiro.thread_id)
    assert segundo.perguntar("Qual é meu nome?").texto == "2|Meu nome é Ana"


def test_prompt_cita_so_ferramentas_ligadas():
    prompt = montar_prompt([calculadora])
    assert "calculadora" in prompt
    assert "pesquisar_wikipedia" not in prompt
    assert "Ferramentas:" not in montar_prompt([])


def test_classificar_fonte():
    assert classificar_fonte("https://www.gov.br/saude/x") == "órgão oficial"
    assert classificar_fonte("https://www.cdc.gov/flu") == "órgão oficial"
    assert classificar_fonte("https://www.scielo.br/j/abc") == "universidade/ciência"
    assert classificar_fonte("https://ufmg.br/noticias") == "universidade/ciência"
    assert classificar_fonte("https://ge.globo.com/futebol") == "imprensa/checagem"
    assert classificar_fonte("https://blogqualquer.com.br/post") is None
    # Domínio que só "termina parecido" não pode passar.
    assert classificar_fonte("https://falsogov.br/golpe") is None


def test_resumo_openalex():
    assert _resumo_openalex({"Dengue": [0], "is": [1], "spreading": [2]}) == "Dengue is spreading"
    assert _resumo_openalex(None) == ""


def test_perguntar_stream_gera_eventos():
    eventos = list(Agente(LLMFalso()).perguntar_stream("faz uma conta"))
    tipos = [tipo for tipo, _ in eventos]
    assert tipos[0] == "ferramenta" and "resultado" in tipos and tipos[-1] == "fim"
    resposta = eventos[-1][1]
    assert resposta.texto == "Resultado: 2+3*4 = 14"
    assert resposta.ferramentas[0]["nome"] == "calculadora"


class LLMTeimoso(BaseChatModel):
    """Pede a calculadora para sempre enquanto tiver ferramentas disponíveis."""

    com_ferramentas: bool = False

    @property
    def _llm_type(self) -> str:
        return "teimoso"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"com_ferramentas": bool(tools)})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.com_ferramentas:
            n = sum(isinstance(m, ToolMessage) for m in messages)
            resposta = AIMessage("", tool_calls=[{
                "name": "calculadora", "args": {"expressao": "1+1"}, "id": f"c{n}"}])
        else:
            # Sem ferramentas, os resultados chegam como texto nas instruções.
            resposta = AIMessage(f"Respondi com {messages[0].content.count('[calculadora]')} resultados")
        return ChatResult(generations=[ChatGeneration(message=resposta)])


def test_limite_obriga_a_responder():
    from agente.nucleo import LIMITE_FERRAMENTAS

    resposta = Agente(LLMTeimoso(), ferramentas=[calculadora]).perguntar("calcule")
    assert len(resposta.ferramentas) == LIMITE_FERRAMENTAS
    assert resposta.texto == f"Respondi com {LIMITE_FERRAMENTAS} resultados"


def test_historico_salva_e_recupera(tmp_path):
    from agente.historico import Historico

    banco = tmp_path / "teste.db"
    historico = Historico(banco)
    agente = Agente(LLMFalso(), memoria=historico.memoria)
    agente.perguntar("Meu nome é Ana")
    historico.adicionar(agente.thread_id,
                        {"papel": "user", "texto": "Meu nome é Ana"},
                        {"papel": "assistant", "texto": "1|Meu nome é Ana", "pensamento": "x"})

    # "Fecha e abre o programa": um novo Historico no mesmo arquivo.
    reaberto = Historico(banco)
    [conversa] = reaberto.listar()
    assert conversa["titulo"] == "Meu nome é Ana"
    assert reaberto.mensagens(conversa["id"])[1]["pensamento"] == "x"
    # O agente continua lembrando da conversa salva.
    continuacao = Agente(LLMFalso(), memoria=reaberto.memoria, thread_id=conversa["id"])
    assert continuacao.perguntar("Qual é meu nome?").texto == "2|Meu nome é Ana"

    reaberto.renomear(conversa["id"], "Apresentação")
    assert reaberto.listar("apresent")[0]["titulo"] == "Apresentação"
    reaberto.apagar(conversa["id"])
    assert reaberto.listar() == [] and reaberto.mensagens(conversa["id"]) == []
    assert Agente(LLMFalso(), memoria=reaberto.memoria,
                  thread_id=conversa["id"]).perguntar("Oi").texto == "1|Oi"


def test_titulo_automatico():
    from agente.historico import titulo_automatico

    assert titulo_automatico("  Oi,   tudo bem? ") == "Oi, tudo bem?"
    longo = titulo_automatico("quanto que o mundo inteiro investe em justiça nos seus países?")
    assert len(longo) <= 46 and longo.endswith("…")


def test_historico_separa_por_dono(tmp_path):
    from agente.historico import Historico

    h = Historico(tmp_path / "teste.db")
    h.adicionar("c1", {"papel": "user", "texto": "da Ana"}, dono="ana")
    h.adicionar("c2", {"papel": "user", "texto": "do Bruno"}, dono="bruno")
    assert [c["titulo"] for c in h.listar(dono="ana")] == ["da Ana"]
    assert h.mensagens("c1", "bruno") == [] and h.titulo("c1", "bruno") is None
    h.apagar("c1", "bruno")    # o Bruno não consegue apagar a conversa da Ana
    h.renomear("c1", "x", "bruno")
    assert h.listar(dono="ana")[0]["titulo"] == "da Ana"
