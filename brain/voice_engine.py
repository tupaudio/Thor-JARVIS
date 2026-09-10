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

class VoiceEngine:
    def __init__(self, voice_name: str = "pt-BR-AntonioNeural"):
        self.voice_name = voice_name
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.temp_audio_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "jarvis_speech.mp3"))

    async def _generate_audio(self, text: str):
        communicate = edge_tts.Communicate(text, self.voice_name)
        await communicate.save(self.temp_audio_file)

    def speak(self, text: str):
        """
        Sintetiza e reproduz a fala do JARVIS pelo alto-falante até o final sem cortes.
        """
        print(f"\n🎙️ [JARVIS]: \"{text}\"")
        try:
            asyncio.run(self._generate_audio(text))
            normalized_path = self.temp_audio_file.replace(os.sep, "/")
            ps_command = f'''
            Add-Type -AssemblyName presentationCore
            $player = New-Object system.windows.media.mediaplayer
            $player.open('{normalized_path}')
            
            # Aguarda o Windows carregar o arquivo e calcular a duração exata
            $timeout = 0
            while (-not $player.NaturalDuration.HasTimeSpan -and $timeout -lt 50) {{
                Start-Sleep -Milliseconds 100
                $timeout++
            }}
            
            if ($player.NaturalDuration.HasTimeSpan) {{
                $duration = $player.NaturalDuration.TimeSpan.TotalSeconds
                $player.Play()
                Start-Sleep -Milliseconds 200
                while ($player.Position.TotalSeconds -lt ($duration - 0.2)) {{
                    Start-Sleep -Milliseconds 100
                }}
                Start-Sleep -Milliseconds 500
            }} else {{
                # Fallback seguro caso não detecte duração
                $player.Play()
                Start-Sleep -Seconds 12
            }}
            
            $player.Stop()
            $player.Close()
            '''
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_command], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[VOZ AVISO] Erro ao reproduzir voz: {e}")

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
