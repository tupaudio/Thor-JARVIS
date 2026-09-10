import asyncio
import os
import sys
import subprocess
import edge_tts

# Garantir suporte a UTF-8 no terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

async def test_jarvis_speak():
    text = "Olá senhor. Sistemas online. Eu sou o Jarvis, seu assistente pessoal."
    voice = "pt-BR-AntonioNeural"  # Voz masculina elegante em português
    output_file = os.path.abspath("test_voice.mp3")
    
    print(f"[JARVIS VOZ] Gerando audio neural: '{text}'...")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    print(f"[OK] Audio salvo com sucesso em: {output_file}")
    
    # Reprodução nativa no Windows com MediaPlayer (WPF)
    print("[AUDIO] Reproduzindo audio no alto-falante...")
    ps_command = f'''
    Add-Type -AssemblyName presentationCore
    $player = New-Object system.windows.media.mediaplayer
    $player.open('{output_file.replace(os.sep, "/")}')
    Start-Sleep -Milliseconds 400
    $player.Play()
    Start-Sleep -Seconds 5
    $player.Stop()
    $player.Close()
    '''
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_command], check=True)
    print("[SUCESSO] Reproducao concluida!")

if __name__ == "__main__":
    asyncio.run(test_jarvis_speak())
