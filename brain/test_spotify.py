"""
Script de Teste de Autenticação e Dispositivos do Spotify do J.A.R.V.I.S.
"""

import os
import sys
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from spotify_service import spotify_service

print("="*60)
print("       J.A.R.V.I.S. - DIAGNÓSTICO DO SPOTIFY")
print("="*60)

print(f"\n1. Verificando Credenciais no .env...")
print(f"• Client ID: {spotify_service.client_id[:8]}...{spotify_service.client_id[-4:] if spotify_service.client_id else 'NÃO'}")
print(f"• Redirect URI: {spotify_service.redirect_uri}")

print("\n2. Tentando autenticar com o Spotify...")
print("👉 O navegador será aberto automaticamente para você clicar em 'Concordo'.")
print("Aguardando confirmação de login no navegador...\n", flush=True)
sp = spotify_service._obter_cliente()

if sp:
    try:
        user_profile = sp.current_user()
        print(f"\n✅ [SUCESSO] Autenticado com sucesso no Spotify!")
        print(f"• Usuário: {user_profile.get('display_name')}")
        print(f"• Tipo de Conta: {user_profile.get('product')}")
        print(f"• País: {user_profile.get('country')}")
        
        print("\n3. Verificando Dispositivos Ativos...")
        devices = sp.devices().get("devices", [])
        if devices:
            print(f"Encontrado(s) {len(devices)} dispositivo(s):")
            for d in devices:
                ativo = "🟢 [ATIVO]" if d.get("is_active") else "⚪ [EM ESPERA]"
                print(f"• {ativo} {d.get('name')} (Tipo: {d.get('type')}, Volume: {d.get('volume_percent')}%)")
        else:
            print("⚠️ Nenhum dispositivo Spotify com reprodução aberta no momento.")
            print("💡 Dica: Abra o aplicativo do Spotify no seu computador ou celular para controlar o som.")

        print("\n4. Verificando Faixa Atual...")
        print(spotify_service.obter_musica_atual())
        
    except Exception as e:
        print(f"\n❌ Erro durante chamada da API do Spotify: {e}")
else:
    print("\n❌ Não foi possível inicializar o cliente do Spotify. Verifique o arquivo .env.")
