"""
camera_manager.py — Arbitragem de câmera (iPhone no dock + webcam V4L2 opcional) para o J.A.R.V.I.S.

Melhorias (QW8 / F13):
  * Dois locks independentes: `_frame_lock` (Condition do buffer de frames na memória) e
    `_device_lock` (I/O de webcam física V4L2). Falhas/travamentos em /dev/video* não travam o stream do iPhone.
  * Relógio monotônico (`time.monotonic()`) para evitar derivas por ajustes de NTP/fuso horário.
  * Gravação atômica de foto (`capturar_foto`) via arquivo temporário + `os.replace` para evitar leitura de arquivo corrompido.
"""

import os
import time
import threading
import tempfile


class CameraManager:
    MAX_JPEG = 3 * 1024 * 1024

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._frame_lock = threading.Lock()
        self._novo_frame = threading.Condition(self._frame_lock)
        self._device_lock = threading.Lock()
        self._cap = None
        self._is_streaming = False
        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self.default_photo_path = os.path.join(self._base_dir, "webcam_view.jpg")
        self._remote_jpeg_bytes = None
        self._remote_frame_time = 0.0
        self._frame_seq = 0

    # ------------------------------------------------------------ iPhone remoto
    def atualizar_frame_remoto(self, jpeg_bytes: bytes) -> bool:
        """Guarda o JPEG mais recente (sem decodificar). Retorna False se não parecer um JPEG válido."""
        if not jpeg_bytes or len(jpeg_bytes) > self.MAX_JPEG or jpeg_bytes[:2] != b"\xff\xd8":
            return False
        with self._novo_frame:
            self._remote_jpeg_bytes = jpeg_bytes
            self._remote_frame_time = time.monotonic()
            self._frame_seq += 1
            self._novo_frame.notify_all()
        return True

    def tem_camera_iphone_ativa(self, max_age_sec: float = 10.0) -> bool:
        with self._frame_lock:
            return self._remote_jpeg_bytes is not None and (time.monotonic() - self._remote_frame_time) <= max_age_sec

    def obter_ultimo_jpeg_remoto(self, max_age_sec: float = 30.0):
        with self._frame_lock:
            if self._remote_jpeg_bytes and (time.monotonic() - self._remote_frame_time) <= max_age_sec:
                return self._remote_jpeg_bytes
        return None

    def aguardar_frame_novo(self, ultimo_seq: int, timeout: float = 5.0):
        """Bloqueia até existir um frame mais novo que ultimo_seq. Retorna (seq, jpeg) ou (ultimo_seq, None)."""
        with self._novo_frame:
            self._novo_frame.wait_for(lambda: self._frame_seq != ultimo_seq, timeout=timeout)
            if self._frame_seq != ultimo_seq:
                return self._frame_seq, self._remote_jpeg_bytes
        return ultimo_seq, None

    def _decodificar_remoto(self):
        import cv2
        import numpy as np
        jpeg = self.obter_ultimo_jpeg_remoto(max_age_sec=10.0)
        if not jpeg:
            return None
        return cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)

    # ------------------------------------------------------------- webcam local
    def is_streaming(self) -> bool:
        with self._device_lock:
            return self._is_streaming

    def iniciar_stream(self) -> bool:
        """Prepara a captura contínua (iPhone se estiver enviando; senão webcam V4L2 local)."""
        if self.tem_camera_iphone_ativa():
            with self._device_lock:
                self._is_streaming = True
            return True
        import cv2
        with self._device_lock:
            if self._is_streaming and self._cap is not None and self._cap.isOpened():
                return True
            try:
                self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
                if not self._cap.isOpened():
                    self._cap.release()
                    self._cap = None
                    self._is_streaming = False
                    return False
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                for _ in range(5):
                    self._cap.read()
                    time.sleep(0.05)
                self._is_streaming = True
                return True
            except Exception as e:
                print(f"⚠️ [CAMERA_MANAGER] Erro ao iniciar stream local: {e}")
                if self._cap:
                    self._cap.release()
                    self._cap = None
                self._is_streaming = False
                return False

    def parar_stream(self):
        with self._device_lock:
            self._is_streaming = False
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def obter_frame(self):
        """(sucesso, frame BGR). Prioriza o iPhone; senão webcam V4L2 local (se houver)."""
        frame = self._decodificar_remoto()
        if frame is not None:
            return True, frame
        import cv2
        with self._device_lock:
            if self._is_streaming and self._cap is not None and self._cap.isOpened():
                return self._cap.read()
            if not os.path.exists(f"/dev/video{self.camera_index}"):
                return False, None  # servidor headless sem webcam: falha imediata, sem esperar o OpenCV
            try:
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
                if not cap.isOpened():
                    return False, None
                for _ in range(2):
                    cap.read()
                ret, frame = cap.read()
                cap.release()
                return ret, frame
            except Exception as e:
                print(f"⚠️ [CAMERA_MANAGER] Erro ao capturar frame avulso local: {e}")
                return False, None

    def capturar_foto(self, caminho_saida: str = None) -> str:
        """Salva uma foto de forma atômica (grava em temp e move). Retorna o caminho ou ''."""
        destino = caminho_saida or self.default_photo_path
        pasta_destino = os.path.dirname(os.path.abspath(destino))
        jpeg = self.obter_ultimo_jpeg_remoto(max_age_sec=10.0)
        try:
            if jpeg:
                fd, tmp_path = tempfile.mkstemp(dir=pasta_destino, prefix="tmp_photo_", suffix=".jpg")
                with os.fdopen(fd, "wb") as f:
                    f.write(jpeg)
                os.replace(tmp_path, destino)
                return destino
            import cv2
            ok, frame = self.obter_frame()
            if ok and frame is not None:
                fd, tmp_path = tempfile.mkstemp(dir=pasta_destino, prefix="tmp_photo_", suffix=".jpg")
                os.close(fd)
                cv2.imwrite(tmp_path, frame)
                os.replace(tmp_path, destino)
                return destino
        except Exception as e:
            print(f"⚠️ [CAMERA_MANAGER] Erro ao salvar imagem atômica: {e}")
        return ""


camera_manager = CameraManager()
