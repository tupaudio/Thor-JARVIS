"""
Gerenciador Central de Câmera e Arbitragem de Dispositivo para o J.A.R.V.I.S.
Evita contenção e conflito de acesso à webcam no Windows entre o Modo Sentinela
(vigilância contínua) e capturas manuais de fotos ou visão computacional.
"""

import os
import sys
import time
import threading

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

class CameraManager:
    """Controlador unificado de câmera frontal com thread-safety e multiplexação de fluxo."""
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._lock = threading.Lock()
        self._cap = None
        self._is_streaming = False
        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self.default_photo_path = os.path.join(self._base_dir, "webcam_view.jpg")

    def is_streaming(self) -> bool:
        """Indica se a câmera está atualmente sob captura contínua (ex: Modo Sentinela)."""
        return self._is_streaming

    def iniciar_stream(self) -> bool:
        """
        Abre o dispositivo de vídeo para captura contínua mantendo o handle aberto.
        Usado pelo Modo Sentinela.
        """
        import cv2
        with self._lock:
            if self._is_streaming and self._cap is not None and self._cap.isOpened():
                return True

            try:
                self._cap = cv2.VideoCapture(self.camera_index)
                if not self._cap.isOpened():
                    self._cap = None
                    self._is_streaming = False
                    return False

                # Minimiza buffer no Windows para frames sempre recentes
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Descarte inicial para calibração de luminosidade
                for _ in range(5):
                    self._cap.read()
                    time.sleep(0.05)

                self._is_streaming = True
                return True
            except Exception as e:
                print(f"⚠️ [CAMERA_MANAGER] Erro ao iniciar stream contínuo: {e}")
                if self._cap:
                    self._cap.release()
                    self._cap = None
                self._is_streaming = False
                return False

    def parar_stream(self):
        """Libera o hardware da câmera após o encerramento do monitoramento contínuo."""
        with self._lock:
            self._is_streaming = False
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def obter_frame(self):
        """
        Retorna uma tupla (sucesso: bool, frame: np.ndarray).
        Se estiver em streaming, lê do handle aberto.
        Se não estiver, abre temporariamente com calibração rápida e libera o hardware.
        """
        import cv2
        with self._lock:
            if self._is_streaming and self._cap is not None and self._cap.isOpened():
                ret, frame = self._cap.read()
                return ret, frame

            # Disparo avulso sob demanda
            try:
                cap = cv2.VideoCapture(self.camera_index)
                if not cap.isOpened():
                    return False, None

                for _ in range(5):
                    cap.read()

                ret, frame = cap.read()
                cap.release()
                return ret, frame
            except Exception as e:
                print(f"⚠️ [CAMERA_MANAGER] Erro ao obter frame avulso: {e}")
                return False, None

    def capturar_foto(self, caminho_saida: str = None) -> str:
        """
        Captura uma foto em alta definição e salva no disco.
        Retorna o caminho absoluto do arquivo ou string vazia em caso de falha.
        """
        import cv2
        destino = caminho_saida or self.default_photo_path
        ret, frame = self.obter_frame()
        if ret and frame is not None:
            try:
                cv2.imwrite(destino, frame)
                return destino
            except Exception as e:
                print(f"⚠️ [CAMERA_MANAGER] Erro ao salvar imagem em '{destino}': {e}")
                return ""
        return ""

camera_manager = CameraManager()
