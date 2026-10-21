#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFmpeg Worker Module
Ejecución asíncrona de comandos FFmpeg con monitoreo de progreso en tiempo real y cancelación limpia.
"""

import os
import sys
import subprocess
import re
from typing import List, Optional
from PyQt5.QtCore import QThread, pyqtSignal


def parse_time_to_seconds(time_str: str) -> float:
    """Convierte cadenas HH:MM:SS.xx en segundos flotantes."""
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m = float(parts[0])
            s = float(parts[1])
            return m * 60 + s
        return float(parts[0])
    except Exception:
        return 0.0


class FFmpegWorker(QThread):
    """
    Hilo de trabajo para ejecutar FFmpeg sin congelar la interfaz gráfica.
    Emite señales de progreso, logs y finalización.
    """
    # Señales Qt
    progress_signal = pyqtSignal(float, str, str)  # (porcentaje 0-100, tiempo_actual, speed_fps_info)
    log_signal = pyqtSignal(str)                   # Líneas de salida para la consola de logs
    finished_signal = pyqtSignal(bool, str, str)   # (éxito, mensaje, ruta_salida)

    def __init__(
        self,
        command: List[str],
        total_duration: float = 0.0,
        output_path: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.command = command
        self.total_duration = total_duration
        self.output_path = output_path
        self._process: Optional[subprocess.Popen] = None
        self._is_cancelled = False
        self.collected_logs: List[str] = []

    def run(self):
        """Ejecuta el subproceso FFmpeg y lee la salida de stderr línea por línea."""
        self._is_cancelled = False
        self.collected_logs = []
        time_regex = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d+)")
        speed_regex = re.compile(r"speed=\s*([\d\.]+x)")
        fps_regex = re.compile(r"fps=\s*([\d\.]+)")
        frame_regex = re.compile(r"frame=\s*(\d+)")

        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # En Windows evita crear ventana de consola CMD
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

        import ffmpeg_core
        cmd_display = ffmpeg_core.format_command_for_display(self.command)
        self.log_signal.emit(f"==> Iniciando comando:\n$ {cmd_display}\n")

        try:
            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                creationflags=creationflags,
                bufsize=1
            )

            current_time_str = "00:00:00"
            speed_str = "1x"
            fps_str = "0"

            recent_error_lines = []
            # FFmpeg escribe su progreso y estadísticas en stderr
            for line in self._process.stderr:
                if self._is_cancelled:
                    break

                line_stripped = line.strip()
                if line_stripped:
                    self.collected_logs.append(line_stripped)
                    self.log_signal.emit(line_stripped)
                    # Guardar líneas informativas para diagnóstico en caso de error (excluir líneas periódicas de frame=)
                    if not line_stripped.startswith("frame=") and not line_stripped.startswith("size="):
                        recent_error_lines.append(line_stripped)
                        if len(recent_error_lines) > 20:
                            recent_error_lines.pop(0)

                # Buscar tiempo transcurrido
                m_time = time_regex.search(line)
                if m_time:
                    current_time_str = m_time.group(1)
                    curr_sec = parse_time_to_seconds(current_time_str)

                    m_speed = speed_regex.search(line)
                    if m_speed:
                        speed_str = m_speed.group(1)

                    m_fps = fps_regex.search(line)
                    if m_fps:
                        fps_str = m_fps.group(1)

                    percent = 0.0
                    if self.total_duration > 0:
                        percent = min(100.0, max(0.0, (curr_sec / self.total_duration) * 100.0))

                    info_status = f"Vel: {speed_str} | FPS: {fps_str}"
                    self.progress_signal.emit(percent, current_time_str, info_status)

            self._process.wait()
            ret_code = self._process.returncode

            if self._is_cancelled:
                self.log_signal.emit("\n[PROCESO CANCELADO POR EL USUARIO]")
                self.finished_signal.emit(False, "Operación cancelada por el usuario.", self.output_path)
            elif ret_code == 0:
                self.progress_signal.emit(100.0, "Completado", "100%")
                self.log_signal.emit("\n[PROCESO COMPLETADO EXITOSAMENTE]")
                self.finished_signal.emit(True, "¡Proceso finalizado con éxito!", self.output_path)
            else:
                self.log_signal.emit(f"\n[ERROR FFmpeg: Código de salida {ret_code}]")
                # Extraer detalle útil de las últimas líneas de error
                error_summary = ""
                key_errors = [
                    l for l in recent_error_lines
                    if any(k in l.lower() for k in ["error", "no such", "invalid", "cannot", "failed", "impossible", "denied"])
                ]
                if key_errors:
                    error_summary = "\n\n" + "\n".join(key_errors[-3:])
                elif recent_error_lines:
                    error_summary = "\n\n" + "\n".join(recent_error_lines[-2:])

                err_msg = f"FFmpeg finalizó con error (código {ret_code}).{error_summary}"
                self.finished_signal.emit(False, err_msg, self.output_path)

        except Exception as e:
            self.log_signal.emit(f"\n[EXCEPCIÓN]: {str(e)}")
            self.finished_signal.emit(False, f"Error durante la ejecución: {str(e)}", self.output_path)
        finally:
            self._process = None

    def cancel(self):
        """Cancela la ejecución de FFmpeg de forma segura y multiplataforma."""
        self._is_cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
