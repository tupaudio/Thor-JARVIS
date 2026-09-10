"""
Módulo de Previsão do Tempo e Clima em Tempo Real para o JARVIS.
Utiliza Open-Meteo (API aberta e gratuita de alta precisão) + Geopy para coordenadas.
"""

import os
import sys
import requests
from geopy.geocoders import Nominatim

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Mapeamento dos códigos WMO da Open-Meteo para descrições em português
WMO_CODES = {
    0: "céu limpo e ensolarado",
    1: "predominantemente limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "nevoeiro",
    48: "nevoeiro com geada",
    51: "garoa leve",
    53: "garoa moderada",
    55: "garoa densa",
    61: "chuva fraca",
    63: "chuva moderada",
    65: "chuva forte",
    80: "pancadas de chuva leves",
    81: "pancadas de chuva moderadas",
    82: "pancadas de chuva violentas",
    95: "tempestade com trovoadas",
    96: "tempestade com granizo leve",
    99: "tempestade severa com granizo"
}

class WeatherService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="jarvis_weather_agent")

    def _obter_coordenadas(self, local: str):
        """Converte o nome da cidade em latitude e longitude."""
        try:
            busca = local if "brasil" in local.lower() else f"{local}, Brasil"
            resultado = self.geolocator.geocode(busca, timeout=8)
            if resultado:
                return resultado.latitude, resultado.longitude, resultado.address.split(",")[0]
        except Exception:
            pass
        # Fallback para o endereço de casa salvo ou Serra/Vitória - ES
        return -20.1878, -40.2447, "Serra/Vitória - ES"

    def consultar_clima(self, local: str = "") -> str:
        """
        Consulta o clima atual e previsão para o dia.
        
        Args:
            local: Nome da cidade ou bairro (ex: 'Vitória', 'Serra', 'São Paulo').
                   Se omitido, consulta o local de residência do usuário.
        """
        if not local or local.strip() == "":
            local = os.getenv("HOME_ADDRESS", "Serra, Espírito Santo")

        print(f"\n🌤️ [CLIMA] Buscando dados meteorológicos para '{local}'...")
        lat, lon, nome_cidade = self._obter_coordenadas(local)

        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&"
            f"daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
            f"timezone=America/Sao_Paulo"
        )

        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                return f"Não foi possível obter os dados meteorológicos para {nome_cidade} no momento."

            dados = res.json()
            atual = dados.get("current", {})
            diario = dados.get("daily", {})

            temp_atual = round(atual.get("temperature_2m", 25))
            sensacao = round(atual.get("apparent_temperature", temp_atual))
            umidade = atual.get("relative_humidity_2m", 60)
            vento = round(atual.get("wind_speed_10m", 10))
            code_atual = atual.get("weather_code", 0)
            condicao_atual = WMO_CODES.get(code_atual, "tempo estável")

            temp_max = round(diario.get("temperature_2m_max", [temp_atual])[0])
            temp_min = round(diario.get("temperature_2m_min", [temp_atual])[0])
            prob_chuva = diario.get("precipitation_probability_max", [0])[0]

            detalhes_chuva = f"A probabilidade de chuva hoje é de {prob_chuva}%."
            if prob_chuva > 60:
                detalhes_chuva += " Recomendo que o senhor leve um guarda-chuva ao sair."
            elif prob_chuva < 20:
                detalhes_chuva += " Tempo firme, sem previsão significativa de chuva."

            resposta = (
                f"Em {nome_cidade}, no momento faz {temp_atual}°C com {condicao_atual} e sensação térmica de {sensacao}°C. "
                f"A umidade relativa do ar está em {umidade}% com ventos de {vento} km/h. "
                f"Para hoje, a máxima prevista é de {temp_max}°C e a mínima de {temp_min}°C. {detalhes_chuva}"
            )
            print(f"✅ [CLIMA SUCESSO] {temp_atual}°C | {condicao_atual}")
            return resposta

        except Exception as e:
            return f"Erro ao consultar o serviço meteorológico: {e}"

weather_service = WeatherService()
