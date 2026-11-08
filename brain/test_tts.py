"""Teste do TTS: gera um MP3 com Edge-TTS (sem tocar no servidor). Abra o arquivo no iPhone/PC para ouvir."""
import asyncio
import edge_tts

async def main():
    out = "teste_tts.mp3"
    await edge_tts.Communicate("Sistemas online, senhor.", "pt-BR-AntonioNeural").save(out)
    print(f"✅ Áudio gerado: {out}")

asyncio.run(main())
