"""
==============================================================================
J.A.R.V.I.S. - Assistente Interativo de Configuração e Instalação (Setup Wizard)
==============================================================================
Permite ao usuário escolher o motor de IA padrão (Ollama Local, Gemini,
ChatGPT ou Claude) e configurar suas credenciais na primeira instalação
(seja no PC atual, em um MiniPC ou servidor dedicado).
Pode ser executado a qualquer momento para alterar o motor.
==============================================================================
"""

import os
import sys
import shutil

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
ENV_EXAMPLE = os.path.join(BASE_DIR, ".env.example")

def banner():
    print("=" * 68)
    print("      J.A.R.V.I.S. - CONFIGURAÇÃO INICIAL DO SISTEMA & MOTOR DE IA    ")
    print("=" * 68)
    print(" Bem-vindo! Este assistente irá configurar o cérebro do J.A.R.V.I.S.\n")

def ler_ou_criar_env():
    if not os.path.exists(ENV_PATH):
        if os.path.exists(ENV_EXAMPLE):
            shutil.copy(ENV_EXAMPLE, ENV_PATH)
            print("📄 Arquivo .env criado a partir de .env.example com sucesso!\n")
        else:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write("# Configuração JARVIS\n")

def atualizar_env(chave: str, valor: str):
    linhas = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            linhas = f.readlines()

    achou = False
    novas_linhas = []
    for linha in linhas:
        if linha.strip().startswith(f"{chave}="):
            novas_linhas.append(f"{chave}={valor}\n")
            achou = True
        else:
            novas_linhas.append(linha)

    if not achou:
        novas_linhas.append(f"{chave}={valor}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(novas_linhas)

def obter_valor_env(chave: str, default: str = "") -> str:
    if not os.path.exists(ENV_PATH):
        return default
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for linha in f:
            if linha.strip().startswith(f"{chave}="):
                return linha.strip().split("=", 1)[1]
    return default

def wizard():
    banner()
    ler_ou_criar_env()

    modo_atual = obter_valor_env("AI_MODE", "hybrid")
    prov_atual = obter_valor_env("CLOUD_AI_PROVIDER", "gemini")
    modelo_local_atual = obter_valor_env("LOCAL_AI_MODEL", "llama3.2")

    print(f"Estado Atual Configurado:")
    print(f" • Modo de Operação: {modo_atual.upper()}")
    print(f" • Provedor na Nuvem: {prov_atual.upper()}")
    print(f" • Modelo Local: {modelo_local_atual}\n")

    print("-" * 68)
    print("PASSO 1: Escolha a arquitetura de operação do J.A.R.V.I.S.:")
    print(" [1] Híbrido (RECOMENDADO):")
    print("     Tarefas rápidas (IoT, Volume, Braço, Status) no modelo local;")
    print("     Tarefas complexas, visão e raciocínio avançado no motor online.")
    print(" [2] Nuvem Exclusiva:")
    print("     Todas as solicitações passam pelo provedor online escolhido.")
    print(" [3] 100% Local / Offline:")
    print("     Privacidade total via Ollama (sem conexão de internet necessária).")
    print("-" * 68)

    escolha_modo = input("Digite o número da sua opção [1, 2 ou 3] (Padrão 1): ").strip()
    if escolha_modo == "2":
        novo_modo = "cloud_only"
    elif escolha_modo == "3":
        novo_modo = "local_only"
    else:
        novo_modo = "hybrid"

    atualizar_env("AI_MODE", novo_modo)
    print(f"✅ Modo de operação definido como: {novo_modo.upper()}\n")

    # Se for híbrido ou nuvem, escolhe o motor de nuvem
    if novo_modo in ["hybrid", "cloud_only"]:
        print("-" * 68)
        print("PASSO 2: Escolha o motor de Inteligência Artificial online principal:")
        print(" [1] Google Gemini (Padrão - Muito rápido, excelente com ferramentas)")
        print(" [2] OpenAI ChatGPT (Modelos GPT-4o / GPT-4o-mini)")
        print(" [3] Anthropic Claude (Claude 3.5 Sonnet / Claude 3.5 Haiku)")
        print("-" * 68)

        escolha_motor = input("Escolha o motor online [1, 2 ou 3] (Padrão 1): ").strip()
        if escolha_motor == "2":
            novo_prov = "openai"
            nome_prov = "OpenAI (ChatGPT)"
            env_key = "OPENAI_API_KEY"
        elif escolha_motor == "3":
            novo_prov = "claude"
            nome_prov = "Anthropic (Claude)"
            env_key = "ANTHROPIC_API_KEY"
        else:
            novo_prov = "gemini"
            nome_prov = "Google Gemini"
            env_key = "GEMINI_API_KEY"

        atualizar_env("CLOUD_AI_PROVIDER", novo_prov)
        print(f"✅ Motor online definido: {nome_prov}")

        chave_atual = obter_valor_env(env_key, "")
        mascara = f"{chave_atual[:8]}...{chave_atual[-4:]}" if len(chave_atual) > 12 else "NÃO CONFIGURADA"
        print(f"\nChave de API atual ({env_key}): {mascara}")
        nova_chave = input(f"Deseja inserir/atualizar sua chave de API para {nome_prov}? (ENTER para manter): ").strip()
        if nova_chave:
            atualizar_env(env_key, nova_chave)
            print(f"🔑 Chave de API {env_key} salva com sucesso!")

    # Se for híbrido ou local, escolhe o modelo do Ollama
    if novo_modo in ["hybrid", "local_only"]:
        print("\n" + "-" * 68)
        print("PASSO 3: Configuração do Modelo Local (Ollama):")
        print(f"Modelo configurado atualmente: {modelo_local_atual}")
        print("Sugestões: llama3.2 (leve e rápido), qwen2.5:3b, mistral, phi-3")
        novo_modelo = input("Digite o nome do modelo Ollama (ENTER para manter): ").strip()
        if novo_modelo:
            atualizar_env("LOCAL_AI_MODEL", novo_modelo)
            print(f"✅ Modelo local definido como: {novo_modelo}")

    print("\n" + "=" * 68)
    print("  🎉 CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 68)
    print(" Você pode reconfigurar ou alternar o motor a qualquer momento:")
    print(" 1. Executando este script: python setup_jarvis.py")
    print(" 2. Ou falando/digitando para o JARVIS em execução:")
    print("    'Mudar motor para chatgpt' | 'Mudar motor para gemini' | 'Mudar motor para claude'")
    print("    'Mudar para modo hibrido' | 'Mudar para modo local'")
    print("=" * 68 + "\n")

if __name__ == "__main__":
    wizard()
