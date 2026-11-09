"""
file_manager_service.py — Organização de pastas do servidor Linux (somente dentro do $HOME).

Correções em relação à versão herdada do Windows:
  * Sem USERPROFILE / 'C:\\' / Área de Trabalho do Windows. Base = Path.home() (ex.: /home/thor).
  * Aliases 'downloads', 'desktop' e 'home' resolvem para as pastas que realmente existem
    (Downloads/Transferências, Desktop/Área de Trabalho); se não existirem, a resposta diz isso
    em vez de "diretório não encontrado".
  * Caminho do Windows (C:\\..., barras invertidas) devolve uma explicação clara, nunca um erro de leitura.
  * Segurança: só atua dentro do home, nunca na raiz do home (só análise), ignora ocultos, links
    simbólicos e arquivos modificados há menos de 60 s (downloads em andamento); nunca sobrescreve
    (colisão vira 'nome (1).ext') e registra cada movimento em organizador.log para reversão manual.
"""

import re
import time
import shutil
from datetime import datetime
from pathlib import Path

HOME = Path.home()
LOG = Path(__file__).resolve().parent / "organizador.log"

CATEGORIAS = {
    "PDFs": [".pdf"],
    "Documentos_e_Planilhas": [".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".txt", ".odt", ".ods", ".md"],
    "Imagens": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp", ".ico", ".heic"],
    "Pacotes_e_Instaladores": [".deb", ".rpm", ".appimage", ".run", ".iso", ".img", ".exe", ".msi", ".dmg"],
    "Compactados": [".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".bz2", ".zst"],
    "Audios_e_Videos": [".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4", ".mkv", ".avi", ".mov", ".webm"],
    "Codigos_e_Scripts": [".py", ".json", ".sql", ".js", ".ts", ".html", ".css", ".sh", ".ino", ".cpp", ".h", ".gcode"],
}
IGNORAR_EXT = {".part", ".crdownload", ".tmp", ".download", ".swp"}
ALIASES = {
    "downloads": ["Downloads", "Transferências", "Transferencias"],
    "desktop": ["Desktop", "Área de Trabalho", "Area de Trabalho"],
}


PASTAS_PERMITIDAS_ORGANIZACAO = {
    "downloads", "transferências", "transferencias",
    "desktop", "área de trabalho", "area de trabalho",
    "documentos", "documents",
    "imagens", "pictures",
    "vídeos", "videos",
    "músicas", "music"
}


def _categoria(ext: str):
    for cat, exts in CATEGORIAS.items():
        if ext in exts:
            return cat
    return None


class FileManagerService:
    def _resolver(self, termo: str):
        """Retorna (Path|None, mensagem_de_erro). Nunca levanta exceção."""
        t = (termo or "downloads").strip()
        tl = t.lower()
        if re.match(r"^[a-z]:[\\/]", tl) or "\\" in t:
            return None, ("Isto é um caminho do Windows, senhor, e o servidor roda Linux, então não existe unidade C:. "
                          f"Informe uma pasta dentro de {HOME}, ou peça 'downloads', 'desktop' ou 'home'.")
        if tl in ("home", "pasta pessoal", "minha pasta"):
            return HOME, ""
        chave = "desktop" if ("desktop" in tl or "area de trabalho" in tl or "área de trabalho" in tl) else (
            "downloads" if ("download" in tl or "transfer" in tl) else "")
        if chave:
            for nome in ALIASES[chave]:
                if (HOME / nome).is_dir():
                    return HOME / nome, ""
            return None, f"A pasta {chave} ainda não existe em {HOME}, senhor. O servidor é headless e ela só existe se for criada."
        try:
            p = Path(t).expanduser()
            p = (p if p.is_absolute() else HOME / p).resolve()
        except Exception:
            return None, f"Não consegui interpretar o caminho '{termo}', senhor."
        if p != HOME and HOME not in p.parents:
            return None, f"Por segurança só trabalho dentro de {HOME}, senhor."
        if not p.is_dir():
            return None, f"A pasta {p} não existe, senhor."
        return p, ""

    @staticmethod
    def _arquivos_soltos(pasta: Path):
        agora = time.time()
        for item in pasta.iterdir():
            try:
                if item.name.startswith(".") or item.is_symlink() or not item.is_file():
                    continue
                if item.suffix.lower() in IGNORAR_EXT:
                    continue
                if agora - item.stat().st_mtime < 60:
                    continue
                yield item
            except OSError:
                continue

    def analisar_pasta(self, pasta: str = "downloads") -> str:
        alvo, erro = self._resolver(pasta)
        if erro:
            return erro
        total = tamanho = outros = 0
        por_cat = {}
        for item in self._arquivos_soltos(alvo):
            total += 1
            try:
                tamanho += item.stat().st_size
            except OSError:
                pass
            cat = _categoria(item.suffix.lower())
            if cat:
                por_cat[cat] = por_cat.get(cat, 0) + 1
            else:
                outros += 1
        if total == 0:
            return f"A pasta {alvo.name} não tem arquivos soltos, senhor."
        linhas = [f"Diagnóstico de {alvo}, senhor: {total} arquivos soltos, {tamanho / 1024 ** 2:.1f} MB."]
        linhas += [f"  {c.replace('_', ' ')}: {n}" for c, n in sorted(por_cat.items())]
        if outros:
            linhas.append(f"  Outros formatos: {outros}")
        return "\n".join(linhas)

    def organizar_pasta(self, pasta: str = "downloads") -> str:
        alvo, erro = self._resolver(pasta)
        if erro:
            return erro
        if alvo == HOME:
            return "Por segurança não reorganizo a raiz do seu home, senhor. Posso analisá-la ou organizar uma subpasta segura."

        # TRAVA DE SEGURANÇA (F10):
        # Apenas pastas padrão de arquivos soltos do usuário são permitidas.
        # Pastas de código, projetos (ex: Jarvis), configurações ou ambientes virtuais são protegidas contra movimentação.
        relativo_home = alvo.relative_to(HOME)
        primeira_pasta = relativo_home.parts[0].lower()
        if primeira_pasta not in PASTAS_PERMITIDAS_ORGANIZACAO:
            return (f"Por segurança, a organização automática de arquivos está restrita às pastas usuais de arquivos recebidos "
                    f"(Downloads, Desktop, Documentos, Imagens). A pasta '{alvo.name}' foi protegida contra movimentações automáticas.")
        movidos = 0
        por_cat = {}
        registro = []
        for item in list(self._arquivos_soltos(alvo)):
            cat = _categoria(item.suffix.lower()) or "Outros_Arquivos"
            destino_dir = alvo / cat
            try:
                destino_dir.mkdir(exist_ok=True)
                destino = destino_dir / item.name
                n = 1
                while destino.exists():
                    destino = destino_dir / f"{item.stem} ({n}){item.suffix}"
                    n += 1
                shutil.move(str(item), str(destino))
                movidos += 1
                por_cat[cat] = por_cat.get(cat, 0) + 1
                registro.append(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{item}\t->\t{destino}")
            except Exception as e:
                print(f"⚠️ [ORGANIZADOR] Não movi '{item.name}': {e}")
        if registro:
            try:
                with open(LOG, "a", encoding="utf-8") as f:
                    f.write("\n".join(registro) + "\n")
            except OSError:
                pass
        if not movidos:
            return f"A pasta {alvo.name} já está organizada, senhor."
        detalhe = ", ".join(f"{c.replace('_', ' ')} ({n})" for c, n in sorted(por_cat.items()))
        return f"Organização de {alvo.name} concluída, senhor: {movidos} arquivos movidos para {detalhe}."


file_manager_service = FileManagerService()
