"""Ferramentas (tools) que o agente pode decidir usar para responder melhor.

Cada função decorada com @tool vira uma ferramenta: o LLM lê o nome, a
docstring e os parâmetros para decidir quando e como chamá-la.
"""

import ast
import math
import operator
import os
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from langchain_core.tools import BaseTool, tool

HEADERS = {"User-Agent": "AgenteIA-Faculdade/1.0 (projeto academico)"}
TIMEOUT = 10

# ---------------------------------------------------------------------------
# Calculadora segura (sem usar eval)
# ---------------------------------------------------------------------------
_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_FUNCOES = {
    nome: getattr(math, nome)
    for nome in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp",
                 "floor", "ceil", "factorial", "radians", "degrees")
}
_FUNCOES.update({"abs": abs, "round": round})
_CONSTANTES = {"pi": math.pi, "e": math.e}


def _avaliar(no):
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)):
        return no.value
    if isinstance(no, ast.BinOp) and type(no.op) in _OPERADORES:
        esquerda, direita = _avaliar(no.left), _avaliar(no.right)
        if isinstance(no.op, ast.Pow) and abs(direita) > 1000:
            raise ValueError("expoente grande demais")
        return _OPERADORES[type(no.op)](esquerda, direita)
    if isinstance(no, ast.UnaryOp) and type(no.op) in _OPERADORES:
        return _OPERADORES[type(no.op)](_avaliar(no.operand))
    if isinstance(no, ast.Name) and no.id in _CONSTANTES:
        return _CONSTANTES[no.id]
    if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
            and no.func.id in _FUNCOES and not no.keywords):
        return _FUNCOES[no.func.id](*[_avaliar(a) for a in no.args])
    raise ValueError("expressão não suportada")


def calcular_expressao(expressao: str) -> float:
    """Avalia uma expressão matemática de forma segura."""
    expressao = expressao.replace("^", "**").replace(",", ".")
    return _avaliar(ast.parse(expressao, mode="eval").body)


@tool
def calculadora(expressao: str) -> str:
    """Calcula expressões matemáticas com precisão. Use sempre que precisar
    fazer contas. Aceita + - * / // % ** (potência), parênteses, as constantes
    pi e e, e as funções sqrt, sin, cos, tan, log, log10, log2, exp, floor,
    ceil, factorial, radians, degrees, abs e round.
    Exemplo de entrada: "sqrt(144) + 2**10 / 4"."""
    try:
        resultado = calcular_expressao(expressao)
    except ZeroDivisionError:
        return "Erro: divisão por zero."
    except Exception as erro:  # noqa: BLE001 - devolvemos o erro ao LLM
        return f"Erro ao calcular '{expressao}': {erro}"
    if isinstance(resultado, float) and resultado.is_integer():
        resultado = int(resultado)
    return f"{expressao} = {resultado}"


# ---------------------------------------------------------------------------
# Data e hora
# ---------------------------------------------------------------------------
_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
         "sexta-feira", "sábado", "domingo"]


@tool
def data_hora_atual(fuso_horario: str = "America/Sao_Paulo") -> str:
    """Retorna a data, a hora e o dia da semana atuais. Use quando o usuário
    perguntar que dia é hoje, que horas são, ou precisar calcular datas.
    O parâmetro fuso_horario segue o padrão IANA (ex.: "America/Sao_Paulo",
    "Europe/Lisbon", "Asia/Tokyo")."""
    try:
        agora = datetime.now(ZoneInfo(fuso_horario))
    except Exception:  # noqa: BLE001
        return f"Fuso horário inválido: {fuso_horario}"
    return (f"{_DIAS[agora.weekday()]}, {agora:%d/%m/%Y}, "
            f"{agora:%H:%M:%S} (fuso {fuso_horario})")


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------
@tool
def pesquisar_wikipedia(termo: str) -> str:
    """Pesquisa um assunto na Wikipédia em português e retorna um resumo.
    Serve para visão geral de conceitos, biografias e lugares. Qualquer pessoa
    pode editar a Wikipédia, então não é a melhor fonte para saúde, notícias
    ou dados que precisam ser exatos."""
    try:
        busca = requests.get(
            "https://pt.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": termo,
                    "format": "json", "srlimit": 1},
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
        resultados = busca.get("query", {}).get("search", [])
        if not resultados:
            return f"Nenhum resultado na Wikipédia para '{termo}'."
        titulo = resultados[0]["title"]
        resumo = requests.get(
            "https://pt.wikipedia.org/api/rest_v1/page/summary/"
            + requests.utils.quote(titulo.replace(" ", "_")),
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
    except requests.RequestException as erro:
        return f"Erro ao acessar a Wikipédia: {erro}"
    texto = resumo.get("extract") or "Resumo indisponível."
    link = resumo.get("content_urls", {}).get("desktop", {}).get("page", "")
    return f"{titulo}: {texto}\nFonte: {link}"


# ---------------------------------------------------------------------------
# Clima (Open-Meteo, gratuito e sem chave)
# ---------------------------------------------------------------------------
_CODIGOS_CLIMA = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado",
    3: "nublado", 45: "neblina", 48: "neblina com geada",
    51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva",
    82: "pancadas de chuva fortes", 95: "trovoadas",
    96: "trovoadas com granizo", 99: "trovoadas fortes com granizo",
}


@tool
def previsao_do_tempo(cidade: str) -> str:
    """Consulta o clima atual e a previsão dos próximos 3 dias de uma cidade.
    Use quando o usuário perguntar sobre tempo, temperatura ou chuva."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": cidade, "count": 1, "language": "pt"},
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
        if not geo.get("results"):
            return f"Cidade '{cidade}' não encontrada."
        local = geo["results"][0]
        dados = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": local["latitude"], "longitude": local["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "timezone": "auto", "forecast_days": 3,
            },
            headers=HEADERS, timeout=TIMEOUT,
        ).json()
    except requests.RequestException as erro:
        return f"Erro ao consultar o clima: {erro}"

    atual = dados["current"]
    linhas = [
        f"{local['name']}, {local.get('admin1', '')} - {local.get('country', '')}",
        f"Agora: {atual['temperature_2m']}°C, "
        f"{_CODIGOS_CLIMA.get(atual['weather_code'], 'condição desconhecida')}, "
        f"umidade {atual['relative_humidity_2m']}%, vento {atual['wind_speed_10m']} km/h",
    ]
    diario = dados["daily"]
    for i, dia in enumerate(diario["time"]):
        data = datetime.strptime(dia, "%Y-%m-%d").strftime("%d/%m")
        linhas.append(
            f"{data}: mín {diario['temperature_2m_min'][i]}°C / "
            f"máx {diario['temperature_2m_max'][i]}°C, "
            f"{_CODIGOS_CLIMA.get(diario['weather_code'][i], '?')}, "
            f"chance de chuva {diario['precipitation_probability_max'][i]}%"
        )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Busca na web restrita a fontes confiáveis
# ---------------------------------------------------------------------------
FONTES_CONFIAVEIS = {
    "órgão oficial": (
        "gov.br", "gov", "gov.uk", "gov.pt", "europa.eu", "leg.br", "jus.br",
        "mp.br", "who.int", "paho.org", "un.org", "unesco.org", "unicef.org",
        "worldbank.org", "imf.org", "oecd.org", "fiocruz.br", "embrapa.br",
        "inpe.br", "ibge.gov.br",
    ),
    "universidade/ciência": (
        "edu", "edu.br", "ac.uk", "usp.br", "unicamp.br", "unesp.br", "unb.br",
        "unifesp.br", "fgv.br", "scielo.org", "scielo.br", "nature.com",
        "science.org", "sciencedirect.com", "springer.com", "thelancet.com",
        "nejm.org", "bmj.com", "arxiv.org", "plos.org", "britannica.com",
        "nationalgeographic.com", "nationalgeographicbrasil.com",
    ),
    "imprensa/checagem": (
        "globo.com", "folha.uol.com.br", "noticias.uol.com.br", "estadao.com.br",
        "agenciabrasil.ebc.com.br", "veja.abril.com.br", "nexojornal.com.br",
        "cnnbrasil.com.br", "correiobraziliense.com.br", "bbc.com", "bbc.co.uk",
        "reuters.com", "apnews.com", "theguardian.com", "nytimes.com",
        "elpais.com", "dw.com", "aosfatos.org", "lupa.uol.com.br",
    ),
}
# Universidades federais e PUCs (ufmg.br, ufrj.br, puc-rio.br, ...).
_UNIVERSIDADES_BR = re.compile(r"(^|\.)(uf[a-z]{1,6}|utfpr|puc[a-z-]*)\.br$")
# Usado na 2ª busca, quando a 1ª trouxe poucas fontes confiáveis.
_SITES_PRIORITARIOS = ("gov.br", "scielo.br", "edu.br", "fiocruz.br",
                       "bbc.com", "globo.com", "folha.uol.com.br")


def classificar_fonte(url: str) -> str | None:
    """Diz o tipo da fonte (ex.: "órgão oficial") ou None se não for confiável."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for tipo, dominios in FONTES_CONFIAVEIS.items():
        if any(host == d or host.endswith("." + d) for d in dominios):
            return tipo
    if _UNIVERSIDADES_BR.search(host):
        return "universidade/ciência"
    return None


def _buscar_web(consulta: str) -> list[dict]:
    from ddgs import DDGS  # importado aqui para não pesar no início do app

    try:
        return DDGS(timeout=TIMEOUT).text(consulta, region="br-pt", max_results=10)
    except Exception:  # noqa: BLE001 - "sem resultados" também vira exceção
        return []


@tool
def pesquisar_fontes_confiaveis(consulta: str) -> str:
    """Pesquisa na web, mas só aceita resultados de fontes confiáveis: órgãos
    oficiais (gov.br, OMS, IBGE), universidades, revistas científicas e
    imprensa profissional/agências de checagem. Sites desconhecidos, blogs e
    fóruns são descartados. Use para fatos atuais, notícias, saúde, leis,
    economia, dados oficiais e qualquer assunto em que a precisão importa."""
    achados, vistos = [], set()
    filtro_sites = " OR ".join(f"site:{s}" for s in _SITES_PRIORITARIOS)
    for busca in (consulta, f"{consulta} ({filtro_sites})"):
        for r in _buscar_web(busca):
            url = r.get("href", "")
            tipo = classificar_fonte(url)
            if tipo and url not in vistos:
                vistos.add(url)
                achados.append((tipo, r))
        if len(achados) >= 3:
            break
    if not achados:
        return (f"Nenhuma fonte confiável encontrada para '{consulta}'. Avise o "
                "usuário em vez de usar fontes duvidosas.")
    linhas = []
    for i, (tipo, r) in enumerate(achados[:4], start=1):
        dominio = urlparse(r["href"]).hostname.removeprefix("www.")
        linhas.append(f"{i}. {r.get('title', '')[:120]} [{dominio} · {tipo}]\n"
                      f"   {r.get('body', '')[:300]}\n   Fonte: {r['href']}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Artigos científicos (OpenAlex, gratuito; chave opcional)
# ---------------------------------------------------------------------------
def _resumo_openalex(indice: dict | None, limite: int = 250) -> str:
    """O OpenAlex guarda o resumo como {palavra: [posições]}; aqui remontamos."""
    if not indice:
        return ""
    posicoes = {p: palavra for palavra, ps in indice.items() for p in ps}
    texto = " ".join(posicoes[p] for p in sorted(posicoes))
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + "…"


@tool
def pesquisar_artigos_cientificos(tema: str) -> str:
    """Busca artigos científicos publicados (revisados por pares) no OpenAlex,
    base aberta com centenas de milhões de publicações. Use quando o usuário
    pedir estudos, evidências, pesquisas acadêmicas ou o que a ciência diz
    sobre um tema. Dica: pesquise em inglês para achar mais artigos."""
    params = {
        "search": tema, "per_page": 4, "filter": "type:article|review",
        "select": "id,doi,title,publication_year,cited_by_count,"
                  "authorships,primary_location,abstract_inverted_index",
    }
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.getenv("OPENALEX_API_KEY")
    try:
        dados = requests.get("https://api.openalex.org/works", params=params,
                             headers=HEADERS, timeout=TIMEOUT).json()
    except (requests.RequestException, ValueError) as erro:
        return f"Erro ao acessar o OpenAlex: {erro}"
    artigos = dados.get("results", [])
    if not artigos:
        return f"Nenhum artigo encontrado para '{tema}'."
    linhas = []
    for i, a in enumerate(artigos, start=1):
        autores = [x["author"]["display_name"] for x in a.get("authorships", [])[:3]]
        if len(a.get("authorships", [])) > 3:
            autores.append("et al.")
        revista = ((a.get("primary_location") or {}).get("source") or {}).get(
            "display_name", "revista não informada")
        linhas.append(
            f"{i}. {a.get('title')} ({a.get('publication_year')}) — "
            f"{', '.join(autores) or 'autores não informados'}. {revista}. "
            f"Citado {a.get('cited_by_count', 0)} vezes.\n"
            f"   Resumo: {_resumo_openalex(a.get('abstract_inverted_index')) or 'indisponível'}\n"
            f"   Fonte: {a.get('doi') or a.get('id')}"
        )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Catálogo: metadados usados pela interface e pelo prompt do agente
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InfoFerramenta:
    ferramenta: BaseTool
    titulo: str
    icone: str
    descricao: str  # mostrada ao usuário na tela de configurações
    guia: str       # instrução para o LLM de quando usar
    grupo: str      # "Pesquisa" ou "Utilidades"


CATALOGO = {info.ferramenta.name: info for info in [
    InfoFerramenta(
        pesquisar_fontes_confiaveis, "Fontes confiáveis na web", "🛡️",
        "Busca na internet, mas só aceita órgãos oficiais, universidades, "
        "revistas científicas e imprensa profissional.",
        "primeira escolha para fatos, notícias, saúde, leis, economia e dados oficiais.",
        "Pesquisa"),
    InfoFerramenta(
        pesquisar_artigos_cientificos, "Artigos científicos", "🔬",
        "Estudos revisados por pares no OpenAlex, com autores, revista e "
        "número de citações.",
        "quando pedirem estudos, evidências ou o que a ciência diz sobre algo.",
        "Pesquisa"),
    InfoFerramenta(
        pesquisar_wikipedia, "Wikipédia", "📚",
        "Enciclopédia colaborativa: ótima para visão geral, mas qualquer "
        "pessoa pode editar.",
        "só para visão geral de conceitos e biografias; se houver ferramenta "
        "de fontes confiáveis, prefira ela para confirmar fatos importantes.",
        "Pesquisa"),
    InfoFerramenta(
        calculadora, "Calculadora", "🧮",
        "Faz contas exatas (LLMs costumam errar aritmética).",
        "para qualquer conta.", "Utilidades"),
    InfoFerramenta(
        data_hora_atual, "Data e hora", "🕒",
        "Informa a data e a hora reais (o modelo não sabe que dia é hoje).",
        "para datas, horários e dia da semana.", "Utilidades"),
    InfoFerramenta(
        previsao_do_tempo, "Previsão do tempo", "🌦️",
        "Clima atual e previsão de 3 dias pela Open-Meteo.",
        "para clima, temperatura e chuva.", "Utilidades"),
]}

FERRAMENTAS = [info.ferramenta for info in CATALOGO.values()]
