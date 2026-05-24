"""
Teste rápido da TIAGA no terminal.
Rode com: python teste_rapido.py
"""

from agent import chat_com_luna, iniciar_conversa

def main():
    print("\n" + "="*60)
    print("  TIAGA — Teste no Terminal")
    print("="*60)
    print("\nDigite 'sair' para encerrar.\n")

    historico = []

    # Mensagem inicial
    print(f"TIAGA: {iniciar_conversa()}\n")

    while True:
        entrada = input("Você: ").strip()

        if entrada.lower() in ("sair", "exit", "quit"):
            print("\nTIAGA: Até logo! Foi um prazer te ajudar! 🌸\n")
            break

        if not entrada:
            continue

        historico.append({"role": "user", "content": entrada})

        print("\nTIAGA: ", end="", flush=True)
        resposta = chat_com_luna(historico)
        print(resposta)
        print()

        historico.append({"role": "assistant", "content": resposta})

if __name__ == "__main__":
    main()
