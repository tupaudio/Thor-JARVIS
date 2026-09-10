"""
Módulo de Organização e Gerenciamento Inteligente de Arquivos para o J.A.R.V.I.S.
Varre pastas bagunçadas (como Downloads ou Desktop) e categoriza arquivos
em subpastas organizadas por tipo (PDFs, Imagens, Instaladores, Planilhas, etc.).
"""

import os
import sys
import shutil
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

CATEGORIAS = {
    "PDFs": [".pdf"],
    "Documentos_e_Planilhas": [".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".txt", ".odt"],
    "Imagens": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp", ".ico"],
    "Instaladores_e_Sistemas": [".exe", ".msi", ".iso"],
    "Compactados": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Audios_e_Videos": [".mp3", ".wav", ".ogg", ".mp4", ".mkv", ".avi", ".mov"],
    "Codigos_e_Scripts": [".py", ".json", ".sql", ".js", ".ts", ".html", ".css", ".bat", ".ps1"]
}

class FileManagerService:
    def __init__(self):
        user_profile = os.environ.get("USERPROFILE", "C:\\Users\\dafnh")
        self.downloads_dir = os.path.join(user_profile, "Downloads")
        self.desktop_dir = os.path.join(user_profile, "Desktop")

    def _obter_pasta_alvo(self, termo: str) -> str:
        termo_limpo = termo.lower().strip()
        if "desktop" in termo_limpo or "área de trabalho" in termo_limpo or "area de trabalho" in termo_limpo:
            return self.desktop_dir
        elif os.path.isdir(termo):
            return termo
        return self.downloads_dir

    def analisar_pasta(self, pasta: str = "downloads") -> str:
        """
        Analisa a quantidade e tamanho de arquivos soltos na pasta sem mover nada.
        
        Args:
            pasta: 'downloads' (padrão) ou 'desktop'.
        """
        caminho = self._obter_pasta_alvo(pasta)
        if not os.path.exists(caminho):
            return f"Não encontrei o diretório '{caminho}', senhor."

        total_arquivos = 0
        tamanho_total = 0
        contagem_por_categoria = {cat: 0 for cat in CATEGORIAS}
        outros = 0

        for item in os.listdir(caminho):
            item_path = os.path.join(caminho, item)
            if os.path.isfile(item_path):
                total_arquivos += 1
                tamanho_total += os.path.getsize(item_path)
                ext = Path(item).suffix.lower()
                
                alocado = False
                for cat, exts in CATEGORIAS.items():
                    if ext in exts:
                        contagem_por_categoria[cat] += 1
                        alocado = True
                        break
                if not alocado:
                    outros += 1

        tamanho_mb = round(tamanho_total / (1024 * 1024), 1)
        nome_exibicao = "Downloads" if caminho == self.downloads_dir else "Área de Trabalho"

        if total_arquivos == 0:
            return f"A sua pasta de {nome_exibicao} já está totalmente limpa e organizada, senhor. Nenhum arquivo solto detectado."

        linhas = [
            f"Diagnóstico da pasta {nome_exibicao}, senhor:",
            f"• Total de arquivos soltos: {total_arquivos} ({tamanho_mb} MB ocupados)\n",
            "Distribuição por categoria:"
        ]
        for cat, qtd in contagem_por_categoria.items():
            if qtd > 0:
                linhas.append(f"  - {cat.replace('_', ' ')}: {qtd} arquivo(s)")
        if outros > 0:
            linhas.append(f"  - Outros formatos: {outros} arquivo(s)")

        linhas.append(f"\nSe desejar, basta pedir: 'Jarvis, organize a pasta de {nome_exibicao.lower()}'.")
        return "\n".join(linhas)

    def organizar_pasta(self, pasta: str = "downloads") -> str:
        """
        Move arquivos soltos para subpastas categorizadas por tipo (PDFs, Imagens, etc.).
        
        Args:
            pasta: 'downloads' (padrão) ou 'desktop'.
        """
        caminho = self._obter_pasta_alvo(pasta)
        if not os.path.exists(caminho):
            return f"Não encontrei o diretório '{caminho}', senhor."

        nome_exibicao = "Downloads" if caminho == self.downloads_dir else "Área de Trabalho"
        print(f"\n📂 [ORGANIZADOR] Organizando arquivos em '{caminho}'...")

        movidos = 0
        por_categoria = {cat: 0 for cat in CATEGORIAS}

        for item in os.listdir(caminho):
            item_path = os.path.join(caminho, item)
            # Ignora diretórios existentes
            if not os.path.isfile(item_path):
                continue

            ext = Path(item).suffix.lower()
            categoria_destino = None

            for cat, exts in CATEGORIAS.items():
                if ext in exts:
                    categoria_destino = cat
                    break

            if not categoria_destino:
                categoria_destino = "Outros_Arquivos"

            pasta_destino = os.path.join(caminho, categoria_destino)
            os.makedirs(pasta_destino, exist_ok=True)

            destino_final = os.path.join(pasta_destino, item)
            # Se houver colisão de nome, renomeia com sufixo
            if os.path.exists(destino_final):
                nome_base = Path(item).stem
                novo_nome = f"{nome_base}_organizado{ext}"
                destino_final = os.path.join(pasta_destino, novo_nome)

            try:
                shutil.move(item_path, destino_final)
                movidos += 1
                if categoria_destino in por_categoria:
                    por_categoria[categoria_destino] += 1
            except Exception as e:
                print(f"⚠️ [ORGANIZADOR] Não foi possível mover '{item}': {e}")

        if movidos == 0:
            return f"A sua pasta de {nome_exibicao} já está totalmente organizada, senhor."

        resumo_cats = [f"{cat.replace('_', ' ')} ({qtd})" for cat, qtd in por_categoria.items() if qtd > 0]
        detalhe = ", ".join(resumo_cats)
        return f"Organização da pasta {nome_exibicao} concluída com sucesso, senhor! {movidos} arquivos categorizados em: {detalhe}."

file_manager_service = FileManagerService()
