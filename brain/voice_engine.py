"""
Módulo de Voz do JARVIS (Text-to-Speech e Speech-to-Text).
Utiliza Edge-TTS para fala neural e SoundDevice + Google Speech para escuta sem depender do PyAudio.
"""

import io
import os
import sys
import wave
import asyncio
import subprocess
import numpy as np
import sounddevice as sd
import edge_tts
import speech_recognition as sr

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pygame
import time

class VoiceEngine:
    def __init__(self, voice_name: str = "pt-BR-AntonioNeural"):
        self.voice_name = voice_name
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"⚠️ [VOZ] Falha ao inicializar pygame.mixer: {e}")

    async def _generate_audio_bytes(self, text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        audio_stream = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_stream.extend(chunk.get("data", b""))
        return bytes(audio_stream)

    def speak(self, text: str):
        """
        Sintetiza e reproduz a fala do assistente diretamente da memória RAM via pygame.mixer,
        adaptando voz, velocidade e tom conforme a personalidade ativa.
        """
        try:
            from persona_manager import persona_manager
            p = persona_manager.obter_persona()
            nome_persona = p.get("nome", "J.A.R.V.I.S.")
            voz = p.get("voz", self.voice_name)
            rate = p.get("rate", "+0%")
            pitch = p.get("pitch", "+0Hz")
            is_r2d2 = (p.get("id") == "R2D2")
        except Exception:
            nome_persona = "J.A.R.V.I.S."
            voz = self.voice_name
            rate = "+0%"
            pitch = "+0Hz"
            is_r2d2 = False

        print(f"\n🎙️ [{nome_persona}]: \"{text}\"")

        try:
            # Se a persona for o R2-D2, primeiro toca os bipes eletrônicos do droide!
            if is_r2d2:
                try:
                    from persona_manager import persona_manager
                    r2_wav = persona_manager.gerar_audio_r2d2()
                    if r2_wav:
                        bio_r2 = io.BytesIO(r2_wav)
                        pygame.mixer.music.load(bio_r2)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.04)
                except Exception:
                    pass

            audio_bytes = asyncio.run(self._generate_audio_bytes(text, voice=voz, rate=rate, pitch=pitch))
            if not audio_bytes:
                return

            bio = io.BytesIO(audio_bytes)
            pygame.mixer.music.load(bio)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.04)

        except Exception as e:
            print(f"[VOZ AVISO] Erro ao reproduzir voz: {e}")

    def parar(self):
        """Interrompe a fala do assistente imediatamente (barge-in)."""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass

    def listen(self, duration: int = 5) -> str:
        """
        Captura áudio do microfone do PC usando SoundDevice e converte em texto.
        """
        try:
            print(f"\n🎧 [OUVINDO...] Fale agora senhor (gravando {duration} segundos)...")
            recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype='int16')
            sd.wait()
            print("⏳ [PROCESSANDO VOZ] Interpretando sua fala...")
            
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(recording.tobytes())
            wav_io.seek(0)
            
            with sr.AudioFile(wav_io) as source:
                audio = self.recognizer.record(source)
                texto = self.recognizer.recognize_google(audio, language="pt-BR")
                print(f"👤 [VOCÊ FALOU]: \"{texto}\"")
                return texto
        except sr.UnknownValueError:
            print("⚠️ [JARVIS]: Não detectei nenhuma fala clara no microfone, senhor.")
            return ""
        except Exception as e:
            print(f"⚠️ [MICROFONE AVISO]: {e}")
            return ""

voice_engine = VoiceEngine()
