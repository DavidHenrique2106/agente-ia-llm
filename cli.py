"""Versão de terminal do agente (alternativa à interface web).

Execute com:  python cli.py            (Groq, modelo padrão)
              python cli.py --provedor ollama --modelo llama3.2
"""

import argparse

from dotenv import load_dotenv

from agente import Agente, criar_modelo


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Converse com o agente Assis.")
    parser.add_argument("--provedor", choices=["groq", "ollama"], default="groq")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--sem-ferramentas", action="store_true")
    args = parser.parse_args()

    modelo = args.modelo or ("openai/gpt-oss-120b" if args.provedor == "groq" else "llama3.2")
    agente = Agente(criar_modelo(args.provedor, modelo),
                    ferramentas=[] if args.sem_ferramentas else None)

    print(f"🤖 Assis ({modelo}). Comandos: /nova = nova conversa, /sair = encerrar.\n")
    while True:
        try:
            pergunta = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pergunta:
            continue
        if pergunta.lower() in {"/sair", "sair", "exit", "quit"}:
            break
        if pergunta.lower() == "/nova":
            agente.nova_conversa()
            print("— Nova conversa iniciada —\n")
            continue
        try:
            resposta = agente.perguntar(pergunta)
        except Exception as erro:  # noqa: BLE001
            print(f"[erro] {erro}\n")
            continue
        for f in resposta.ferramentas:
            print(f"   🔧 {f['nome']}({f['argumentos']})")
        print(f"Assis: {resposta.texto}\n")
    print("Até logo! 👋")


if __name__ == "__main__":
    main()
