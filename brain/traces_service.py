"""
traces_service.py — Registro e observabilidade de interações do J.A.R.V.I.S. em SQLite (MP3).

Permite auditar:
  * Latência real (P50/P95 em ms) por rota (local/nuvem/ollama/telegram).
  * Histórico de comandos com taxas de sucesso e causas de fallback.
  * Estatísticas agregadas sem comprometer a performance (escrita assíncrona/rápida em banco local).
"""

import os
import time
import sqlite3
import threading
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    data_hora TEXT,
    origem TEXT,
    entrada TEXT,
    rota TEXT,
    modelo TEXT,
    lat_ms INTEGER,
    ok INTEGER,
    erro TEXT
);
CREATE INDEX IF NOT EXISTS idx_traces_ts ON traces(ts);
CREATE INDEX IF NOT EXISTS idx_traces_rota ON traces(rota);
"""


class TracesService:
    def __init__(self):
        self._lock = threading.Lock()
        self._inicializado = False

    def _garantir_tabela(self):
        if not self._inicializado:
            with self._lock:
                if not self._inicializado:
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.executescript(SCHEMA)
                        self._inicializado = True
                    except Exception as e:
                        print(f"⚠️ [TRACES] Falha ao criar schema do banco: {e}")

    def gravar(self, t: dict):
        """Grava uma linha de trace de forma thread-safe."""
        self._garantir_tabela()
        try:
            with self._lock:
                with sqlite3.connect(DB_PATH, timeout=5.0) as conn:
                    conn.execute(
                        "INSERT INTO traces (ts, data_hora, origem, entrada, rota, modelo, lat_ms, ok, erro) "
                        "VALUES (?, datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?)",
                        (
                            t.get("ts", time.time()),
                            t.get("origem", "desconhecido"),
                            t.get("entrada", "")[:500],
                            t.get("rota", "desconhecida"),
                            t.get("modelo", ""),
                            int(t.get("lat_ms", 0)),
                            int(t.get("ok", 1)),
                            str(t.get("erro", ""))[:200]
                        )
                    )
        except Exception as e:
            # Observabilidade nunca deve derrubar o fluxo principal
            pass

    @contextmanager
    def medir(self, origem: str, entrada: str):
        """Context manager para envolver a execução de comandos."""
        t = {
            "ts": time.time(),
            "origem": origem,
            "entrada": entrada,
            "rota": "desconhecida",
            "modelo": "",
            "ok": 1,
            "erro": ""
        }
        t0 = time.monotonic()
        try:
            yield t
        except Exception as e:
            t["ok"] = 0
            t["erro"] = type(e).__name__
            raise
        finally:
            t["lat_ms"] = int((time.monotonic() - t0) * 1000)
            threading.Thread(target=self.gravar, args=(t,), daemon=True).start()

    def obter_metricas_resumo(self) -> dict:
        """Retorna estatísticas agregadas das últimas 24 horas."""
        self._garantir_tabela()
        try:
            with self._lock:
                with sqlite3.connect(DB_PATH, timeout=3.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*), AVG(lat_ms), SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) FROM traces WHERE ts > ?",
                                   (time.time() - 86400,))
                    total, media_lat, sucessos = cursor.fetchone()
                    total = total or 0
                    taxa = (sucessos / total * 100) if total > 0 else 100.0
                    return {
                        "total_24h": total,
                        "latencia_media_ms": int(media_lat or 0),
                        "taxa_sucesso": round(taxa, 1)
                    }
        except Exception:
            return {"total_24h": 0, "latencia_media_ms": 0, "taxa_sucesso": 100.0}


traces_service = TracesService()
