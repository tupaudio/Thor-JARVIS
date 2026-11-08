"""Escrita atômica e thread-safe de variáveis no .env (evita arquivo truncado/corrompido)."""

import os
import tempfile
import threading
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
_lock = threading.Lock()


def atualizar_env(chave: str, valor: str, caminho: Path = ENV_PATH) -> bool:
    """Grava/atualiza CHAVE=valor no .env de forma atômica e reflete em os.environ."""
    valor = str(valor).replace("\n", " ").strip()
    with _lock:
        try:
            try:
                linhas = caminho.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                linhas = []
            achou = False
            for i, linha in enumerate(linhas):
                if linha.strip().startswith(f"{chave}="):
                    linhas[i] = f"{chave}={valor}"
                    achou = True
                    break
            if not achou:
                linhas.append(f"{chave}={valor}")

            fd, tmp = tempfile.mkstemp(dir=str(caminho.parent), prefix=".env.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write("\n".join(linhas) + "\n")
                os.chmod(tmp, 0o600)
                os.replace(tmp, caminho)  # atômico no mesmo filesystem
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            os.environ[chave] = valor
            return True
        except Exception as e:
            print(f"⚠️ [ENV] Falha ao persistir {chave}: {e}")
            return False
