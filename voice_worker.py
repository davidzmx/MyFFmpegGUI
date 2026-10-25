#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice Worker Module
Hilo de trabajo asíncrono en segundo plano para detección de voz, diarización de hablantes y extracción de muestras.
"""

import os
import sys
import tempfile
import subprocess
from typing import Optional, List, Dict, Any, Tuple
from PyQt5.QtCore import QThread, pyqtSignal

import ffmpeg_core
import diarization_core


class DiarizationWorker(QThread):
    """
    Hilo de trabajo para ejecutar el flujo completo de diarización sin bloquear la interfaz:
    1. Extracción rápida de audio de referencia (16 kHz mono).
    2. Detección de silencios y tramos de voz (VAD con FFmpeg).
    3. Análisis acústico y clustering por timbre vocal.
    4. Generación de estadísticas y selección de muestras óptimas.
    """
    progress_signal = pyqtSignal(float, str, str)  # (porcentaje 0-100, mensaje_estado, detalle)
    log_signal = pyqtSignal(str)                   # Líneas de registro para la consola
    finished_signal = pyqtSignal(bool, str, dict)  # (éxito, mensaje, resultados)

    def __init__(
        self,
        ffmpeg_path: str,
        ffprobe_path: Optional[str],
        input_file: str,
        num_speakers: Optional[int] = None,
        noise_threshold_db: float = -28.0,
        min_silence_duration: float = 0.35,
        parent=None
    ):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.input_file = input_file
        self.num_speakers = num_speakers
        self.noise_threshold_db = noise_threshold_db
        self.min_silence_duration = min_silence_duration
        self._is_cancelled = False
        self._process: Optional[subprocess.Popen] = None
        self.temp_analysis_wav = ""

    def cancel(self):
        """Cancela la ejecución de forma limpia."""
        self._is_cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def run(self):
        self._is_cancelled = False
        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

        try:
            # Paso 0: Obtener duración total del archivo
            self.log_signal.emit("[1/4] Analizando metadatos del archivo de entrada...\n")
            info = ffmpeg_core.get_media_info(self.input_file, self.ffprobe_path)
            total_duration = info.get("duration", 0.0)

            if self._is_cancelled:
                self.finished_signal.emit(False, "Proceso cancelado por el usuario.", {})
                return

            # Paso 1: Extraer pista mono temporal de 16kHz para análisis acústico
            self.progress_signal.emit(10.0, "Extrayendo audio para análisis acústico...", "FFmpeg 16kHz PCM")
            tmp_dir = tempfile.gettempdir()
            self.temp_analysis_wav = os.path.join(tmp_dir, f"myffmpeg_diar_{os.getpid()}_{id(self)}.wav")

            cmd_extract = ffmpeg_core.build_extract_mono_wav_command(
                self.ffmpeg_path,
                self.input_file,
                self.temp_analysis_wav,
                sample_rate=16000
            )
            self.log_signal.emit(f"[2/4] Extrayendo audio base a 16 kHz:\n$ {' '.join(cmd_extract)}\n")

            self._process = subprocess.Popen(
                cmd_extract,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            _, err_extract = self._process.communicate()

            if self._is_cancelled:
                self._cleanup_temp()
                self.finished_signal.emit(False, "Proceso cancelado por el usuario.", {})
                return

            if not os.path.isfile(self.temp_analysis_wav) or os.path.getsize(self.temp_analysis_wav) == 0:
                self.finished_signal.emit(False, f"Error extrayendo audio de análisis: {err_extract.decode('utf-8', errors='ignore')}", {})
                return

            # Paso 2: Detectar actividad de voz y silencios con FFmpeg silencedetect
            self.progress_signal.emit(35.0, "Detectando turnos de habla y silencios (VAD)...", "Filtro silencedetect")
            cmd_silence = ffmpeg_core.build_silence_detect_command(
                self.ffmpeg_path,
                self.temp_analysis_wav,
                noise_db=self.noise_threshold_db,
                min_duration=self.min_silence_duration
            )
            self.log_signal.emit(f"[3/4] Detectando actividad de voz:\n$ {' '.join(cmd_silence)}\n")

            self._process = subprocess.Popen(
                cmd_silence,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            _, err_silence = self._process.communicate()

            if self._is_cancelled:
                self._cleanup_temp()
                self.finished_signal.emit(False, "Proceso cancelado por el usuario.", {})
                return

            stderr_silence_str = err_silence.decode("utf-8", errors="replace")
            speech_segments = ffmpeg_core.parse_silence_detect_output(stderr_silence_str, total_duration)

            if not speech_segments and total_duration > 0:
                speech_segments = [(0.0, round(total_duration, 3))]

            self.log_signal.emit(f"• Tramos de habla identificados por VAD: {len(speech_segments)}\n")

            if not speech_segments:
                self._cleanup_temp()
                self.finished_signal.emit(False, "No se detectó actividad de habla en el archivo proporcionado.", {})
                return

            # Paso 3: Análisis de timbre vocal (MFCC + Pitch + Centroide) y clustering jerárquico
            self.progress_signal.emit(70.0, "Analizando timbres vocales y agrupando interlocutores...", "Ventanas acústicas de 1.5s")
            self.log_signal.emit("[4/4] Extrayendo huellas acústicas (MFCC + Pitch F0) y agrupando interlocutores...\n")

            diar_result = diarization_core.perform_speaker_diarization(
                self.temp_analysis_wav,
                speech_segments,
                num_speakers=self.num_speakers,
                max_speakers=5
            )

            diar_result["total_file_duration"] = total_duration
            diar_result["analysis_wav_path"] = self.temp_analysis_wav  # Conservar para vistas previas si se necesita

            num_found = diar_result.get("num_speakers", 0)
            self.log_signal.emit(f"==> Diarización finalizada con éxito. Interlocutores detectados: {num_found}\n")

            self.progress_signal.emit(100.0, "Diarización completada con éxito.", f"{num_found} personas detectadas")
            self.finished_signal.emit(True, f"Detección completada: {num_found} interlocutor(es) identificado(s).", diar_result)

        except Exception as e:
            self._cleanup_temp()
            self.finished_signal.emit(False, f"Error durante la diarización: {str(e)}", {})

    def _cleanup_temp(self):
        if self.temp_analysis_wav and os.path.isfile(self.temp_analysis_wav):
            try:
                os.remove(self.temp_analysis_wav)
            except Exception:
                pass
