"""
Módulo de Integração com o Waze em Tempo Real para o JARVIS.
Permite salvar endereços favoritos (Casa, Trabalho) e calcular rotas ao vivo.
"""

import os
import sys
import logging
from geopy.geocoders import Nominatim
import WazeRouteCalculator

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Silenciar logs internos do Waze
logger = logging.getLogger('WazeRouteCalculator.WazeRouteCalculator')
logger.setLevel(logging.WARNING)

class WazeService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="jarvis_assistant_route")
        self.env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    def salvar_endereco_favorito(self, tipo: str, endereco: str) -> str:
        """
        Salva o endereço de casa ou trabalho no arquivo .env para persistência.
        
        Args:
            tipo: 'casa' ou 'trabalho'.
            endereco: Endereço completo (Rua, Número, Bairro, Cidade - UF).
        """
        chave = "HOME_ADDRESS" if "casa" in tipo.lower() else "WORK_ADDRESS"
        os.environ[chave] = endereco
        
        # Atualizar ou adicionar no arquivo .env
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

        print(f"📍 [LOCAL SALVO] {chave}: {endereco}")
        nome_tipo = "casa" if chave == "HOME_ADDRESS" else "trabalho"
        return f"Endereço de {nome_tipo} configurado com sucesso como: '{endereco}', senhor."

    def _resolver_apelido(self, local: str) -> tuple[str, str]:
        """Substitui termos como 'casa' ou 'trabalho' pelo endereço real."""
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

    def _obter_coordenadas(self, endereco: str) -> str:
        """Converte um endereço em coordenadas 'lat,lon'."""
        try:
            busca = endereco if "brasil" in endereco.lower() else f"{endereco}, Brasil"
            local = self.geolocator.geocode(busca, timeout=8)
            if local:
                return f"{local.latitude},{local.longitude}"
        except Exception:
            pass
        return endereco

    def calcular_rota(self, destino: str, origem: str = "") -> str:
        """
        Calcula o tempo de viagem e a distância em tempo real via Waze.
        """
        # Se não especificou origem, assume a casa do usuário por padrão
        if not origem or origem.strip() == "":
            origem = "casa"

        origem_real, nome_origem = self._resolver_apelido(origem)
        if not origem_real:
            return nome_origem

        destino_real, nome_destino = self._resolver_apelido(destino)
        if not destino_real:
            return nome_destino

        print(f"\n🚗 [WAZE] Calculando trajeto de '{origem_real}' até '{destino_real}' com trânsito ao vivo...")
        
        c_origem = self._obter_coordenadas(origem_real)
        c_destino = self._obter_coordenadas(destino_real)

        regioes = ['EU', 'US', 'IL']
        resultado = None

        for reg in regioes:
            try:
                calc = WazeRouteCalculator.WazeRouteCalculator(
                    c_origem, c_destino, region=reg, log_lvl=logging.WARNING
                )
                tempo_min, distancia_km = calc.calc_route_info()
                resultado = (tempo_min, distancia_km)
                break
            except Exception:
                continue

        if not resultado:
            return f"Não foi possível calcular uma rota no Waze entre '{nome_origem}' e '{nome_destino}', senhor."

        tempo_min, distancia_km = resultado
        tempo_min = int(round(tempo_min))
        distancia_km = round(distancia_km, 1)

        if tempo_min >= 60:
            horas = tempo_min // 60
            min_rest = tempo_min % 60
            tempo_formatado = f"{horas}h e {min_rest} minutos" if min_rest > 0 else f"{horas} horas"
        else:
            tempo_formatado = f"{tempo_min} minutos"

        resposta = (
            f"Consultando o Waze em tempo real, a distância de {nome_origem} até {nome_destino} "
            f"é de aproximadamente {distancia_km} km. Com o trânsito atual, o tempo estimado de viagem é de {tempo_formatado}, senhor."
        )
        print(f"✅ [WAZE SUCESSO] {distancia_km} km | {tempo_formatado}")
        return resposta

waze_service = WazeService()
