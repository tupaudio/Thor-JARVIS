"""
Módulo de Busca Web em Tempo Real e Resumo de Vídeos do YouTube para o J.A.R.V.I.S.
Permite consultar informações em tempo real (notícias, cotações, esportes, artigos)
e extrair transcrições de vídeos do YouTube para análise e resumos com a IA.
"""

import os
import sys
import re
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class WebSearchService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")

    def _obter_ddgs(self):
        try:
            from ddgs import DDGS
            return DDGS()
        except ImportError:
            from duckduckgo_search import DDGS
            return DDGS()

    def pesquisar_web(self, consulta: str, max_resultados: int = 4) -> str:
        """
        Realiza uma pesquisa em tempo real na web usando DuckDuckGo.
        
        Args:
            consulta: Termo ou dúvida a ser pesquisada na internet.
            max_resultados: Quantidade de resultados a retornar (padrão 4).
        """
        if not consulta or not consulta.strip():
            return "Por favor informe o termo que deseja pesquisar, senhor."

        termo = consulta.strip()
        print(f"\n🌐 [BUSCA WEB] Pesquisando na internet: '{termo}'...")

        try:
            ddgs = self._obter_ddgs()
            # Se a consulta menciona notícias, tenta busca de notícias primeiro
            is_noticia = any(k in termo.lower() for k in ["notícia", "noticia", "ultimas", "últimas", "hoje", "aconteceu"])
            resultados = []
            
            if is_noticia:
                try:
                    raw_news = list(ddgs.news(query=termo, region="br-pt", max_results=max_resultados))
                    for item in raw_news:
                        resultados.append({
                            "titulo": item.get("title", ""),
                            "resumo": item.get("body", ""),
                            "fonte": item.get("source", ""),
                            "link": item.get("url", "")
                        })
                except Exception:
                    pass

            if not resultados:
                raw_text = list(ddgs.text(query=termo, region="br-pt", max_results=max_resultados))
                for item in raw_text:
                    resultados.append({
                        "titulo": item.get("title", ""),
                        "resumo": item.get("body", ""),
                        "fonte": "Web",
                        "link": item.get("href", "")
                    })

            if not resultados:
                return f"Não encontrei resultados na web para '{consulta}', senhor."

            linhas = [f"Resultados da pesquisa em tempo real para '{termo}':\n"]
            for i, res in enumerate(resultados, 1):
                linhas.append(f"{i}. {res['titulo']}")
                linhas.append(f"   Trecho: {res['resumo']}")
                linhas.append(f"   Fonte/Link: {res['link']}\n")

            return "\n".join(linhas)

        except Exception as e:
            print(f"⚠️ [BUSCA WEB] Erro na pesquisa: {e}")
            return f"Houve uma oscilação ao consultar a internet para '{consulta}': {e}"

    def _extrair_id_youtube(self, url_ou_id: str) -> str:
        """Extrai o ID do vídeo a partir de URLs comuns do YouTube ou retorna o ID direto."""
        texto = url_ou_id.strip()
        
        # Padrões comuns de URL
        padroes = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"youtu\.be\/([0-9A-Za-z_-]{11})",
            r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})",
            r"^([0-9A-Za-z_-]{11})$"
        ]
        
        for p in padroes:
            match = re.search(p, texto)
            if match:
                return match.group(1)
                
        return ""

    def resumir_youtube(self, url_ou_id: str, instrucao: str = "") -> str:
        """
        Extrai a transcrição de um vídeo do YouTube e gera um resumo executivo com IA.
        
        Args:
            url_ou_id: Link completo do YouTube (ex: 'https://youtu.be/...') ou ID do vídeo.
            instrucao: Foco específico do resumo (ex: 'destaque as ferramentas mencionadas').
        """
        video_id = self._extrair_id_youtube(url_ou_id)
        if not video_id:
            return "Não consegui identificar um link ou ID válido do YouTube na sua solicitação, senhor."

        print(f"\n📺 [YOUTUBE SUMMARIZER] Baixando transcrição do vídeo '{video_id}'...")

        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            # Tenta português primeiro, depois inglês ou automático
            transcricao_lista = None
            try:
                transcricao_lista = YouTubeTranscriptApi.get_transcript(video_id, languages=['pt', 'pt-BR', 'en'])
            except Exception:
                # Fallback: lista transcrições disponíveis
                transcripts_disp = YouTubeTranscriptApi.list_transcripts(video_id)
                # Pega a primeira que encontrar
                for t in transcripts_disp:
                    transcricao_lista = t.fetch()
                    break

            if not transcricao_lista:
                return "Não foi possível obter legendas ou transcrição para este vídeo do YouTube, senhor. O canal pode não ter disponibilizado áudio transcrito."

            texto_completo = " ".join([item.get("text", "") for item in transcricao_lista])
            
            # Limita tamanho para caber no contexto do modelo
            if len(texto_completo) > 35000:
                texto_completo = texto_completo[:35000] + "... [Transcrição truncada por limite]"

            print(f"🧠 [YOUTUBE SUMMARIZER] Analisando {len(texto_completo)} caracteres com Gemini...")
            
            from google import genai
            client = genai.Client(api_key=self.api_key)
            
            foco = f"Foco solicitado pelo usuário: {instrucao}." if instrucao else ""
            prompt = (
                "Você é o J.A.R.V.I.S., assistente pessoal de alto nível. "
                "Analise a seguinte transcrição de um vídeo do YouTube e elabore um resumo executivo elegante, "
                "estruturado nos seguintes tópicos:\n"
                "1. Ideia Central do Vídeo\n"
                "2. Pontos-Chave & Lições Práticas (em tópicos com bullets)\n"
                "3. Conclusão Final\n"
                f"{foco}\n"
                "Chame o usuário de senhor e seja direto e objetivo.\n\n"
                f"TRANSCRIÇÃO DO VÍDEO:\n{texto_completo}"
            )

            resposta = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[prompt]
            )

            return resposta.text if resposta.text else "Não consegui gerar o resumo do vídeo, senhor."

        except Exception as e:
            print(f"⚠️ [YOUTUBE SUMMARIZER] Erro: {e}")
            return f"Não foi possível processar o vídeo do YouTube: {e}"

web_search_service = WebSearchService()
