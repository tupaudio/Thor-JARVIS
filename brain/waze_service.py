"""
Módulo de Integração com Waze e Rotas OSRM para o J.A.R.V.I.S.
Funciona no Linux Debian (headless).
Calcula tempo estimado de viagem, distância em km e rotas em tempo real.
"""

import os
import sys
import logging
import requests
from geopy.geocoders import Nominatim


class WazeService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="jarvis_assistant_navigation/2.0")
        self.env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "JARVIS-Navigation/2.0"})

    def salvar_endereco_favorito(self, tipo: str, endereco: str) -> str:
        """Salva o endereço de casa ou trabalho no arquivo .env."""
        chave = "HOME_ADDRESS" if "casa" in tipo.lower() else "WORK_ADDRESS"
        os.environ[chave] = endereco
        
        linhas = []
        achou = False
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                linhas = f.readlines()

        novas_linhas = []
        for linha in linhas:
            if linha.startswith(f"{chave}="):
                novas_linhas.append(f"{chave}={endereco}\n")
                achou = True
            else:
                novas_linhas.append(linha)
                
        if not achou:
            novas_linhas.append(f"{chave}={endereco}\n")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)

        nome_tipo = "casa" if chave == "HOME_ADDRESS" else "trabalho"
        return f"Endereço de {nome_tipo} configurado com sucesso como: '{endereco}', senhor."

    def _resolver_apelido(self, local: str) -> tuple:
        """Substitui termos como 'casa' ou 'trabalho' pelo endereço configurado."""
        termo = local.lower().strip()
        if termo in ["casa", "minha casa", "minha residência", "home"]:
            casa = os.getenv("HOME_ADDRESS")
            if not casa:
                return None, "O senhor ainda não cadastrou seu endereço de casa. Diga: 'Jarvis, cadastre meu endereço de casa como [Rua, Cidade]'."
            return casa, "Casa"
        elif termo in ["trabalho", "meu trabalho", "escritório", "oficina", "work"]:
            trab = os.getenv("WORK_ADDRESS")
            if not trab:
                return None, "O senhor ainda não cadastrou seu endereço de trabalho. Diga: 'Jarvis, cadastre meu endereço de trabalho como [Rua, Cidade]'."
            return trab, "Trabalho"
        return local, local

    def _obter_coordenadas(self, endereco: str) -> tuple:
        """Converte endereço para tupla (lat, lon) usando Nominatim/OpenStreetMap."""
        try:
            busca = endereco if "brasil" in endereco.lower() else f"{endereco}, Brasil"
            local = self.geolocator.geocode(busca, timeout=8)
            if local:
                return (local.latitude, local.longitude)
        except Exception as e:
            print(f"⚠️ [GEO] Erro ao geocodificar '{endereco}': {e}")
        return None

    def calcular_rota(self, destino: str, origem: str = "") -> str:
        """
        Calcula a rota em tempo real usando motor de roteamento rodoviário global (OSRM).
        """
        if not origem or origem.strip() == "":
            origem = "casa"

        origem_real, nome_origem = self._resolver_apelido(origem)
        if not origem_real:
            return nome_origem

        destino_real, nome_destino = self._resolver_apelido(destino)
        if not destino_real:
            return nome_destino

        print(f"\n🚗 [ROTAS] Calculando trajeto de '{nome_origem}' até '{nome_destino}'...")

        coord_origem = self._obter_coordenadas(origem_real)
        coord_destino = self._obter_coordenadas(destino_real)

        if not coord_origem or not coord_destino:
            return f"Não consegui localizar geograficamente os pontos '{nome_origem}' ou '{nome_destino}'. Por favor informe nomes mais específicos ou cidades."

        lat1, lon1 = coord_origem
        lat2, lon2 = coord_destino

        # Consulta API de roteamento OSRM (motor padrão global OpenStreetMap)
        try:
            url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    r = data["routes"][0]
                    duracao_min = int(round(r.get("duration", 0) / 60))
                    distancia_km = round(r.get("distance", 0) / 1000, 1)

                    if duracao_min >= 60:
                        horas = duracao_min // 60
                        min_rest = duracao_min % 60
                        tempo_str = f"{horas}h e {min_rest} minutos" if min_rest > 0 else f"{horas} horas"
                    else:
                        tempo_str = f"{duracao_min} minutos"

                    resposta = (
                        f"Calculando o trajeto em tempo real, a distância de {nome_origem} até {nome_destino} "
                        f"é de aproximadamente {distancia_km} km. O tempo estimado de deslocamento é de {tempo_str}, senhor."
                    )
                    print(f"✅ [ROTAS SUCESSO] {distancia_km} km | {tempo_str}")
                    return resposta
        except Exception as e:
            print(f"⚠️ [ROTAS] Falha no cálculo: {e}")

        return f"Não foi possível calcular a rota entre '{nome_origem}' e '{nome_destino}' no momento, senhor."

waze_service = WazeService()
