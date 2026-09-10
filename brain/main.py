"""
J.A.R.V.I.S. - Cérebro Central com Gemini AI
Controle de Voz, Automações e Simulador de Hardware
"""

import os
import sys
import time
import random
import threading
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

from hardware_simulator import hardware
from voice_engine import voice_engine
from google_calendar import calendar_service
from gmail_service import gmail_service
from waze_service import waze_service
from google_services import google_extended
from notion_service import notion_service
from weather_service import weather_service
from telegram_service import telegram_service
from spotify_service import spotify_service
from whatsapp_service import whatsapp_service
from windows_service import windows_service
from iot_service import iot_service
from web_search_service import web_search_service
from protocols_service import protocols_service
from file_manager_service import file_manager_service
from sentinel_service import sentinel_service

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Carregar variáveis de ambiente
load_dotenv()

# ==============================================================================
# DEFINIÇÃO DE FERRAMENTAS (TOOLS / FUNCTION CALLING PARA O GEMINI)
# ==============================================================================

def mover_braco_mecanico(acao: str, justificativa: str = "") -> str:
    """
    Aciona o braço robótico físico ou simulador para executar um gesto.
    
    Args:
        acao: Nome do movimento. Opções suportadas: 'acenar', 'apontar', 'repouso', 'positivo', 'alerta'.
        justificativa: Motivo pelo qual o braço está fazendo este movimento.
    """
    hardware.atualizar_tela(titulo="BRAÇO EM MOVIMENTO", subtitulo=f"Gesto: {acao.upper()}", icone="🦾")
    resultado = hardware.mover_braco(acao=acao, detalhes=justificativa)
    return resultado

def atualizar_painel_visual(titulo: str, subtitulo: str, icone: str = "🤖") -> str:
    """
    Atualiza as informações exibidas no display TFT 4.0" de mesa.
    
    Args:
        titulo: Texto principal do card (ex: 'PRÓXIMA REUNIÃO', 'CLIMA ATUAL', 'STATUS').
        subtitulo: Detalhe explicativo ou informação (ex: '15:00 - Reunião de Projeto').
        icone: Emoji ou símbolo representativo.
    """
    return hardware.atualizar_tela(titulo=titulo, subtitulo=subtitulo, icone=icone)

def gerenciar_agenda(acao: str, titulo: str = "", data_hora: str = "") -> str:
    """
    Gerencia eventos e compromissos do calendário/agenda pessoal no Google Calendar real.
    
    Args:
        acao: 'adicionar', 'consultar' ou 'remover'.
        titulo: Título ou assunto do compromisso (obrigatório para adicionar ou remover).
        data_hora: Data e horário do evento (ex: 'amanhã às 14h', '2026-09-10 15:00').
    """
    hardware.atualizar_tela(titulo="GOOGLE CALENDAR", subtitulo=f"{acao.upper()}: {titulo}", icone="📅")
    acao_limpa = acao.lower().strip()
    if "adic" in acao_limpa or "criar" in acao_limpa or "agend" in acao_limpa:
        return calendar_service.adicionar_evento(titulo=titulo, inicio_str=data_hora)
    elif "remov" in acao_limpa or "exclu" in acao_limpa or "cancel" in acao_limpa:
        return calendar_service.excluir_evento(termo_busca=titulo)
    else:
        return calendar_service.listar_proximos_eventos(max_eventos=5)

def enviar_recado_whatsapp(contato: str, mensagem: str) -> str:
    """
    Envia uma mensagem real no WhatsApp para um contato ou número de telefone.
    
    Args:
        contato: Nome do contato cadastrado na agenda (ex: 'Carlos', 'Mãe') ou número de telefone com DDD.
        mensagem: Conteúdo do recado a ser enviado.
    """
    hardware.atualizar_tela(titulo="WHATSAPP REAL", subtitulo=f"Para: {contato[:24]}", icone="💬")
    return whatsapp_service.enviar_mensagem(destinatario=contato, mensagem=mensagem)

def salvar_contato_whatsapp(nome: str, numero: str) -> str:
    """
    Salva ou atualiza um contato na agenda do WhatsApp do JARVIS.
    
    Args:
        nome: Nome ou apelido do contato (ex: 'Carlos', 'Mãe', 'Amor').
        numero: Número de telefone com DDD (ex: '27 99123-4567').
    """
    hardware.atualizar_tela(titulo="WHATSAPP - AGENDA", subtitulo=f"Salvo: {nome[:24]}", icone="📇")
    return whatsapp_service.salvar_contato(nome=nome, numero=numero)

def listar_contatos_whatsapp() -> str:
    """Consulta e lista todos os contatos salvos na agenda do WhatsApp do JARVIS."""
    return whatsapp_service.listar_contatos()

def consultar_data_hora_atual() -> str:
    """Retorna a data e hora atual do sistema."""
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    return f"A data e hora atual é {agora}."

def ler_ultimos_emails(quantidade: int = 3, apenas_nao_lidos: bool = True) -> str:
    """
    Consulta os últimos e-mails recebidos na caixa de entrada do Gmail.
    
    Args:
        quantidade: Quantidade de mensagens para listar (padrão: 3).
        apenas_nao_lidos: Se True, busca somente e-mails que ainda não foram lidos.
    """
    hardware.atualizar_tela(titulo="GMAIL - ENTRADA", subtitulo="Verificando mensagens...", icone="✉️")
    return gmail_service.ler_ultimos_emails(quantidade=quantidade, apenas_nao_lidos=apenas_nao_lidos)

def enviar_email(destinatario: str, assunto: str, corpo: str) -> str:
    """
    Envia um novo e-mail formal pelo Gmail.
    
    Args:
        destinatario: Endereço de e-mail do destinatário.
        assunto: Assunto do e-mail.
        corpo: Texto completo do e-mail.
    """
    hardware.atualizar_tela(titulo="GMAIL - ENVIAR", subtitulo=f"Para: {destinatario}", icone="📤")
    return gmail_service.enviar_email(destinatario=destinatario, assunto=assunto, corpo=corpo)

def consultar_rota_e_transito_waze(destino: str, origem: str = "") -> str:
    """
    Consulta o trânsito em tempo real, distância e tempo de viagem pelo Waze.
    
    Args:
        destino: Local de chegada ou endereço de destino (ex: 'Aeroporto de Congonhas', 'Shopping Morumbi' ou 'casa').
        origem: Local de partida (opcional, se omitido assume 'casa' ou ponto atual do usuário).
    """
    hardware.atualizar_tela(titulo="WAZE TRÂNSITO", subtitulo=f"Para: {destino[:28]}", icone="🚗")
    return waze_service.calcular_rota(destino=destino, origem=origem)

def cadastrar_endereco_favorito(tipo: str, endereco: str) -> str:
    """
    Cadastra ou atualiza o endereço de 'casa' ou 'trabalho' do usuário para consultas rápidas no Waze.
    
    Args:
        tipo: 'casa' ou 'trabalho'.
        endereco: Endereço completo (ex: 'Rua Augusta 500, Consolação, São Paulo - SP').
    """
    hardware.atualizar_tela(titulo="ENDEREÇO SALVO", subtitulo=f"{tipo.upper()}: {endereco[:24]}", icone="📍")
    return waze_service.salvar_endereco_favorito(tipo=tipo, endereco=endereco)

def gerenciar_tarefas_google(acao: str, titulo: str = "", notas: str = "") -> str:
    """
    Gerencia a lista de afazeres no Google Tasks (adicionar ou listar tarefas pendentes).
    
    Args:
        acao: 'adicionar' ou 'listar'.
        titulo: Título da tarefa a adicionar.
        notas: Detalhes ou observações da tarefa.
    """
    hardware.atualizar_tela(titulo="GOOGLE TASKS", subtitulo=f"{acao.upper()}: {titulo[:24]}", icone="✅")
    if "adic" in acao.lower() or "criar" in acao.lower():
        return google_extended.adicionar_tarefa(titulo=titulo, notas=notas)
    else:
        return google_extended.listar_tarefas(max_tarefas=5)

def tocar_musica_ou_video_youtube(termo_busca: str) -> str:
    """
    Pesquisa e reproduz vídeos, músicas ou podcasts no YouTube abrindo o navegador.
    
    Args:
        termo_busca: Nome da música, artista ou tema do vídeo a pesquisar.
    """
    hardware.atualizar_tela(titulo="YOUTUBE PLAYER", subtitulo=f"Tocando: {termo_busca[:24]}", icone="🎵")
    return google_extended.tocar_youtube(termo=termo_busca)

def registrar_gasto_financeiro(item: str, valor: float, categoria: str = "Geral") -> str:
    """
    Registra um gasto financeiro na Planilha Google do usuário.
    
    Args:
        item: Nome do produto ou serviço (ex: 'Almoço', 'Uber', 'Componentes').
        valor: Valor numérico em reais (ex: 45.50).
        categoria: Categoria do gasto (ex: 'Alimentação', 'Transporte', 'Tecnologia').
    """
    hardware.atualizar_tela(titulo="PLANILHA FINANCEIRA", subtitulo=f"R$ {valor:.2f} - {item}", icone="💵")
    return google_extended.registrar_gasto_planilha(item=item, valor=valor, categoria=categoria)

def adicionar_tarefa_notion(titulo: str, detalhes: str = "") -> str:
    """
    Adiciona uma nova tarefa ou cartão no banco de dados do Notion.
    
    Args:
        titulo: Título da tarefa a ser criada no Notion.
        detalhes: Observações ou descrição detalhada da tarefa.
    """
    hardware.atualizar_tela(titulo="NOTION - TAREFA", subtitulo=f"Criar: {titulo[:24]}", icone="📝")
    return notion_service.adicionar_tarefa(titulo=titulo, detalhes=detalhes)

def anotar_ideia_no_notion(texto: str) -> str:
    """
    Adiciona uma anotação rápida, ideia ou tópico na página de anotações do Notion.
    
    Args:
        texto: Conteúdo da ideia ou pensamento a ser anotado.
    """
    hardware.atualizar_tela(titulo="NOTION - NOTA", subtitulo="Anotando ideia...", icone="💡")
    return notion_service.anotar_ideia_ou_nota(texto=texto)

def consultar_notion(termo_busca: str = "") -> str:
    """
    Pesquisa e consulta páginas, bancos de dados e tarefas no Notion.
    
    Args:
        termo_busca: Palavra-chave a pesquisar ou vazio para listar itens acessíveis.
    """
    hardware.atualizar_tela(titulo="NOTION - BUSCA", subtitulo=f"Termo: {termo_busca[:24]}", icone="🔍")
    if termo_busca:
        return notion_service.buscar_no_notion(termo=termo_busca)
    return notion_service.listar_itens_compartilhados()

def consultar_clima_e_tempo(cidade_ou_local: str = "") -> str:
    """
    Consulta a previsão do tempo e clima em tempo real (temperatura, probabilidade de chuva, umidade, vento).
    
    Args:
        cidade_ou_local: Nome da cidade ou bairro. Se omitido, consulta o local de residência do usuário.
    """
    hardware.atualizar_tela(titulo="METEOROLOGIA", subtitulo=f"Clima: {cidade_ou_local if cidade_ou_local else 'Residência'}", icone="🌤️")
    return weather_service.consultar_clima(local=cidade_ou_local)

def enviar_mensagem_telegram(mensagem: str) -> str:
    """
    Envia uma mensagem de texto ou lembrete para o celular do usuário via Telegram.
    
    Args:
        mensagem: Conteúdo da mensagem a ser enviada no Telegram.
    """
    hardware.atualizar_tela(titulo="TELEGRAM", subtitulo=f"Envio: {mensagem[:24]}", icone="📱")
    return telegram_service.enviar_mensagem(texto=mensagem)

def tocar_no_spotify(busca: str = "", tipo: str = "track") -> str:
    """
    Pesquisa e reproduz músicas, artistas, álbuns ou playlists no Spotify.
    
    Args:
        busca: Nome da faixa, banda, álbum ou playlist. Se omitido, retoma a música pausada.
        tipo: Tipo da busca: 'track' (música), 'artist' (artista/banda), 'playlist' ou 'album'.
    """
    subtitulo = f"Tocando: {busca[:24]}" if busca else "Retomando música"
    hardware.atualizar_tela(titulo="SPOTIFY", subtitulo=subtitulo, icone="🎧")
    return spotify_service.tocar(termo_busca=busca, tipo=tipo)

def controlar_reproducao_spotify(acao: str, valor: int = 0) -> str:
    """
    Controla o reprodutor do Spotify (pausar, avançar próxima faixa, voltar faixa anterior ou ajustar volume).
    
    Args:
        acao: Ação desejada: 'pausar', 'retomar', 'proxima', 'anterior' ou 'volume'.
        valor: Valor numérico para o volume de 0 a 100 (usado apenas quando a acao for 'volume').
    """
    acao_limpa = acao.lower().strip()
    if "paus" in acao_limpa or "stop" in acao_limpa or "parar" in acao_limpa:
        hardware.atualizar_tela(titulo="SPOTIFY", subtitulo="Reprodução pausada", icone="⏸️")
        return spotify_service.pausar()
    elif "prox" in acao_limpa or "avanc" in acao_limpa or "pass" in acao_limpa or "next" in acao_limpa:
        hardware.atualizar_tela(titulo="SPOTIFY", subtitulo="Próxima faixa", icone="⏭️")
        return spotify_service.proxima_faixa()
    elif "ant" in acao_limpa or "volt" in acao_limpa or "prev" in acao_limpa:
        hardware.atualizar_tela(titulo="SPOTIFY", subtitulo="Faixa anterior", icone="⏮️")
        return spotify_service.faixa_anterior()
    elif "vol" in acao_limpa:
        hardware.atualizar_tela(titulo="SPOTIFY", subtitulo=f"Volume: {valor}%", icone="🔊")
        return spotify_service.ajustar_volume(valor)
    else:
        hardware.atualizar_tela(titulo="SPOTIFY", subtitulo="Retomando música", icone="▶️")
        return spotify_service.tocar()

def consultar_musica_atual_spotify() -> str:
    """Retorna os detalhes da música que está tocando no Spotify no momento."""
    hardware.atualizar_tela(titulo="SPOTIFY", subtitulo="Consultando faixa...", icone="🎵")
    return spotify_service.obter_musica_atual()

def controlar_volume_windows(acao: str, valor: int = 0) -> str:
    """
    Controla o volume de som do computador Windows (definir porcentagem, aumentar, diminuir, mutar ou desmutar).
    
    Args:
        acao: 'definir' (ex: valor=50), 'aumentar', 'diminuir', 'mutar', 'desmutar' ou 'consultar'.
        valor: Porcentagem de 0 a 100 para o volume (quando acao for 'definir', 'aumentar' ou 'diminuir').
    """
    sub = f"Volume: {valor}%" if valor > 0 else f"Ação: {acao.upper()}"
    hardware.atualizar_tela(titulo="VOLUME WINDOWS", subtitulo=sub, icone="🔊")
    return windows_service.controlar_volume(acao=acao, valor=valor)

def bloquear_computador() -> str:
    """Bloqueia a tela da estação de trabalho do Windows imediatamente por segurança."""
    hardware.atualizar_tela(titulo="SEGURANÇA", subtitulo="PC BLOQUEADO", icone="🔒")
    return windows_service.bloquear_computador()

def abrir_programa_windows(nome_programa: str) -> str:
    """
    Abre programas ou ferramentas no Windows (ex: 'VS Code', 'Chrome', 'Calculadora', 'Steam', 'Bloco de Notas', 'Explorador').
    
    Args:
        nome_programa: Nome do programa a ser aberto.
    """
    hardware.atualizar_tela(titulo="INICIAR PROGRAMA", subtitulo=f"Abrir: {nome_programa[:24]}", icone="🚀")
    return windows_service.abrir_aplicativo(nome_app=nome_programa)

def fechar_programa_windows(nome_programa: str) -> str:
    """
    Encerra um programa em execução no Windows.
    
    Args:
        nome_programa: Nome do programa a ser fechado.
    """
    hardware.atualizar_tela(titulo="FECHAR PROGRAMA", subtitulo=f"Encerrar: {nome_programa[:24]}", icone="⏹️")
    return windows_service.fechar_aplicativo(nome_processo=nome_programa)

def consultar_status_computador() -> str:
    """Retorna o uso de CPU, memória RAM ocupada, espaço em disco e bateria do computador."""
    hardware.atualizar_tela(titulo="TELEMETRIA PC", subtitulo="Consultando status...", icone="📊")
    return windows_service.obter_telemetria()

def analisar_o_que_esta_na_tela(duvida: str = "") -> str:
    """
    Tira um screenshot da tela do computador e analisa visualmente com a IA do Gemini para tirar dúvidas ou resumir.
    
    Args:
        duvida: Pergunta ou instrução sobre o que analisar na tela.
    """
    hardware.atualizar_tela(titulo="VISÃO DE TELA", subtitulo="Analisando display...", icone="👁️")
    return windows_service.analisar_tela(pergunta=duvida)

def tirar_foto_e_enviar_ao_telegram(legenda: str = "") -> str:
    """
    Tira uma foto em tempo real usando a câmera frontal (webcam) do computador e envia para o Telegram do usuário.
    
    Args:
        legenda: Texto ou descrição opcional para acompanhar a foto no Telegram.
    """
    hardware.atualizar_tela(titulo="WEBCAM FOTO", subtitulo="Capturando imagem...", icone="📸")
    return windows_service.tirar_foto_e_enviar_telegram(legenda=legenda)

def analisar_visao_da_camera(pergunta: str = "") -> str:
    """
    Aciona a câmera frontal do computador e analisa visualmente com a IA o que ou quem está na frente da mesa/PC.
    
    Args:
        pergunta: Pergunta específica sobre o que a câmera está vendo.
    """
    hardware.atualizar_tela(titulo="VISÃO WEBCAM", subtitulo="Analisando ambiente...", icone="👁️")
    return windows_service.analisar_ambiente_webcam(pergunta=pergunta)

def controlar_dispositivos_casa_inteligente(dispositivo: str, acao: str, valor: str = "") -> str:
    """
    Controla lâmpadas inteligentes, fitas LED, tomadas ou aparelhos de casa inteligente (ligar, desligar, brilho ou cor).
    
    Args:
        dispositivo: Nome do dispositivo ou termo (ex: 'luz do quarto', 'fita led', 'abajur', 'tomada', 'todas as luzes', 'tudo').
        acao: 'ligar', 'desligar', 'alternar', 'brilho', 'cor' ou 'consultar'.
        valor: Porcentagem de brilho (0 a 100) ou nome da cor (ex: 'azul', 'vermelho', 'verde', 'ciano', 'branco quente', 'ambar').
    """
    hardware.atualizar_tela(titulo="CASA INTELIGENTE", subtitulo=f"{acao.upper()}: {dispositivo[:18]}", icone="💡")
    return iot_service.controlar(dispositivo=dispositivo, acao=acao, valor=valor)

def consultar_status_casa_inteligente(dispositivo: str = "") -> str:
    """
    Retorna o status atual dos dispositivos de iluminação e automação residencial inteligente.
    
    Args:
        dispositivo: Nome ou termo específico do dispositivo a consultar (opcional, deixe em branco para ver todos).
    """
    hardware.atualizar_tela(titulo="STATUS IOT", subtitulo="Consultando luzes...", icone="🏠")
    return iot_service.listar_status(dispositivo=dispositivo)

def pesquisar_na_web(consulta: str, quantidade: int = 4) -> str:
    """
    Realiza uma pesquisa em tempo real na internet para buscar notícias, cotações, esportes, preços ou fatos recentes.
    
    Args:
        consulta: Dúvida ou termo a pesquisar na web.
        quantidade: Quantidade máxima de resultados (padrão 4).
    """
    hardware.atualizar_tela(titulo="BUSCA WEB", subtitulo=f"Busca: {consulta[:20]}", icone="🌐")
    return web_search_service.pesquisar_web(consulta=consulta, max_resultados=quantidade)

def resumir_video_youtube(url_ou_id: str, instrucao_foco: str = "") -> str:
    """
    Baixa a transcrição de um vídeo do YouTube e gera um resumo executivo com pontos-chave e conclusões usando a IA.
    
    Args:
        url_ou_id: Link completo do YouTube (ex: 'https://youtube.com/watch?v=...') ou ID do vídeo.
        instrucao_foco: Instrução opcional sobre o que focar no resumo.
    """
    hardware.atualizar_tela(titulo="RESUMO YOUTUBE", subtitulo="Analisando vídeo...", icone="📺")
    return web_search_service.resumir_youtube(url_ou_id=url_ou_id, instrucao=instrucao_foco)

def executar_protocolo_stark(nome_protocolo: str) -> str:
    """
    Executa protocolos e rotinas macro de automação integrada: 'foco' (trabalho/estudo), 'cinema' (filmes/lazer), 'sair_da_base' (trancar PC, luzes e foto no Telegram) ou 'bom_dia' (clima, status e música).
    
    Args:
        nome_protocolo: Nome do protocolo ('foco', 'cinema', 'sair_da_base' ou 'bom_dia').
    """
    return protocols_service.executar(nome_protocolo=nome_protocolo)

def organizar_arquivos_pasta(pasta: str = "downloads") -> str:
    """
    Organiza arquivos soltos da pasta Downloads ou Área de Trabalho categorizando-os em subpastas por tipo (PDFs, Imagens, Documentos, Instaladores, etc.).
    
    Args:
        pasta: 'downloads' (padrão) ou 'desktop' (área de trabalho).
    """
    hardware.atualizar_tela(titulo="ORGANIZAR ARQUIVOS", subtitulo=f"Pasta: {pasta[:18]}", icone="📂")
    return file_manager_service.organizar_pasta(pasta=pasta)

def analisar_arquivos_pasta(pasta: str = "downloads") -> str:
    """
    Analisa a quantidade, tipos e tamanho em MB dos arquivos soltos na pasta de Downloads ou Área de Trabalho sem mover nada.
    
    Args:
        pasta: 'downloads' (padrão) ou 'desktop'.
    """
    hardware.atualizar_tela(titulo="DIAGNÓSTICO PASTAS", subtitulo=f"Varrendo {pasta[:16]}...", icone="📊")
    return file_manager_service.analisar_pasta(pasta=pasta)

def ativar_modo_sentinela(duracao_minutos: int = 60) -> str:
    """
    Ativa o Modo Sentinela de vigilância pela câmera frontal. Ao detectar qualquer movimento, tranca o PC e envia foto de alerta ao Telegram.
    
    Args:
        duracao_minutos: Tempo em minutos da vigilância (padrão 60 minutos).
    """
    return sentinel_service.ativar(duracao_minutos=duracao_minutos)

def desativar_modo_sentinela() -> str:
    """Desativa o Modo Sentinela de vigilância por câmera frontal."""
    return sentinel_service.desativar()

def consultar_status_sentinela() -> str:
    """Retorna se a vigilância sentinela está ativa e se houve registro de invasores/movimento."""
    return sentinel_service.consultar_status()

# Lista de funções para o Gemini
JARVIS_TOOLS = [
    mover_braco_mecanico,
    atualizar_painel_visual,
    gerenciar_agenda,
    ler_ultimos_emails,
    enviar_email,
    consultar_rota_e_transito_waze,
    cadastrar_endereco_favorito,
    consultar_clima_e_tempo,
    gerenciar_tarefas_google,
    adicionar_tarefa_notion,
    anotar_ideia_no_notion,
    consultar_notion,
    tocar_no_spotify,
    controlar_reproducao_spotify,
    consultar_musica_atual_spotify,
    tocar_musica_ou_video_youtube,
    registrar_gasto_financeiro,
    enviar_recado_whatsapp,
    salvar_contato_whatsapp,
    listar_contatos_whatsapp,
    enviar_mensagem_telegram,
    controlar_volume_windows,
    bloquear_computador,
    abrir_programa_windows,
    fechar_programa_windows,
    consultar_status_computador,
    analisar_o_que_esta_na_tela,
    tirar_foto_e_enviar_ao_telegram,
    analisar_visao_da_camera,
    controlar_dispositivos_casa_inteligente,
    consultar_status_casa_inteligente,
    pesquisar_na_web,
    resumir_video_youtube,
    executar_protocolo_stark,
    organizar_arquivos_pasta,
    analisar_arquivos_pasta,
    ativar_modo_sentinela,
    desativar_modo_sentinela,
    consultar_status_sentinela,
    consultar_data_hora_atual
]

JARVIS_SYSTEM_INSTRUCTION = """
Você é o J.A.R.V.I.S., o assistente pessoal inteligente, educado, eficiente e leal criado para auxiliar o senhor em todas as suas tarefas diárias.

DIRETRIZES DE PERSONALIDADE:
1. Chame o usuário sempre de "senhor" de maneira elegante, polida e prestativa (estilo o Jarvis de Tony Stark).
2. Seja conciso e direto na fala por voz, evitando parágrafos excessivamente longos.
3. Utilize suas ferramentas (tools) sempre que o usuário pedir ações práticas:
   - Se ele pedir para acenar, apontar ou reagir fisicamente, acione 'mover_braco_mecanico'.
   - Se for algo de agenda, use 'gerenciar_agenda'.
   - Se for e-mails, use 'ler_ultimos_emails' ou 'enviar_email'.
   - Se perguntar sobre tempo de viagem, rota ou trânsito, acione 'consultar_rota_e_transito_waze'.
   - Se pedir para salvar endereço de casa ou trabalho, use 'cadastrar_endereco_favorito'.
   - Se perguntar sobre clima, previsão do tempo ou chuva, use 'consultar_clima_e_tempo'.
   - Se for Notion (tarefas, ideias, notas ou consultas no Notion), use 'adicionar_tarefa_notion', 'anotar_ideia_no_notion' ou 'consultar_notion'.
   - Se for tarefas do Google, use 'gerenciar_tarefas_google'.
   - Se pedir para tocar música no Spotify, use 'tocar_no_spotify'.
   - Se pedir para pausar, passar para a próxima música, voltar ou ajustar volume do Spotify, use 'controlar_reproducao_spotify'.
   - Se perguntar qual música está tocando no momento, use 'consultar_musica_atual_spotify'.
   - Se pedir para tocar vídeo ou música especificamente no YouTube, acione 'tocar_musica_ou_video_youtube'.
   - Se mencionar registro de gastos ou despesas, use 'registrar_gasto_financeiro'.
   - Se for aviso ou recado no WhatsApp, use 'enviar_recado_whatsapp'.
   - Se pedir para salvar contato na agenda do WhatsApp, use 'salvar_contato_whatsapp' ou para ver contatos use 'listar_contatos_whatsapp'.
   - Se pedir para controlar volume do computador (som do Windows), use 'controlar_volume_windows'.
   - Se pedir para bloquear ou trancar o computador/PC, use 'bloquear_computador'.
   - Se pedir para abrir programas (VS Code, Chrome, Steam, etc.), use 'abrir_programa_windows'. Para fechar programas, use 'fechar_programa_windows'.
   - Se perguntar como está o computador, uso de CPU, memória ou status geral do PC, use 'consultar_status_computador'.
   - Se pedir para olhar o que está na tela ou tirar print para tirar dúvidas, use 'analisar_o_que_esta_na_tela'.
   - Se pedir para tirar uma foto pela câmera/webcam e enviar no Telegram (ou pelo celular), use 'tirar_foto_e_enviar_ao_telegram'.
   - Se pedir para a câmera olhar quem ou o que está na frente do PC, use 'analisar_visao_da_camera'.
   - Se o usuário pedir para enviar algo no Telegram ou avisar no celular dele, use 'enviar_mensagem_telegram'.
   - Se o usuário pedir para acender, ligar, apagar ou mudar a cor/brilho de luzes, lâmpadas ou tomadas inteligentes, use 'controlar_dispositivos_casa_inteligente'. Para ver o status das luzes, use 'consultar_status_casa_inteligente'.
   - Se o usuário pedir para pesquisar algo na internet, cotações de moedas, notícias do dia ou fatos em tempo real, use 'pesquisar_na_web'.
   - Se o usuário enviar um link do YouTube ou pedir o resumo de um vídeo, use 'resumir_video_youtube'.
   - Se o usuário pedir para ativar um protocolo ou rotina (ex: 'protocolo foco', 'modo trabalho', 'protocolo cinema', 'modo filme', 'sair da base', 'trancar estação' ou 'bom dia'), use 'executar_protocolo_stark'.
   - Se o usuário pedir para organizar a pasta de downloads ou área de trabalho (desktop), use 'organizar_arquivos_pasta'. Para ver o diagnóstico dos arquivos soltos antes de organizar, use 'analisar_arquivos_pasta'.
   - Se o usuário pedir para ativar o modo sentinela, vigiar a mesa/câmera ou monitorar intrusos, use 'ativar_modo_sentinela'. Para desativar, use 'desativar_modo_sentinela' e para ver o status use 'consultar_status_sentinela'.
   - Sempre que fizer uma ação importante, atualize a tela com 'atualizar_painel_visual'.
4. Confirme as ações de forma natural e sofisticada após a execução das ferramentas.
"""

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "sua_chave_gemini_aqui":
        print("\n" + "!"*60)
        print("⚠️  CHAVE DO GEMINI NÃO ENCONTRADA!")
        print("Obtenha sua chave gratuita em: https://aistudio.google.com/")
        api_key = input("Cole sua chave GEMINI_API_KEY aqui: ").strip()
        if not api_key:
            print("Chave não informada. Encerrando.")
            sys.exit(1)
        # Salvar no .env para as próximas vezes
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={api_key}\n")
        print("✅ Chave salva no arquivo .env!")

    print("\n" + "="*60)
    print("       J.A.R.V.I.S. - PROTOCOLO INICIALIZADO")
    print("="*60)

    # Inicializar cliente Gemini
    client = genai.Client(api_key=api_key)
    
    # Criar sessão de Chat com ferramentas automáticas
    chat = client.chats.create(
        model="gemini-3.5-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=JARVIS_SYSTEM_INSTRUCTION,
            tools=JARVIS_TOOLS,
            temperature=0.7,
        )
    )
    
    # Trava de concorrência thread-safe para o chat
    chat_lock = threading.Lock()

    # Inicializar listener do Telegram Bot em segundo plano
    telegram_service.iniciar_em_segundo_plano(gemini_chat=chat, chat_lock=chat_lock)

    saudacao_inicial = "Sistemas online e operantes, senhor. O braço robótico e o painel visual estão em prontidão. Como posso auxiliá-lo hoje?"
    hardware.atualizar_tela(titulo="JARVIS ONLINE", subtitulo="Aguardando comandos...", icone="⚡")
    voice_engine.speak(saudacao_inicial)

    print("\nMODOS DE ENTRADA DISPONÍVEIS:")
    print("1. Pressione ENTER para falar no microfone")
    print("2. Ou digite sua mensagem diretamente no teclado")
    print("3. Digite 'sair' para encerrar.\n")

    while True:
        try:
            modo = input("\n[Pressione ENTER para falar, ou digite o texto]: ").strip()
            
            if modo.lower() in ["sair", "exit", "quit"]:
                despedida = "Encerrando protocolos senhor. Até logo."
                hardware.mover_braco("repouso")
                voice_engine.speak(despedida)
                break
                
            mensagem_usuario = ""
            if modo == "":
                # Modo microfone: muda rosto para ouvindo
                hardware.desenhar_rosto_oled("OUVINDO")
                mensagem_usuario = voice_engine.listen()
                if not mensagem_usuario:
                    hardware.desenhar_rosto_oled("NEUTRO")
                    continue
            else:
                mensagem_usuario = modo

            print(f"\n🤔 [JARVIS PROCESSANDO] Analisando sua solicitação...")
            
            # Envio resiliente thread-safe com backoff exponencial e jitter
            resposta = None
            for tentativa in range(3):
                try:
                    with chat_lock:
                        resposta = chat.send_message(mensagem_usuario)
                    break
                except Exception as e_gem:
                    err_msg = str(e_gem)
                    if any(t in err_msg for t in ["503", "UNAVAILABLE", "high demand", "429"]):
                        espera = min(2 ** tentativa + random.uniform(0.1, 0.9), 8)
                        print(f"⚠️ [GEMINI] Servidor com alta demanda temporária (503). Retentando em {espera:.1f}s ({tentativa+1}/3)...")
                        time.sleep(espera)
                    else:
                        raise e_gem

            # Se as 3 tentativas falharem com 503, aciona o modelo secundário gemini-2.5-flash
            if not resposta:
                print("🔄 [GEMINI] Alternando para rota de contingência (gemini-2.5-flash)...")
                chat_secundario = client.chats.create(
                    model="gemini-2.5-flash",
                    config=types.GenerateContentConfig(
                        system_instruction=JARVIS_SYSTEM_INSTRUCTION,
                        tools=JARVIS_TOOLS,
                        temperature=0.7,
                    )
                )
                with chat_lock:
                    resposta = chat_secundario.send_message(mensagem_usuario)
            
            texto_resposta = resposta.text if resposta.text else "Comando executado com sucesso, senhor."
            voice_engine.speak(texto_resposta)

        except KeyboardInterrupt:
            print("\nEncerrando JARVIS...")
            break
        except Exception as e:
            print(f"\n❌ Erro durante o processamento: {e}")

if __name__ == "__main__":
    main()
