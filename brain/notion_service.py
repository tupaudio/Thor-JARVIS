"""
Módulo de Integração com o Notion para o JARVIS.
Permite criar tarefas, pesquisar páginas e adicionar anotações rápidas por voz.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from notion_client import Client

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

class NotionService:
    def __init__(self):
        self.token = os.getenv("NOTION_API_KEY")
        self.client = None
        if self.token and not self.token.startswith("sua_"):
            try:
                self.client = Client(auth=self.token)
            except Exception as e:
                print(f"⚠️ [NOTION AVISO] Erro ao inicializar cliente: {e}")

    def _obter_primeiro_banco(self):
        """Busca o primeiro banco de dados compartilhado com o JARVIS."""
        if not self.client:
            return None
        try:
            res = self.client.search(filter={"value": "database", "property": "object"}).get("results", [])
            if res:
                return res[0]
        except Exception:
            pass
        return None

    def _obter_primeira_pagina(self):
        """Busca a primeira página compartilhada com o JARVIS."""
        if not self.client:
            return None
        try:
            res = self.client.search(filter={"value": "page", "property": "object"}).get("results", [])
            if res:
                return res[0]
        except Exception:
            pass
        return None

    def listar_itens_compartilhados(self) -> str:
        """Lista todas as páginas e bancos de dados aos quais o JARVIS tem acesso."""
        if not self.client:
            return "Chave do Notion não configurada no arquivo .env."

        try:
            res = self.client.search().get("results", [])
            if not res:
                return (
                    "O JARVIS está conectado à sua conta, mas o senhor ainda não compartilhou nenhuma página com ele. "
                    "Para liberar uma página ou banco, abra-o no Notion, clique nos 3 pontinhos (...) no topo direito, "
                    "vá em 'Conexões' e selecione 'JARVIS'."
                )

            lista = "Páginas e Bancos acessíveis no seu Notion:\n"
            for item in res:
                tipo = item.get("object", "item")
                titulo = "Sem título"
                if tipo == "database":
                    t_arr = item.get("title", [])
                    if t_arr:
                        titulo = t_arr[0].get("plain_text", "Sem título")
                elif tipo == "page":
                    props = item.get("properties", {})
                    for p in props.values():
                        if p.get("type") == "title":
                            t_arr = p.get("title", [])
                            if t_arr:
                                titulo = t_arr[0].get("plain_text", "Sem título")
                lista += f"- [{tipo.upper()}] {titulo}\n"

            return lista
        except Exception as e:
            return f"Erro ao consultar itens no Notion: {e}"

    def adicionar_tarefa(self, titulo: str, detalhes: str = "") -> str:
        """
        Adiciona uma nova tarefa no primeiro banco de dados compartilhado com o JARVIS.
        """
        if not self.client:
            return "Notion não configurado."

        try:
            db = self._obter_primeiro_banco()
            if not db:
                # Se não tem banco de dados, tenta adicionar como subpágina ou nota na primeira página
                pag = self._obter_primeira_pagina()
                if pag:
                    return self.anotar_ideia_ou_nota(f"Tarefa: {titulo} ({detalhes})")
                return (
                    "Não encontrei nenhum banco de dados ou página compartilhada com o JARVIS no Notion. "
                    "Por favor, compartilhe a sua página de tarefas com a conexão JARVIS nos 3 pontinhos (...) do Notion."
                )

            db_id = db.get("id")
            
            # Descobrir qual propriedade é o título (Name, Nome, Tarefa, Title, etc.)
            prop_titulo = "Name"
            for k, v in db.get("properties", {}).items():
                if v.get("type") == "title":
                    prop_titulo = k
                    break

            nova_pagina = {
                "parent": {"database_id": db_id},
                "properties": {
                    prop_titulo: {
                        "title": [{"text": {"content": titulo}}]
                    }
                }
            }

            # Se houver detalhes, adiciona como bloco de texto na página
            children = []
            if detalhes:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": detalhes}}]
                    }
                })

            if children:
                nova_pagina["children"] = children

            self.client.pages.create(**nova_pagina)
            print(f"📝 [NOTION TAREFA] Criada com sucesso: '{titulo}'")
            return f"Tarefa '{titulo}' adicionada com sucesso ao seu Notion, senhor."
        except Exception as e:
            return f"Erro ao adicionar tarefa no Notion: {e}"

    def anotar_ideia_ou_nota(self, texto: str) -> str:
        """
        Adiciona um tópico ou nota rápida no final da primeira página compartilhada.
        """
        if not self.client:
            return "Notion não configurado."

        try:
            pag = self._obter_primeira_pagina()
            if not pag:
                return (
                    "Nenhuma página do Notion está compartilhada com o JARVIS ainda. "
                    "Abra a página de notas no Notion, clique nos 3 pontinhos (...) e conecte o JARVIS."
                )

            page_id = pag.get("id")
            agora = datetime.now().strftime("%d/%m %H:%M")
            bloco = {
                "children": [
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [
                                {"type": "text", "text": {"content": f"[{agora}] {texto}"}}
                            ]
                        }
                    }
                ]
            }

            self.client.blocks.children.append(block_id=page_id, **bloco)
            print(f"💡 [NOTION NOTA] Anotado: '{texto}'")
            return f"Anotação registrada com sucesso no seu Notion: '{texto}', senhor."
        except Exception as e:
            return f"Erro ao adicionar anotação no Notion: {e}"

    def buscar_no_notion(self, termo: str) -> str:
        """
        Pesquisa conteúdos em todas as páginas e bancos compartilhados no Notion.
        """
        if not self.client:
            return "Notion não configurado."

        try:
            res = self.client.search(query=termo).get("results", [])
            if not res:
                return f"Não encontrei nenhuma nota ou tarefa contendo '{termo}' no seu Notion, senhor."

            resposta = f"Encontrei os seguintes resultados no Notion para '{termo}':\n"
            for item in res[:4]:
                tipo = item.get("object")
                titulo = "Sem título"
                if tipo == "database":
                    t_arr = item.get("title", [])
                    if t_arr:
                        titulo = t_arr[0].get("plain_text", "Sem título")
                elif tipo == "page":
                    props = item.get("properties", {})
                    for p in props.values():
                        if p.get("type") == "title":
                            t_arr = p.get("title", [])
                            if t_arr:
                                titulo = t_arr[0].get("plain_text", "Sem título")
                resposta += f"- {titulo} ({tipo})\n"

            return resposta
        except Exception as e:
            return f"Erro ao buscar no Notion: {e}"

notion_service = NotionService()
