"""
Serviço de Memória Episódica e Perfil de Longo Prazo do J.A.R.V.I.S. (Memory Stream / RAG).
Permite reter preferências do usuário, projetos da impressora 3D, rotinas e histórico de conversas,
persistindo em SQLite com índice FTS5 (Full-Text Search com ranking BM25) e recuperação contextual.
"""

import os
import re
import time
import math
import sqlite3
import threading
import logging
from datetime import datetime

logger = logging.getLogger("jarvis-memory")

_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "memory.db"))


class MemoryService:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._inicializar_banco()

    def _obter_conexao(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _inicializar_banco(self):
        """Cria as tabelas de memória episódica, tabela virtual FTS5 e perfil do usuário."""
        with self._lock, self._obter_conexao() as conn:
            # 1. Tabela de Memórias Episódicas
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memorias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chave TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    conteudo TEXT NOT NULL,
                    origem TEXT DEFAULT 'usuario',
                    acessos INTEGER DEFAULT 0,
                    criado_em REAL NOT NULL,
                    atualizado_em REAL NOT NULL
                );
            """)

            # 2. Índice FTS5 para busca textual ultra-rápida (BM25)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memorias_fts USING fts5(
                    chave,
                    categoria,
                    conteudo,
                    content='memorias',
                    content_rowid='id'
                );
            """)

            # Triggers para sincronizar a tabela normal com o FTS5
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memorias_ai AFTER INSERT ON memorias BEGIN
                    INSERT INTO memorias_fts(rowid, chave, categoria, conteudo)
                    VALUES (new.id, new.chave, new.categoria, new.conteudo);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memorias_ad AFTER DELETE ON memorias BEGIN
                    INSERT INTO memorias_fts(memorias_fts, rowid, chave, categoria, conteudo)
                    VALUES ('delete', old.id, old.chave, old.categoria, old.conteudo);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memorias_au AFTER UPDATE ON memorias BEGIN
                    INSERT INTO memorias_fts(memorias_fts, rowid, chave, categoria, conteudo)
                    VALUES ('delete', old.id, old.chave, old.categoria, old.conteudo);
                    INSERT INTO memorias_fts(rowid, chave, categoria, conteudo)
                    VALUES (new.id, new.chave, new.categoria, new.conteudo);
                END;
            """)

            # 3. Tabela de Chave-Valor para Perfil do Dono (Tony Stark / Usuário)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS perfil_usuario (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL,
                    atualizado_em REAL NOT NULL
                );
            """)

            # Seed inicial de perfil básico se estiver vazio
            cur = conn.execute("SELECT COUNT(*) as c FROM perfil_usuario")
            if cur.fetchone()["c"] == 0:
                agora = time.time()
                perfis_padrao = [
                    ("tratamento_preferido", "Senhor", agora),
                    ("idioma_padrao", "Português do Brasil", agora),
                    ("impressora_3d_padrao", "Creality Ender 3 S1 Pro", agora),
                    ("filamento_padrao", "PLA (205°C bico / 60°C mesa)", agora),
                    ("dispositivo_dock", "iPhone 11", agora),
                    ("servidor_principal", "Dell OptiPlex 3060 Micro (Debian 13)", agora),
                ]
                conn.executemany("INSERT INTO perfil_usuario (chave, valor, atualizado_em) VALUES (?, ?, ?)", perfis_padrao)
            conn.commit()

    def salvar_memoria(self, chave: str, conteudo: str, categoria: str = "geral", origem: str = "usuario") -> bool:
        """
        Salva ou atualiza uma memória episódica.
        Se já existir uma memória com a mesma chave e categoria, atualiza o conteúdo.
        """
        chave = chave.strip().lower()
        conteudo = conteudo.strip()
        categoria = categoria.strip().lower()
        if not chave or not conteudo:
            return False

        agora = time.time()
        with self._lock, self._obter_conexao() as conn:
            # Verifica se já existe
            cur = conn.execute("SELECT id FROM memorias WHERE chave = ? AND categoria = ?", (chave, categoria))
            row = cur.fetchone()
            if row:
                conn.execute("""
                    UPDATE memorias 
                    SET conteudo = ?, origem = ?, atualizado_em = ?
                    WHERE id = ?
                """, (conteudo, origem, agora, row["id"]))
            else:
                conn.execute("""
                    INSERT INTO memorias (chave, categoria, conteudo, origem, acessos, criado_em, atualizado_em)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                """, (chave, categoria, conteudo, origem, agora, agora))
            conn.commit()
            return True

    def buscar_memorias(self, termo: str, limite: int = 5) -> list[dict]:
        """
        Busca memórias relevantes utilizando FTS5 e ordenação por BM25 combinada com recência.
        """
        termo = termo.strip()
        if not termo:
            return []

        # Limpa termos para sintaxe segura do FTS5
        palavras = [re.sub(r"[^\wáéíóúâêîôûãõç]", "", p) for p in termo.split()]
        palavras = [p for p in palavras if len(p) >= 2]
        if not palavras:
            return []

        fts_query = " OR ".join(f'"{p}"*' for p in palavras)

        with self._lock, self._obter_conexao() as conn:
            try:
                # FTS5 bm25() devolve valores negativos (quanto menor, mais relevante)
                sql = """
                    SELECT m.id, m.chave, m.categoria, m.conteudo, m.acessos, m.atualizado_em,
                           bm25(memorias_fts) as score_bm25
                    FROM memorias_fts f
                    JOIN memorias m ON m.id = f.rowid
                    WHERE memorias_fts MATCH ?
                    ORDER BY bm25(memorias_fts) ASC
                    LIMIT ?
                """
                cur = conn.execute(sql, (fts_query, limite * 2))
                linhas = cur.fetchall()
            except Exception as e:
                # Fallback para busca LIKE caso a consulta FTS contenha caractere inválido
                logger.warning(f"Fallback FTS5 para LIKE: {e}")
                sql = """
                    SELECT id, chave, categoria, conteudo, acessos, atualizado_em, 0.0 as score_bm25
                    FROM memorias
                    WHERE chave LIKE ? OR conteudo LIKE ?
                    ORDER BY atualizado_em DESC
                    LIMIT ?
                """
                cur = conn.execute(sql, (f"%{termo}%", f"%{termo}%", limite))
                linhas = cur.fetchall()

            agora = time.time()
            resultados = []
            for r in linhas:
                # Cálculo de decaimento temporal: meia-vida de 14 dias (1209600 s)
                idade_segundos = max(0.0, agora - r["atualizado_em"])
                decaimento = math.exp(-idade_segundos / 1209600.0)
                score_final = (-r["score_bm25"] * 2.0) + (decaimento * 1.5) + (math.log1p(r["acessos"]) * 0.5)

                resultados.append({
                    "id": r["id"],
                    "chave": r["chave"],
                    "categoria": r["categoria"],
                    "conteudo": r["conteudo"],
                    "acessos": r["acessos"],
                    "atualizado_em": r["atualizado_em"],
                    "score": score_final
                })

            # Re-ordena pelo score final combinado
            resultados.sort(key=lambda x: x["score"], reverse=True)
            top_resultados = resultados[:limite]

            # Incrementa contador de acessos para os recuperados
            if top_resultados:
                ids = [r["id"] for r in top_resultados]
                conn.execute(f"UPDATE memorias SET acessos = acessos + 1 WHERE id IN ({','.join('?'*len(ids))})", ids)
                conn.commit()

            return top_resultados

    def obter_perfil_completo(self) -> dict:
        """Retorna todas as preferências salvas no perfil do usuário."""
        with self._lock, self._obter_conexao() as conn:
            cur = conn.execute("SELECT chave, valor FROM perfil_usuario")
            return {r["chave"]: r["valor"] for r in cur.fetchall()}

    def atualizar_perfil(self, chave: str, valor: str) -> bool:
        """Insere ou atualiza uma propriedade no perfil do usuário."""
        chave = chave.strip().lower()
        valor = valor.strip()
        if not chave or not valor:
            return False
        with self._lock, self._obter_conexao() as conn:
            conn.execute("""
                INSERT INTO perfil_usuario (chave, valor, atualizado_em)
                VALUES (?, ?, ?)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em
            """, (chave, valor, time.time()))
            conn.commit()
            return True

    def obter_contexto_relevante(self, query: str, limite: int = 4) -> str:
        """
        Recupera as memórias mais relevantes formatadas como bloco de contexto para injeção no prompt do LLM.
        """
        memorias = self.buscar_memorias(query, limite=limite)
        if not memorias:
            return ""

        linhas = ["### MEMÓRIA DE LONGO PRAZO DO J.A.R.V.I.S. (Fatos e Preferências do Usuário):"]
        for m in memorias:
            dt = datetime.fromtimestamp(m["atualizado_em"]).strftime("%d/%m/%Y")
            linhas.append(f"- [{m['categoria'].upper()}] {m['chave']}: {m['conteudo']} (registrado em {dt})")
        return "\n".join(linhas)

    def extrair_e_persistir_fatos(self, texto_usuario: str, resposta_assistente: str = ""):
        """
        Extrai heuristicamente preferências e fatos importantes ditos pelo usuário na conversa
        e os persiste na memória de longo prazo (estilo OpenJarvis / Reflexion).
        """
        t = texto_usuario.strip()
        
        # Padrões comuns: "Lembre-se que ...", "Guarde que ...", "Minha preferência é ...", "Meu ... é ..."
        padroes = [
            (r"(?:lembre-se(?: que)?|não se esqueça(?: que)?|guarde(?: que)?)\s+(.+)", "instrucao_usuario"),
            (r"(?:eu prefiro|minha preferência é|prefiro sempre)\s+(.+)", "preferencia"),
            (r"(?:o meu|a minha)\s+([a-zA-Z0-9_\s]{3,20})\s+é\s+(.+)", "fato_pessoal"),
            (r"(?:para o|no filamento|na impressora)\s+([a-zA-Z0-9_\s]{3,20})\s+(?:use|coloque|configure)\s+(.+)", "projeto_3d"),
        ]

        for regex, cat in padroes:
            match = re.search(regex, t, re.IGNORECASE)
            if match:
                grupos = match.groups()
                if len(grupos) == 1:
                    chave = grupos[0][:25].strip().lower()
                    conteudo = grupos[0].strip()
                elif len(grupos) >= 2:
                    chave = grupos[0].strip().lower()
                    conteudo = grupos[1].strip()
                else:
                    continue

                if len(conteudo) >= 4:
                    self.salvar_memoria(chave=chave, conteudo=conteudo, categoria=cat, origem="conversa_automatica")
                    logger.info(f"Fato memorizado automaticamente: [{cat}] {chave} -> {conteudo}")
                    break


memory_service = MemoryService()
