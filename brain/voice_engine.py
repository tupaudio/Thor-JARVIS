"""
voice_engine.py — Voz do J.A.R.V.I.S. (Edge-TTS -> HUD do iPhone).

Pipeline de baixa latência:
  * speak() NÃO bloqueia: enfileira o texto e retorna. Uma thread de voz consome a fila.
  * O texto é limpo para fala (sem markdown/emoji/URL: o Edge-TTS lê "check mark button" etc.)
    e dividido em trechos por sentença; o PRIMEIRO trecho é curto. Cada trecho é sintetizado e
    publicado assim que fica pronto, então o iPhone começa a falar após ~1 sentença em vez de
    esperar a resposta inteira, enquanto o servidor já sintetiza o trecho seguinte.
  * Um event loop asyncio dedicado e persistente (antes: um loop novo por chamada) e timeout por
    trecho: uma conexão pendurada com o serviço da Microsoft não trava mais as falas seguintes.
  * Fila limitada (mantém só as falas mais recentes) e barge-in com parar().
  * sounddevice/numpy/pygame são importados só quando realmente usados (servidor headless não
    precisa de PortAudio/SDL para falar pelo iPhone).
"""

import io
import os
import re
import wave
import queue
import asyncio
import threading

from dotenv import load_dotenv

from env_utils import ENV_PATH

load_dotenv(ENV_PATH)

_RE_URL = re.compile(r"https?://\S+")
_RE_MD = re.compile(r"[*_`#>~]+")
_RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
_RE_BULLET = re.compile(r"(?m)^\s*[•\-–·▪]\s+")
_RE_SENT = re.compile(r"(?<=[.!?…])\s+")
_RE_ONOV_ASTERISK = re.compile(r"\*[^*]*(?:whistle|beep|boop|trill|chirp|tweet|bip|apito|assobio|suspira|risos|som|click)[^*]*\*", re.I)
_RE_ONOV_WORDS = re.compile(r"(?i)\b(beep[s]?|beeping|boop[s]?|whistle[s]?|whistling|trill[s]?|chirp[s]?|tweet[s]?|bipe[s]?|bip[s]?|apito[s]?|assobio[s]?)\b")
_RE_TRADUCAO = re.compile(r"\[(?:Tradução|Traducao|Translation)?\s*:?\s*(.*?)\]", re.I)

# Normalização fonética para evitar que siglas sejam soletradas letra a letra pelo TTS
_MAPA_FONETICO = [
    (re.compile(r"\bT\.?[Aa]\.?[Rr]\.?[Ss]\.?\b", re.I), "Társ"),
    (re.compile(r"\bT\.?[Rr]\.?[Aa]\.?[Ss]\.?\b", re.I), "Társ"),
    (re.compile(r"\bJ\.?A\.?R\.?V\.?I\.?S\.?\b", re.I), "Járvis"),
    (re.compile(r"\bF\.?R\.?I\.?D\.?A\.?Y\.?\b", re.I), "Fráidei"),
    (re.compile(r"\bG\.?I\.?D\.?E\.?O\.?N\.?\b", re.I), "Gídeon"),
    (re.compile(r"\bH\.?A\.?L\.?(?:\s*9000)?\b", re.I), "Hál 9000"),
    (re.compile(r"\bR2-?D2\b", re.I), "R dois D dois"),
    (re.compile(r"\bC-?3PO\b", re.I), "Cê três Pê ó"),
    (re.compile(r"\bEDI\b", re.I), "Édi"),
]


def normalizar_fonetica(texto: str) -> str:
    """Substitui siglas e acrônimos conhecidos por palavras fonéticas que o TTS lê naturalmente."""
    t = _RE_TRADUCAO.sub(r"\1", texto)
    t = _RE_ONOV_ASTERISK.sub("", t)
    t = _RE_ONOV_WORDS.sub("", t)
    for padrao, subst in _MAPA_FONETICO:
        t = padrao.sub(subst, t)
    return t


def limpar_para_fala(texto: str) -> str:
    t = normalizar_fonetica(texto)
    t = _RE_URL.sub("link", t)
    t = _RE_BULLET.sub("", t)
    t = _RE_EMOJI.sub("", t)
    t = _RE_MD.sub("", t)
    linhas = [l.strip() for l in t.splitlines() if l.strip()]
    t = " ".join(l if re.search(r"[.!?…:;]$", l) else l + "." for l in linhas)
    return re.sub(r"\s{2,}", " ", t).strip()


def dividir_em_trechos(texto: str, primeiro: int = 140, demais: int = 260) -> list:
    sentencas = [s for s in _RE_SENT.split(texto) if s]
    trechos, atual, limite = [], "", primeiro
    for s in sentencas:
        while len(s) > limite:  # sentença gigante: corta em espaço
            corte = s.rfind(" ", 0, limite)
            corte = corte if corte > 40 else limite
            parte, s = s[:corte], s[corte:].lstrip()
            if atual:
                trechos.append(atual)
                atual, limite = "", demais
            trechos.append(parte)
            limite = demais
        if atual and len(atual) + 1 + len(s) > limite:
            trechos.append(atual)
            atual, limite = "", demais
        atual = f"{atual} {s}".strip()
    if atual:
        trechos.append(atual)
    return trechos


class VoiceEngine:
    TEXTO_MAX = 1500
    FILA_MAX = 3
    TIMEOUT_TRECHO = 20.0

    def __init__(self, voice_name: str = "pt-BR-AntonioNeural"):
        self.voice_name = voice_name
        self.sample_rate = 16000
        self.audio_output = os.getenv("JARVIS_AUDIO_OUTPUT", "iphone").strip().lower()
        self._fila: "queue.Queue" = queue.Queue()
        self._worker = None
        self._worker_lock = threading.Lock()
        self._loop = None
        self._loop_lock = threading.Lock()
        self._geracao = 0           # incrementa em parar(): invalida o que estava na fila
        self._recognizer = None

    # ---------------------------------------------------------- infraestrutura
    def _garantir_loop(self):
        with self._loop_lock:
            if self._loop is None or not self._loop.is_running():
                loop = asyncio.new_event_loop()
                t = threading.Thread(target=loop.run_forever, daemon=True, name="VoiceAsyncLoop")
                t.start()
                self._loop = loop
            return self._loop

    def _garantir_worker(self):
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._consumir, daemon=True, name="VoiceWorker")
                self._worker.start()

    async def _sintetizar(self, texto: str, voz: str, rate: str, pitch: str) -> bytes:
        import edge_tts

        async def _coletar():
            buf = bytearray()
            async for chunk in edge_tts.Communicate(texto, voice=voz, rate=rate, pitch=pitch).stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk.get("data", b""))
            return bytes(buf)

        return await asyncio.wait_for(_coletar(), timeout=self.TIMEOUT_TRECHO)

    def _sintetizar_sync(self, texto: str, voz: str, rate: str, pitch: str) -> bytes:
        fut = asyncio.run_coroutine_threadsafe(self._sintetizar(texto, voz, rate, pitch), self._garantir_loop())
        try:
            return fut.result(timeout=self.TIMEOUT_TRECHO + 5)
        except Exception as e:
            fut.cancel()
            print(f"[VOZ AVISO] Falha ao sintetizar trecho: {type(e).__name__}: {e}")
            return b""

    @staticmethod
    def _parametros_persona(padrao_voz: str):
        try:
            from persona_manager import persona_manager
            p = persona_manager.obter_persona()
            return p.get("nome", "J.A.R.V.I.S."), p.get("voz", padrao_voz), p.get("rate", "+0%"), p.get("pitch", "+0Hz")
        except Exception:
            return "J.A.R.V.I.S.", padrao_voz, "+0%", "+0Hz"

    # ------------------------------------------------------------------ API
    def speak(self, text: str):
        """Enfileira a fala e retorna imediatamente (não bloqueia o HTTP nem o Telegram)."""
        if not text or not text.strip():
            return
        nome, voz, rate, pitch = self._parametros_persona(self.voice_name)
        print(f"\n🎙️ [{nome}]: \"{text}\"")
        # Fila curta: se o servidor ficou para trás, descarta as falas mais antigas.
        while self._fila.qsize() >= self.FILA_MAX:
            try:
                self._fila.get_nowait()
            except queue.Empty:
                break
        self._fila.put((self._geracao, text, voz, rate, pitch))
        self._garantir_worker()

    def _consumir(self):
        while True:
            geracao, texto, voz, rate, pitch = self._fila.get()
            if geracao != self._geracao:
                continue
            try:
                self._falar(geracao, texto, voz, rate, pitch)
            except Exception as e:  # o worker nunca morre
                print(f"[VOZ AVISO] Erro na fala: {e}")

    def _falar(self, geracao: int, texto: str, voz: str, rate: str, pitch: str):
        from persona_manager import persona_manager
        p = persona_manager.obter_persona()
        persona_id = p.get("id", "JARVIS")

        dock = None
        if self.audio_output != "local":
            from iphone_dock_server import dock_state as dock
            dock.definir_resposta(texto)          # o HUD mostra o texto completo imediatamente

        # Tratamento especial para R2-D2: emite sons autênticos e remove onomatopeias do TTS
        tem_r2 = (persona_id == "R2D2") or any(w in texto.lower() for w in ["whistle", "beep", "boop", "trill", "chirp"])
        texto_para_tts = texto

        if tem_r2:
            # 1. Gera e publica o áudio procedural autêntico de bipes e apitos do R2-D2
            audio_r2 = persona_manager.gerar_audio_r2d2(texto)
            if audio_r2:
                if self.audio_output == "local":
                    self._tocar_local(audio_r2)
                elif dock is not None:
                    dock.publicar_audio(audio_r2, "🛸 [ÁUDIO ASTROMECH TRANSMITIDO]")

            # 2. Extrai a tradução ou limpa as onomatopeias para a voz nunca falar 'whistle', 'bip'
            texto_para_tts = normalizar_fonetica(texto)
            m = re.search(r'\[(?:Tradução|Traducao)?\s*:?\s*(.*?)\]', texto, re.I)
            if m:
                texto_para_tts = normalizar_fonetica(m.group(1).strip())
            else:
                texto_para_tts = normalizar_fonetica(texto)

            # Se não restou texto útil de fala humana, encerra apenas com o áudio astromech autêntico
            if not texto_para_tts or len(texto_para_tts.strip()) < 3 or re.match(r"^[\W_]+$", texto_para_tts):
                if dock is not None:
                    dock.fim_da_resposta()
                return

        falavel = limpar_para_fala(texto_para_tts)[: self.TEXTO_MAX]
        for trecho in dividir_em_trechos(falavel):
            if geracao != self._geracao:          # barge-in: abandona o resto
                return
            audio = self._sintetizar_sync(trecho, voz, rate, pitch)
            if not audio:
                continue
            if self.audio_output == "local":
                self._tocar_local(audio)
            else:
                dock.publicar_audio(audio, trecho)
        if dock is not None:
            dock.fim_da_resposta()

    def _tocar_local(self, audio: bytes):
        import time
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(io.BytesIO(audio))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.04)

    def parar(self):
        """Barge-in: cancela fala em andamento e fila."""
        self._geracao += 1
        while True:
            try:
                self._fila.get_nowait()
            except queue.Empty:
                break
        try:
            from iphone_dock_server import dock_state
            dock_state.limpar_audio()
        except Exception:
            pass
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    # ---------------------------------------------- microfone do servidor (opcional)
    def listen(self, duration: int = 15, timeout_silencio: float = 2.5) -> str:
        """Captura do microfone do SERVIDOR (só para testes; o uso normal é o microfone do iPhone)."""
        try:
            import numpy as np
            import sounddevice as sd
            import speech_recognition as sr
        except Exception as e:
            print(f"⚠️ [MICROFONE] Dependências de áudio local ausentes: {e}")
            return ""
        try:
            print(f"\n🎧 [OUVINDO] Janela de {duration}s...")
            passo = 0.25
            amostras = int(passo * self.sample_rate)
            frames, falou, silencio = [], False, 0.0
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16") as stream:
                for _ in range(int(duration / passo)):
                    dado, _ = stream.read(amostras)
                    frames.append(dado.copy())
                    rms = float(np.sqrt(np.mean(dado.astype(np.float32) ** 2)))
                    if rms > 350:
                        falou, silencio = True, 0.0
                    elif falou:
                        silencio += passo
                        if silencio >= timeout_silencio:
                            break
            wav = io.BytesIO()
            with wave.open(wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(np.concatenate(frames, axis=0).tobytes())
            wav.seek(0)
            if self._recognizer is None:
                self._recognizer = sr.Recognizer()
                self._recognizer.operation_timeout = 10  # sem isto o reconhecimento pode pendurar indefinidamente
            with sr.AudioFile(wav) as fonte:
                audio = self._recognizer.record(fonte)
            texto = self._recognizer.recognize_google(audio, language="pt-BR")
            print(f"👤 [VOCÊ FALOU]: \"{texto}\"")
            return texto
        except Exception as e:
            print(f"⚠️ [MICROFONE] {type(e).__name__}: {e}")
            return ""


voice_engine = VoiceEngine()
