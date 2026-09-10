"""
Módulo de Integração com o Spotify Web API para o J.A.R.V.I.S.
Permite tocar músicas, playlists, artistas, pausar, avançar faixas,
regular volume e consultar o que está tocando por voz e pelo Telegram.
"""

import os
import sys
import subprocess
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

SPOTIFY_SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative"
]

class SpotifyService:
    def __init__(self):
        self.client_id = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:9090").strip()
        self.cache_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".spotify_cache"))
        self._sp = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.client_id != "seu_spotify_client_id_aqui")

    def _obter_cliente(self) -> spotipy.Spotify:
        """Autentica e retorna a instância da API do Spotify."""
        if not self.is_configured():
            return None
        
        if self._sp:
            return self._sp

        auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scope=" ".join(SPOTIFY_SCOPES),
            cache_path=self.cache_path,
            open_browser=True
        )
        self._sp = spotipy.Spotify(auth_manager=auth_manager)
        return self._sp

    def _obter_dispositivo_ativo(self, sp: spotipy.Spotify):
        """Retorna o ID do dispositivo ativo ou o primeiro disponível."""
        try:
            devices = sp.devices().get("devices", [])
            if not devices:
                return None
            for d in devices:
                if d.get("is_active"):
                    return d.get("id")
            return devices[0].get("id")
        except Exception:
            return None

    def tocar(self, termo_busca: str = "", tipo: str = "track") -> str:
        """
        Inicia ou retoma a reprodução de uma música, artista, álbum ou playlist.
        
        Args:
            termo_busca: Nome da faixa, banda ou playlist a pesquisar. Se vazio, retoma reprodução.
            tipo: 'track' (música), 'artist' (artista), 'playlist' ou 'album'.
        """
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado no arquivo .env."

        # Se não informou termo de busca, tenta apenas despausar
        if not termo_busca or termo_busca.strip() == "":
            try:
                sp.start_playback()
                return "Reprodução do Spotify retomada, senhor."
            except Exception as e:
                # Tenta abrir aplicativo no Windows se não houver dispositivo ativo
                if "NO_ACTIVE_DEVICE" in str(e).upper() or "NOT FOUND" in str(e).upper():
                    subprocess.Popen(["cmd.exe", "/c", "start spotify:"], shell=True)
                    return "Iniciando o Spotify no seu computador, senhor. Por favor aguarde um instante."
                return f"Não foi possível retomar o Spotify: {e}"

        print(f"\n🎵 [SPOTIFY BUSCA] Pesquisando {tipo} por '{termo_busca}'...")
        try:
            device_id = self._obter_dispositivo_ativo(sp)
            tipo_limpo = tipo.lower().strip()
            
            # Mapeamento do tipo de busca
            search_type = "track"
            if "artist" in tipo_limpo or "cantor" in tipo_limpo or "banda" in tipo_limpo:
                search_type = "artist"
            elif "playlist" in tipo_limpo or "lista" in tipo_limpo:
                search_type = "playlist"
            elif "album" in tipo_limpo or "álbum" in tipo_limpo:
                search_type = "album"

            resultado = sp.search(q=termo_busca, limit=1, type=search_type)
            
            if search_type == "track" and resultado.get("tracks", {}).get("items"):
                track = resultado["tracks"]["items"][0]
                track_uri = track["uri"]
                track_name = track["name"]
                artist_name = track["artists"][0]["name"]
                
                try:
                    sp.start_playback(device_id=device_id, uris=[track_uri])
                except Exception:
                    # Fallback abre direto o link / URI do Spotify no Windows
                    subprocess.Popen(["cmd.exe", "/c", f"start {track_uri}"], shell=True)
                
                return f"Reproduzindo '{track_name}' de {artist_name} no Spotify."

            elif search_type == "artist" and resultado.get("artists", {}).get("items"):
                artist = resultado["artists"]["items"][0]
                artist_uri = artist["uri"]
                artist_name = artist["name"]
                
                try:
                    sp.start_playback(device_id=device_id, context_uri=artist_uri)
                except Exception:
                    subprocess.Popen(["cmd.exe", "/c", f"start {artist_uri}"], shell=True)

                return f"Tocando músicas de {artist_name} no Spotify."

            elif search_type == "playlist" and resultado.get("playlists", {}).get("items"):
                playlist = resultado["playlists"]["items"][0]
                playlist_uri = playlist["uri"]
                playlist_name = playlist["name"]
                
                try:
                    sp.start_playback(device_id=device_id, context_uri=playlist_uri)
                except Exception:
                    subprocess.Popen(["cmd.exe", "/c", f"start {playlist_uri}"], shell=True)

                return f"Tocando a playlist '{playlist_name}' no Spotify."

            elif search_type == "album" and resultado.get("albums", {}).get("items"):
                album = resultado["albums"]["items"][0]
                album_uri = album["uri"]
                album_name = album["name"]
                artist_name = album["artists"][0]["name"]
                
                try:
                    sp.start_playback(device_id=device_id, context_uri=album_uri)
                except Exception:
                    subprocess.Popen(["cmd.exe", "/c", f"start {album_uri}"], shell=True)

                return f"Tocando o álbum '{album_name}' de {artist_name} no Spotify."

            else:
                # Fallback: pesquisa genérica por faixa
                resultado_geral = sp.search(q=termo_busca, limit=1, type="track")
                if resultado_geral.get("tracks", {}).get("items"):
                    track = resultado_geral["tracks"]["items"][0]
                    track_uri = track["uri"]
                    try:
                        sp.start_playback(device_id=device_id, uris=[track_uri])
                    except Exception:
                        subprocess.Popen(["cmd.exe", "/c", f"start {track_uri}"], shell=True)
                    return f"Reproduzindo '{track['name']}' de {track['artists'][0]['name']} no Spotify."
                
                return f"Não encontrei nenhuma música ou artista para '{termo_busca}' no Spotify, senhor."

        except Exception as e:
            # Em caso de erro de dispositivo inativo, abre o aplicativo
            subprocess.Popen(["cmd.exe", "/c", f"start spotify:search:{termo_busca}"], shell=True)
            return f"Abrindo busca por '{termo_busca}' diretamente no Spotify do seu computador."

    def pausar(self) -> str:
        """Pausa a reprodução no Spotify."""
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado."
        try:
            sp.pause_playback()
            return "Música pausada no Spotify, senhor."
        except Exception as e:
            return f"Não foi possível pausar: {e}"

    def proxima_faixa(self) -> str:
        """Avança para a próxima faixa."""
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado."
        try:
            sp.next_track()
            return "Avançando para a próxima música no Spotify, senhor."
        except Exception as e:
            return f"Não foi possível passar a música: {e}"

    def faixa_anterior(self) -> str:
        """Volta para a música anterior."""
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado."
        try:
            sp.previous_track()
            return "Voltando para a música anterior no Spotify, senhor."
        except Exception as e:
            return f"Não foi possível voltar a música: {e}"

    def ajustar_volume(self, volume_porcentagem: int) -> str:
        """Ajusta o volume do Spotify (0 a 100)."""
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado."
        try:
            vol = max(0, min(100, int(volume_porcentagem)))
            sp.volume(vol)
            return f"Volume do Spotify ajustado para {vol}%, senhor."
        except Exception as e:
            return f"Não foi possível alterar o volume: {e}"

    def obter_musica_atual(self) -> str:
        """Retorna os detalhes da música que está tocando no momento."""
        sp = self._obter_cliente()
        if not sp:
            return "Spotify não configurado."
        try:
            current = sp.current_playback()
            if not current or not current.get("item"):
                return "Nenhuma música está sendo reproduzida no Spotify no momento, senhor."
            
            track = current["item"]
            nome = track.get("name")
            artistas = ", ".join([a["name"] for a in track.get("artists", [])])
            album = track.get("album", {}).get("name", "")
            tocando = "em reprodução" if current.get("is_playing") else "pausada"
            
            return f"No momento está {tocando}: '{nome}' de {artistas} (Álbum: {album})."
        except Exception as e:
            return f"Erro ao consultar música atual no Spotify: {e}"

spotify_service = SpotifyService()
