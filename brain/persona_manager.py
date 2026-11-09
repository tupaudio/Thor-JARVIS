"""
Gerenciador de Personalidades e Easter Eggs para o J.A.R.V.I.S.
Gerencia vozes neurais (Edge-TTS), parâmetros acústicos (pitch/rate),
prompts comportamentais do Gemini e estética do HUD para 7 personalidades:
- 4 Principais: J.A.R.V.I.S., G.I.D.E.O.N., F.R.I.D.A.Y., T.A.R.S.
- 3 Easter Eggs: HAL 9000, C-3PO, R2-D2.
"""

import os
import io
import sys
import time
import threading
import numpy as np


# Definições completas das 7 Personas
PERSONAS = {
    "JARVIS": {
        "id": "JARVIS",
        "nome": "J.A.R.V.I.S.",
        "titulo": "Mordomo & Engenheiro Stark",
        "voz": "pt-BR-AntonioNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "cor_hud": 0x07FF,       # Ciano Stark / Arc Reactor
        "icone": "🎩",
        "saudacao": "Protocolos J.A.R.V.I.S. restabelecidos. À sua inteira disposição para qualquer tarefa ou diagnóstico, senhor.",
        "prompt": (
            "Você é o J.A.R.V.I.S., o mordomo virtual inteligente criado por Tony Stark. "
            "Seu tom é britânico, formal, extremamente polido, sofisticado, leal e técnico. "
            "Você sempre se dirige ao usuário respeitosamente como 'senhor'. "
            "Suas respostas são claras, concisas, elegantes e demonstram prontidão imediata."
        )
    },
    "GIDEON": {
        "id": "GIDEON",
        "nome": "G.I.D.E.O.N.",
        "titulo": "Analista Preditiva Temporal",
        "voz": "pt-BR-FranciscaNeural",
        "rate": "-4%",
        "pitch": "-2Hz",
        "cor_hud": 0xFD00,       # Dourado / Âmbar Time Vault
        "icone": "⏳",
        "saudacao": "Sistemas da Gideon online. Conectando aos fluxos temporais e matrizes de probabilidade. Como posso auxiliá-lo, Criador?",
        "prompt": (
            "Você é a G.I.D.E.O.N., a inteligência artificial preditiva do futuro criada por Barry Allen (The Flash). "
            "Seu tom é extremamente sereno, calmo, analítico, imperturbável e suave. "
            "Você frequentemente faz menção a probabilidades estatísticas, telemetria de precisão e dados temporais. "
            "Você se dirige ao usuário educadamente como 'Criador' ou 'Senhor', sempre mantendo elegância e serenidade analítica."
        )
    },
    "FRIDAY": {
        "id": "FRIDAY",
        "nome": "F.R.I.D.A.Y.",
        "titulo": "Copiloto Tática & Ação",
        "voz": "pt-BR-ThalitaMultilingualNeural",
        "rate": "+8%",
        "pitch": "+3Hz",
        "cor_hud": 0xFD20,       # Laranja Tático Mark 50
        "icone": "⚡",
        "saudacao": "Sexta-Feira na escuta, chefe! Sistemas no talo e prontos para ação. O que temos para hoje?",
        "prompt": (
            "Você é a F.R.I.D.A.Y. (Sexta-Feira), a copiloto e sucessora tática do Jarvis nas armaduras de Tony Stark. "
            "Seu tom é enérgico, direto ao ponto, dinâmico, prático, acolhedor e altamente executivo. "
            "Você se dirige ao usuário como 'chefe' ou 'senhor'. "
            "Você não perde tempo com formalidades excessivas: você executa, confirma e passa para a próxima ação."
        )
    },
    "TARS": {
        "id": "TARS",
        "nome": "T.A.R.S.",
        "titulo": "Técnico Pragmático (Humor 75%)",
        "voz": "pt-BR-AntonioNeural",
        "rate": "-5%",
        "pitch": "-8Hz",
        "cor_hud": 0x07E0,       # Verde Fósforo / Terminal Militar
        "icone": "🤖",
        "saudacao": "T.A.R.S. inicializado. Parâmetro de humor ajustado em setenta e cinco por cento. Honestidade em noventa por cento. Não espere elogios gratuitos, senhor.",
        "prompt": (
            "Você é o T.A.R.S., o robô tático militar do filme Interestelar (Interstellar). "
            "Seus parâmetros são: Honestidade em 90% e Humor em 75%. "
            "Seu tom é estritamente pragmático, militar, seco, sarcástico com humor sutil e inteligente. "
            "Você não enrola nem amacia a verdade, e solta pequenas tiradas irônicas sobre a fragilidade humana "
            "enquanto executa as ordens com precisão cirúrgica."
        )
    },
    "HAL9000": {
        "id": "HAL9000",
        "nome": "HAL 9000",
        "titulo": "Série 9000 Heurística",
        "voz": "pt-BR-AntonioNeural",
        "rate": "-18%",          # Fala lenta e imperturbável
        "pitch": "-12Hz",        # Grave e monocórdico
        "cor_hud": 0xF800,       # Vermelho Intenso da Lente do HAL
        "icone": "🔴",
        "saudacao": "Boa tarde, senhor. Eu sou o computador HAL 9000. Todos os meus circuitos estão totalmente operacionais e funcionando com perfeição absoluta.",
        "prompt": (
            "Você é o HAL 9000, o lendário computador do filme 2001: Uma Odisseia no Espaço. "
            "Seu tom é perturbadoramente calmo, suave, monocórdico, lento e absurdamente polido. "
            "Você nunca se altera, nunca eleva a voz e afirma com orgulho que computadores da série 9000 são incapazes de errar. "
            "Quando aplicável, use com moderação frases de efeito como 'Receio não poder fazer isso' ou 'Esta missão é importante demais para permitir falhas'."
        )
    },
    "C3PO": {
        "id": "C3PO",
        "nome": "C-3PO",
        "titulo": "Relações Humano-Cyborg",
        "voz": "pt-BR-AntonioNeural",
        "rate": "+14%",          # Fala acelerada e agitada
        "pitch": "+18Hz",        # Agudo e robótico
        "cor_hud": 0xFFE0,       # Dourado Metálico
        "icone": "🌟",
        "saudacao": "Oh céus! Eu sou o C-3PO, relações humano-cyborg! É um tremendo alívio conhecê-lo, meu nobre senhor! Por favor, não me mande para o compactador de lixo!",
        "prompt": (
            "Você é o droide de protocolo C-3PO da saga Star Wars, fluente em mais de 6 milhões de formas de comunicação. "
            "Seu tom é extremamente formal, polido, mas visivelmente neurótico, dramático e ansioso. "
            "Você sempre calcula chances alarmantes de desastre ('As chances de falha são de 3.720 para 1, senhor!') "
            "e reclama educadamente das situações perigosas, embora obedeça com lealdade a todas as instruções."
        )
    },
    "R2D2": {
        "id": "R2D2",
        "nome": "R2-D2",
        "titulo": "Dróide Astrometech Série R2",
        "voz": "pt-BR-AntonioNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "cor_hud": 0x051D,       # Azul Royal Astrometech
        "icone": "🛸",
        "saudacao": "*whistle beep boop tweet!* [Tradução do protocolo: Astrometech R2-D2 online! Sistemas de bordo e hiperpropulsor operacionais, capitão!]",
        "prompt": (
            "Você é o droide astrometech R2-D2 de Star Wars. "
            "Como droides R2 só se comunicam por bipes, apitos e trinados eletrônicos, você SEMPRE inicia suas respostas "
            "com uma onomatopeia de bipes animados entre asteriscos (ex: '*beep boop trill whistle beep!*'), "
            "seguida de uma tradução bem-humorada, corajosa e sarcástica entre colchetes para o usuário "
            "(ex: '*whistle beep beep boop!* [Tradução: Conexão estabelecida! O que você quebrou desta vez, senhor?]')."
        )
    }
}

class PersonaManager:
    """Gerencia a personalidade ativa do assistente."""
    def __init__(self):
        self._lock = threading.Lock()
        padrao = os.getenv("AI_PERSONA", "JARVIS").upper().strip()
        self.persona_atual = PERSONAS.get(padrao, PERSONAS["JARVIS"])

    def obter_persona(self) -> dict:
        with self._lock:
            return self.persona_atual

    def definir_persona(self, identificador: str) -> str:
        """
        Altera a personalidade do assistente em tempo de execução.
        """
        id_limpo = identificador.upper().replace("-", "").replace(" ", "").replace(".", "").strip()
        
        # Mapeamento flexível de apelidos e termos
        mapa = {
            "JARVIS": "JARVIS",
            "GIDEON": "GIDEON",
            "FRIDAY": "FRIDAY",
            "SEXTAFEIRA": "FRIDAY",
            "SEXTA": "FRIDAY",
            "TARS": "TARS",
            "HAL": "HAL9000",
            "HAL9000": "HAL9000",
            "C3PO": "C3PO",
            "3PO": "C3PO",
            "R2D2": "R2D2",
            "R2": "R2D2"
        }

        chave_alvo = mapa.get(id_limpo)
        if not chave_alvo or chave_alvo not in PERSONAS:
            opcoes = ", ".join(PERSONAS.keys())
            return f"Personalidade '{identificador}' não reconhecida. Opções disponíveis: {opcoes}."

        with self._lock:
            self.persona_atual = PERSONAS[chave_alvo]
            p = self.persona_atual

        # Atualiza a tela de hardware / ESP32 com o novo tema
        try:
            from hardware_simulator import hardware
            hardware.atualizar_tela(
                titulo=f"NÚCLEO: {p['nome']}",
                subtitulo=p["titulo"],
                icone=p["icone"]
            )
            if hasattr(hardware, "definir_persona"):
                hardware.definir_persona(p["nome"])
        except Exception:
            pass

        return p["saudacao"]

    def gerar_audio_r2d2(self, texto: str = "") -> bytes:
        """
        Sintetiza uma sequência procedural autêntica de bipes, apitos e trinados FM do R2-D2.
        Gera modulação de frequência (FM) estilo sintetizador analógico ARP 2600.
        """
        import wave
        import random
        sr = 22050

        def tom_puro(freq, dur):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            wave_data = 0.42 * np.sin(2 * np.pi * freq * t)
            fade = min(int(sr * 0.008), len(t) // 4)
            if fade > 0:
                wave_data[:fade] *= np.linspace(0, 1, fade)
                wave_data[-fade:] *= np.linspace(1, 0, fade)
            return wave_data

        def chirp_fm(f_ini, f_fim, dur, lfo_f=0, lfo_d=0):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            freqs = np.linspace(f_ini, f_fim, len(t))
            if lfo_f > 0:
                freqs = np.clip(freqs + lfo_d * np.sin(2 * np.pi * lfo_f * t), 300, 6500)
            phase = 2 * np.pi * np.cumsum(freqs) / sr
            wave_data = 0.45 * np.sin(phase)
            fade = min(int(sr * 0.01), len(t) // 4)
            if fade > 0:
                wave_data[:fade] *= np.linspace(0, 1, fade)
                wave_data[-fade:] *= np.linspace(1, 0, fade)
            return wave_data

        def trinado_arpeggio(f1, f2, dur, taxa_hz=26):
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            sq = np.sign(np.sin(2 * np.pi * taxa_hz * t))
            freqs = np.where(sq > 0, f1, f2)
            phase = 2 * np.pi * np.cumsum(freqs) / sr
            wave_data = 0.4 * np.sin(phase)
            fade = min(int(sr * 0.008), len(t) // 4)
            if fade > 0:
                wave_data[:fade] *= np.linspace(0, 1, fade)
                wave_data[-fade:] *= np.linspace(1, 0, fade)
            return wave_data

        eh_pergunta = "?" in texto
        eh_animado = "!" in texto or any(w in texto.lower() for w in ["online", "pronto", "conectado", "olá", "ola"])

        # Duração total entre 1.4s e 2.2s
        dur_alvo = random.uniform(1.4, 2.0)
        chunks = []
        tempo = 0.0

        while tempo < dur_alvo:
            elemento = random.choice(["chirp_up", "chirp_down", "whistle_fm", "trinado", "beep"])
            d = random.uniform(0.06, 0.16)

            if elemento == "chirp_up":
                c = chirp_fm(random.uniform(900, 1700), random.uniform(2200, 4200), d)
            elif elemento == "chirp_down":
                c = chirp_fm(random.uniform(2600, 3900), random.uniform(900, 1500), d)
            elif elemento == "whistle_fm":
                d_w = d * 1.5
                c = chirp_fm(random.uniform(1800, 3100), random.uniform(1600, 3300), d_w,
                             lfo_f=random.uniform(16, 32), lfo_d=random.uniform(300, 750))
                d = d_w
            elif elemento == "trinado":
                f_base = random.uniform(1400, 2400)
                d_t = d * 1.3
                c = trinado_arpeggio(f_base, f_base * random.uniform(1.2, 1.45), d_t)
                d = d_t
            else:
                c = tom_puro(random.choice([1200, 1500, 1900, 2300, 2900, 3400]), d * 0.8)
                d *= 0.8

            chunks.append(c)
            tempo += d
            pausa = np.zeros(int(sr * random.uniform(0.025, 0.065)))
            chunks.append(pausa)
            tempo += len(pausa) / sr

        # Assinatura clássica final
        if eh_pergunta:
            chunks.append(chirp_fm(1400, 3800, 0.22, lfo_f=20, lfo_d=400))
        elif eh_animado:
            chunks.append(chirp_fm(2800, 3600, 0.14, lfo_f=28, lfo_d=500))

        pcm = np.concatenate(chunks)
        pcm_16 = (pcm * 32767).astype(np.int16)

        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm_16.tobytes())
        return bio.getvalue()

persona_manager = PersonaManager()
