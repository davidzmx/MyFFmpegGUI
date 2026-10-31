#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Timeline Waveform Selector Widget
Componente gráfico interactivo para visualización de forma de onda y selección manual/ajuste
de segmentos de voz mediante arrastre con el ratón, zoom de onda, desplazamiento y marcador de reproducción arrastrable.
"""

import os
import sys
import math
import subprocess
from typing import List, Tuple, Optional
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QStyle, QSizePolicy, QToolTip, QShortcut, QScrollBar
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QCursor,
    QPainterPath, QPolygonF, QKeySequence
)
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, pyqtSignal, QTimer, QPoint
)


def format_seconds_exact(sec: float) -> str:
    """Convierte segundos a formato MM:SS.cc (centésimas de segundo)."""
    if sec < 0:
        sec = 0.0
    m, s = divmod(sec, 60.0)
    h, m = divmod(int(m), 60)
    int_s = int(s)
    cents = int(round((s - int_s) * 100))
    if cents >= 100:
        int_s += 1
        cents = 0
    if h > 0:
        return f"{h:02d}:{m:02d}:{int_s:02d}.{cents:02d}"
    return f"{m:02d}:{int_s:02d}.{cents:02d}"


def extract_waveform_peaks(ffmpeg_path: str, input_file: str, num_peaks: int = 2400) -> np.ndarray:
    """
    Extrae la envolvente de picos de amplitud (waveform) de forma ultra rápida
    mediante una tubería (pipe) directa de FFmpeg sin crear archivos temporales en disco.
    """
    if not os.path.isfile(input_file) or not ffmpeg_path:
        return np.zeros(num_peaks, dtype=np.float32)

    cmd = [
        ffmpeg_path, "-y",
        "-i", input_file,
        "-vn",
        "-ac", "1",
        "-ar", "8000",
        "-f", "s16le", "-"
    ]
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        raw_bytes, _ = proc.communicate(timeout=15.0)
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) == 0:
            return np.zeros(num_peaks, dtype=np.float32)

        chunk_size = max(1, len(samples) // num_peaks)
        usable_len = (len(samples) // chunk_size) * chunk_size
        reshaped = samples[:usable_len].reshape(-1, chunk_size)
        peaks = np.max(np.abs(reshaped), axis=1)
        max_p = float(np.max(peaks)) if len(peaks) > 0 else 1.0
        norm_peaks = (peaks / max(1.0, max_p)).astype(np.float32)
        if len(norm_peaks) < num_peaks:
            norm_peaks = np.pad(norm_peaks, (0, num_peaks - len(norm_peaks)))
        elif len(norm_peaks) > num_peaks:
            norm_peaks = norm_peaks[:num_peaks]
        return norm_peaks
    except Exception:
        return np.zeros(num_peaks, dtype=np.float32)


class AudioTimelineCanvas(QWidget):
    """
    Lienzo interactivo que dibuja la onda de audio real y permite crear, seleccionar,
    mover y redimensionar segmentos de tiempo, hacer zoom temporal y arrastrar el marcador playhead.
    """
    segment_selected = pyqtSignal(int, float, float) # (index, start_sec, end_sec)
    segments_changed = pyqtSignal(list)              # [(st, en), ...]
    seek_requested = pyqtSignal(float)               # time in seconds
    view_changed = pyqtSignal(float, float)          # (view_start, zoom_level)

    HANDLE_WIDTH = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.total_duration: float = 0.0
        self.waveform_peaks: Optional[np.ndarray] = None
        self.segments: List[Tuple[float, float]] = []
        self.selected_idx: int = -1
        self.playhead_pos: float = 0.0

        # Zoom y ventana visible
        self.zoom_level: float = 1.0
        self.view_start: float = 0.0

        # Estados de interacción con el ratón
        self._drag_mode: Optional[str] = None  # 'create', 'resize_left', 'resize_right', 'move', 'playhead'
        self._drag_start_x: float = 0.0
        self._drag_start_time: float = 0.0
        self._orig_seg: Optional[Tuple[float, float]] = None
        self._hover_mode: Optional[str] = None
        self._hover_idx: int = -1

    def set_media(self, duration: float, waveform_peaks: Optional[np.ndarray] = None):
        """Carga la duración y los picos de forma de onda."""
        self.total_duration = max(0.1, duration)
        self.waveform_peaks = waveform_peaks
        self.playhead_pos = 0.0
        self.zoom_level = 1.0
        self.view_start = 0.0
        self.update()
        self.view_changed.emit(self.view_start, self.zoom_level)

    def set_segments(self, segments: List[Tuple[float, float]]):
        """Asigna la lista de segmentos activos [(inicio, fin), ...]."""
        max_en = max([float(en) for _, en in segments], default=0.0)
        if self.total_duration <= 0.0:
            self.total_duration = max(0.1, max_en)
        else:
            self.total_duration = max(self.total_duration, max_en)

        parsed = []
        for st, en in segments:
            st_f = max(0.0, float(st))
            en_f = min(self.total_duration, float(en))
            if en_f > st_f:
                parsed.append((st_f, en_f))
        parsed.sort(key=lambda s: s[0])
        self.segments = parsed
        self.selected_idx = 0 if self.segments else -1
        self.update()
        self.segments_changed.emit(self.segments)
        if self.selected_idx >= 0 and self.selected_idx < len(self.segments):
            st, en = self.segments[self.selected_idx]
            self.segment_selected.emit(self.selected_idx, st, en)

    def set_playhead(self, seconds: float):
        """Actualiza la aguja de reproducción visual."""
        self.playhead_pos = max(0.0, min(self.total_duration, seconds))
        # Si se reproduce con zoom activo y el playhead avanza más allá del borde derecho visible
        if self.zoom_level > 1.0:
            vis_dur = max(0.001, self.total_duration / self.zoom_level)
            if self.playhead_pos > self.view_start + vis_dur:
                self.set_view_start(self.playhead_pos - (vis_dur * 0.15))
            elif self.playhead_pos < self.view_start:
                self.set_view_start(self.playhead_pos)
        self.update()

    def set_zoom(self, zoom: float, center_time: Optional[float] = None):
        """Ajusta el nivel de zoom (1.0x a 20.0x) manteniendo el punto de enfoque temporal."""
        old_zoom = self.zoom_level
        new_zoom = max(1.0, min(20.0, float(zoom)))
        if self.total_duration <= 0:
            self.zoom_level = new_zoom
            self.view_start = 0.0
            self.update()
            self.view_changed.emit(self.view_start, self.zoom_level)
            return

        old_vis_dur = max(0.001, self.total_duration / old_zoom)
        new_vis_dur = max(0.001, self.total_duration / new_zoom)

        if center_time is None:
            center_time = self.view_start + (old_vis_dur / 2.0)

        center_time = max(0.0, min(self.total_duration, center_time))
        rel_pos = (center_time - self.view_start) / old_vis_dur if old_vis_dur > 0 else 0.5
        rel_pos = max(0.0, min(1.0, rel_pos))
        new_start = center_time - (rel_pos * new_vis_dur)

        self.zoom_level = new_zoom
        self.set_view_start(new_start)

    def set_view_start(self, start_sec: float):
        """Desplaza horizontalmente la ventana de tiempo visible."""
        vis_dur = max(0.001, self.total_duration / self.zoom_level)
        max_start = max(0.0, self.total_duration - vis_dur)
        self.view_start = max(0.0, min(max_start, float(start_sec)))
        self.update()
        self.view_changed.emit(self.view_start, self.zoom_level)

    def zoom_in(self):
        self.set_zoom(self.zoom_level * 1.35)

    def zoom_out(self):
        self.set_zoom(self.zoom_level / 1.35)

    def reset_zoom(self):
        self.set_zoom(1.0, center_time=0.0)

    def get_selected_segment(self) -> Optional[Tuple[float, float]]:
        if 0 <= self.selected_idx < len(self.segments):
            return self.segments[self.selected_idx]
        return None

    def add_segment(self, start_sec: float, end_sec: float):
        st = max(0.0, min(self.total_duration, start_sec))
        en = max(0.0, min(self.total_duration, end_sec))
        if en > st + 0.2:
            self.segments.append((round(st, 2), round(en, 2)))
            self.segments.sort(key=lambda s: s[0])
            self.selected_idx = self.segments.index((round(st, 2), round(en, 2)))
            self.update()
            self.segments_changed.emit(self.segments)
            self.segment_selected.emit(self.selected_idx, st, en)

    def delete_selected_segment(self):
        if 0 <= self.selected_idx < len(self.segments):
            del self.segments[self.selected_idx]
            self.selected_idx = min(self.selected_idx, len(self.segments) - 1)
            self.update()
            self.segments_changed.emit(self.segments)
            if 0 <= self.selected_idx < len(self.segments):
                st, en = self.segments[self.selected_idx]
                self.segment_selected.emit(self.selected_idx, st, en)
            else:
                self.segment_selected.emit(-1, 0.0, 0.0)

    def clear_all_segments(self):
        self.segments.clear()
        self.selected_idx = -1
        self.update()
        self.segments_changed.emit([])
        self.segment_selected.emit(-1, 0.0, 0.0)

    # Coordenadas X <-> Segundos con soporte de Zoom
    def _time_to_x(self, t: float) -> float:
        if self.total_duration <= 0 or self.width() <= 0:
            return 0.0
        vis_dur = max(0.001, self.total_duration / self.zoom_level)
        return ((t - self.view_start) / vis_dur) * float(self.width())

    def _x_to_time(self, x: float) -> float:
        if self.total_duration <= 0 or self.width() <= 0:
            return 0.0
        vis_dur = max(0.001, self.total_duration / self.zoom_level)
        ratio = x / float(self.width())
        t = self.view_start + (ratio * vis_dur)
        return max(0.0, min(self.total_duration, t))

    # Eventos de Rueda de Ratón (Zoom con Ctrl, Pan horizontal sin Ctrl)
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            # Zoom enfocado en la posición actual del cursor
            mouse_x = event.pos().x()
            mouse_t = self._x_to_time(mouse_x)
            factor = 1.25 if delta > 0 else 0.8
            self.set_zoom(self.zoom_level * factor, center_time=mouse_t)
            event.accept()
        else:
            # Desplazamiento horizontal (pan) cuando hay zoom activo
            if self.zoom_level > 1.0:
                vis_dur = max(0.001, self.total_duration / self.zoom_level)
                pan_step = vis_dur * 0.12 * (-1 if delta > 0 else 1)
                self.set_view_start(self.view_start + pan_step)
                event.accept()
            else:
                super().wheelEvent(event)

    # Eventos de Ratón
    def mousePressEvent(self, event):
        if self.total_duration <= 0 or event.button() != Qt.LeftButton:
            return

        x = event.pos().x()
        y = event.pos().y()
        t = self._x_to_time(x)
        px = self._time_to_x(self.playhead_pos)

        self._drag_start_x = x
        self._drag_start_time = t

        # 1. Clic en la regla superior (donde está el triángulo rojo del marcador)
        if y <= 24:
            if abs(x - px) <= 12:
                # Agarre directo sobre el triángulo rojo
                self._drag_mode = 'playhead'
                self.setCursor(Qt.SizeHorCursor)
            else:
                # Clic en cualquier otro punto de la regla: mueve la posición y permite arrastrarlo
                self.set_playhead(t)
                self.seek_requested.emit(t)
                self._drag_mode = 'playhead'
                self.setCursor(Qt.SizeHorCursor)
            self.update()
            return

        # 2. Comprobar si se hace clic sobre un asa o segmento existente
        clicked_mode = None
        clicked_idx = -1

        for idx, (st, en) in enumerate(self.segments):
            x_st = self._time_to_x(st)
            x_en = self._time_to_x(en)

            if abs(x - x_st) <= self.HANDLE_WIDTH:
                clicked_mode = 'resize_left'
                clicked_idx = idx
                break
            elif abs(x - x_en) <= self.HANDLE_WIDTH:
                clicked_mode = 'resize_right'
                clicked_idx = idx
                break
            elif x_st < x < x_en:
                clicked_mode = 'move'
                clicked_idx = idx
                break

        if clicked_mode is not None:
            self._drag_mode = clicked_mode
            self.selected_idx = clicked_idx
            self._orig_seg = self.segments[clicked_idx]
            st, en = self.segments[clicked_idx]
            self.segment_selected.emit(clicked_idx, st, en)
            self.update()
        else:
            # Clic en zona vacía: iniciar creación de nuevo segmento arrastrando
            self._drag_mode = 'create'
            self.selected_idx = -1
            self._orig_seg = (t, t)
            self.update()

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        t = self._x_to_time(x)
        px = self._time_to_x(self.playhead_pos)

        if not self._drag_mode:
            # Comprobar si el ratón está sobre el triángulo rojo del marcador
            if y <= 24 and abs(x - px) <= 12:
                self.setCursor(Qt.SizeHorCursor)
                if self._hover_mode != 'playhead':
                    self._hover_mode = 'playhead'
                    self.update()
                return
            elif self._hover_mode == 'playhead':
                self._hover_mode = None
                self.update()

            if y <= 24:
                self.setCursor(Qt.PointingHandCursor)
                return

            hover_mode = None
            hover_idx = -1
            for idx, (st, en) in enumerate(self.segments):
                x_st = self._time_to_x(st)
                x_en = self._time_to_x(en)
                if abs(x - x_st) <= self.HANDLE_WIDTH:
                    hover_mode = 'resize_left'
                    hover_idx = idx
                    break
                elif abs(x - x_en) <= self.HANDLE_WIDTH:
                    hover_mode = 'resize_right'
                    hover_idx = idx
                    break
                elif x_st < x < x_en:
                    hover_mode = 'move'
                    hover_idx = idx
                    break

            if hover_mode in ('resize_left', 'resize_right'):
                self.setCursor(Qt.SizeHorCursor)
            elif hover_mode == 'move':
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return

        # Arrastre activo
        if self._drag_mode == 'playhead':
            new_t = max(0.0, min(self.total_duration, t))
            self.playhead_pos = new_t
            self.seek_requested.emit(new_t)
            # Si el arrastre se aproxima a los bordes con zoom activo, hacer auto-pan suave
            if self.zoom_level > 1.0:
                vis_dur = max(0.001, self.total_duration / self.zoom_level)
                if x >= self.width() - 5:
                    self.set_view_start(self.view_start + (vis_dur * 0.05))
                elif x <= 5:
                    self.set_view_start(self.view_start - (vis_dur * 0.05))
            self.setCursor(Qt.SizeHorCursor)
            self.update()
            return

        elif self._drag_mode == 'create':
            st = min(self._drag_start_time, t)
            en = max(self._drag_start_time, t)
            self._orig_seg = (st, en)
            self.update()

        elif self._drag_mode == 'resize_left' and self.selected_idx >= 0:
            _, en = self.segments[self.selected_idx]
            new_st = max(0.0, min(en - 0.2, t))
            self.segments[self.selected_idx] = (round(new_st, 2), en)
            self.update()
            self.segment_selected.emit(self.selected_idx, new_st, en)

        elif self._drag_mode == 'resize_right' and self.selected_idx >= 0:
            st, _ = self.segments[self.selected_idx]
            new_en = min(self.total_duration, max(st + 0.2, t))
            self.segments[self.selected_idx] = (st, round(new_en, 2))
            self.update()
            self.segment_selected.emit(self.selected_idx, st, new_en)

        elif self._drag_mode == 'move' and self.selected_idx >= 0 and self._orig_seg:
            orig_st, orig_en = self._orig_seg
            dur = orig_en - orig_st
            delta_t = t - self._drag_start_time
            new_st = max(0.0, min(self.total_duration - dur, orig_st + delta_t))
            new_en = new_st + dur
            self.segments[self.selected_idx] = (round(new_st, 2), round(new_en, 2))
            self.update()
            self.segment_selected.emit(self.selected_idx, new_st, new_en)

    def mouseReleaseEvent(self, event):
        x = event.pos().x()
        t = self._x_to_time(x)

        if self._drag_mode == 'playhead':
            self.seek_requested.emit(self.playhead_pos)
            self._drag_mode = None
            self.update()
            return

        elif self._drag_mode == 'create' and self._orig_seg:
            st, en = self._orig_seg
            if en - st >= 0.35:
                self.segments.append((round(st, 2), round(en, 2)))
                self.segments.sort(key=lambda s: s[0])
                self.selected_idx = self.segments.index((round(st, 2), round(en, 2)))
                self.segments_changed.emit(self.segments)
                self.segment_selected.emit(self.selected_idx, st, en)
            else:
                # Clic simple sin arrastre sobre la onda: mover la aguja roja a este punto
                self.seek_requested.emit(t)
                self.set_playhead(t)
            self._orig_seg = None

        elif self._drag_mode == 'move':
            if abs(x - self._drag_start_x) < 4:
                self.seek_requested.emit(t)
                self.set_playhead(t)
            self.segments.sort(key=lambda s: s[0])
            self.segments_changed.emit(self.segments)

        elif self._drag_mode in ('resize_left', 'resize_right'):
            self.segments.sort(key=lambda s: s[0])
            self.segments_changed.emit(self.segments)

        self._drag_mode = None
        self._orig_seg = None
        self.update()

    def leaveEvent(self, event):
        if self._hover_mode:
            self._hover_mode = None
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_segment()
            event.accept()
        else:
            super().keyPressEvent(event)

    # Dibujado con QPainter
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return

        ruler_h = 24.0
        wave_h = h - ruler_h
        center_y = ruler_h + (wave_h / 2.0)

        # 1. Fondo de la línea de tiempo (Dark Slate)
        painter.fillRect(0, 0, int(w), int(h), QColor("#0b1329"))
        painter.fillRect(0, 0, int(w), int(ruler_h), QColor("#111c38"))

        # Borde divisor de regla
        painter.setPen(QPen(QColor("#1e293b"), 1))
        painter.drawLine(0, int(ruler_h), int(w), int(ruler_h))

        # 2. Regla superior de marcas de tiempo adaptativa al zoom
        painter.setFont(QFont("Consolas", 8))
        vis_dur = max(0.001, self.total_duration / self.zoom_level)

        if vis_dur <= 1.0:
            step_sec = 0.1
        elif vis_dur <= 2.5:
            step_sec = 0.25
        elif vis_dur <= 5.0:
            step_sec = 0.5
        elif vis_dur <= 12.0:
            step_sec = 1.0
        elif vis_dur <= 25.0:
            step_sec = 2.0
        elif vis_dur <= 60.0:
            step_sec = 5.0
        elif vis_dur <= 150.0:
            step_sec = 10.0
        elif vis_dur <= 300.0:
            step_sec = 20.0
        elif vis_dur <= 600.0:
            step_sec = 30.0
        else:
            step_sec = 60.0

        first_mark = math.floor(self.view_start / step_sec) * step_sec
        t_mark = max(0.0, first_mark)
        max_mark = min(self.total_duration, self.view_start + vis_dur + step_sec)

        while t_mark <= max_mark:
            x_m = self._time_to_x(t_mark)
            if -20 <= x_m <= w + 20:
                painter.setPen(QPen(QColor("#475569"), 1))
                painter.drawLine(int(x_m), int(ruler_h - 7), int(x_m), int(ruler_h))

                # Texto de tiempo
                if step_sec < 1.0:
                    lbl = format_seconds_exact(t_mark)
                else:
                    lbl = format_seconds_exact(t_mark).split(".")[0]
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(int(x_m) + 3, int(ruler_h - 6), lbl)

            t_mark += step_sec

        # Línea central sutil de la forma de onda
        painter.setPen(QPen(QColor("#1e293b"), 1, Qt.DashLine))
        painter.drawLine(0, int(center_y), int(w), int(center_y))

        # 3. Dibujar Forma de Onda (Waveform) adaptativa con resolución continua
        if self.waveform_peaks is not None and len(self.waveform_peaks) > 0 and self.total_duration > 0:
            total_p = len(self.waveform_peaks)
            max_amp = (wave_h / 2.0) - 4.0

            col_step = 2.0
            num_cols = int(w / col_step) + 1
            painter.setPen(Qt.NoPen)

            for i in range(num_cols):
                col_x = i * col_step
                t1 = self._x_to_time(col_x)
                t2 = self._x_to_time(col_x + col_step)

                idx1 = int((t1 / self.total_duration) * total_p)
                idx2 = int((t2 / self.total_duration) * total_p) + 1
                idx1 = max(0, min(total_p - 1, idx1))
                idx2 = max(idx1 + 1, min(total_p, idx2))

                peak = float(np.max(self.waveform_peaks[idx1:idx2]))
                bh = max(2.0, peak * max_amp)

                painter.fillRect(
                    QRectF(col_x, center_y - bh, max(1.0, col_step - 0.5), bh * 2.0),
                    QColor("#1e3a8a")
                )

        # 4. Dibujar Segmentos Seleccionados (Siempre translúcidos sobre la onda)
        for idx, (st, en) in enumerate(self.segments):
            x1 = self._time_to_x(st)
            x2 = self._time_to_x(en)

            # Omitir si queda completamente fuera de pantalla
            if x2 < -10 or x1 > w + 10:
                continue

            seg_w = max(4.0, x2 - x1)
            is_active = (idx == self.selected_idx)

            # Fondo del bloque de voz (Translúcido para que la onda sea siempre visible)
            rect = QRectF(x1, ruler_h + 2.0, seg_w, wave_h - 4.0)
            fill_color = QColor(14, 165, 233, 75) if is_active else QColor(56, 189, 248, 38)
            painter.fillRect(rect, fill_color)

            # Borde exterior (Asegurar NoBrush para que drawRoundedRect NO rellene)
            border_pen = QPen(
                QColor("#38bdf8") if is_active else QColor("#0284c7"),
                2.0 if is_active else 1.2
            )
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 4.0, 4.0)

            # Manijas laterales de redimensionamiento (Grip Handles)
            h_color = QColor("#ffffff") if is_active else QColor("#94a3b8")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(h_color))

            # Asa izquierda
            if -10 <= x1 <= w + 10:
                painter.drawRoundedRect(QRectF(x1, center_y - 12, 4.0, 24.0), 2.0, 2.0)
            # Asa derecha
            if -10 <= x2 <= w + 10:
                painter.drawRoundedRect(QRectF(x2 - 4.0, center_y - 12, 4.0, 24.0), 2.0, 2.0)

            painter.setBrush(Qt.NoBrush)

            # Etiqueta de tiempo del segmento
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold if is_active else QFont.Normal))
            painter.setPen(QColor("#f8fafc") if is_active else QColor("#cbd5e1"))
            dur_str = f"{en - st:.2f}s"
            lbl_x = max(x1 + 6, 6.0)
            painter.drawText(QRectF(lbl_x, ruler_h + 6, min(seg_w - 12, w - lbl_x), 16), Qt.AlignLeft, f"#{idx+1} ({dur_str})")

        # Dibujar tramo en creación activa
        if self._drag_mode == 'create' and self._orig_seg:
            c_st, c_en = self._orig_seg
            cx1 = self._time_to_x(c_st)
            cx2 = self._time_to_x(c_en)
            c_rect = QRectF(cx1, ruler_h + 2.0, max(2.0, cx2 - cx1), wave_h - 4.0)
            painter.fillRect(c_rect, QColor(245, 158, 11, 70))
            painter.setPen(QPen(QColor("#f59e0b"), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(c_rect)

        # 5. Aguja de Reproducción (Playhead con marcador triangular arrastrable)
        px = self._time_to_x(self.playhead_pos)
        if -20 <= px <= w + 20:
            # Línea vertical del marcador
            painter.setPen(QPen(QColor("#ef4444"), 2.0))
            painter.drawLine(int(px), int(ruler_h), int(px), int(h))

            # Marcador triangular en la regla superior
            is_grab = (self._hover_mode == 'playhead' or self._drag_mode == 'playhead')
            m_color = QColor("#ff4d4d") if is_grab else QColor("#ef4444")
            b_color = QColor("#ffffff") if is_grab else QColor("#b91c1c")

            # Triángulo invertido ergonómico con punta en y=15
            head = QPolygonF([
                QPointF(px - 7, 0),
                QPointF(px + 7, 0),
                QPointF(px + 7, 5),
                QPointF(px, 15),
                QPointF(px - 7, 5)
            ])
            painter.setPen(QPen(b_color, 1.2))
            painter.setBrush(QBrush(m_color))
            painter.drawPolygon(head)

            # Grips visuales horizontales si está en foco o arrastre
            if is_grab:
                painter.setPen(QPen(QColor("#ffffff"), 1.2))
                painter.drawLine(int(px - 3), 3, int(px + 3), 3)
                painter.drawLine(int(px - 2), 6, int(px + 2), 6)


class AudioSegmentSelectorWidget(QWidget):
    """
    Contenedor completo que incluye el lienzo interactivo de la forma de onda,
    barra de transporte, controles de reproducción normal y por tramo, zoom y desplazamiento.
    """
    segments_updated = pyqtSignal(list)
    play_normal_requested = pyqtSignal(float)           # start_sec (hasta el final del archivo)
    play_selection_requested = pyqtSignal(float, float) # (start_sec, end_sec)
    play_requested = pyqtSignal(float, float)           # compatibilidad hacia atrás
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(float)                  # time in seconds

    def __init__(self, guide_text: Optional[str] = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Cabecera explicativa
        default_guide = (
            "✂️ <b>Selector Gráfico de Voz:</b> Arrastra el marcador rojo (triángulo superior) o haz clic en la regla para ubicar la reproducción. "
            "Arrastra con el ratón sobre la onda para marcar tramos de habla y ajusta los bordes. "
            "Usa los botones de Zoom o <b>Ctrl + Rueda</b> para ver la onda con máxima precisión."
        )
        self.lbl_guide = QLabel(guide_text if guide_text is not None else default_guide)
        self.lbl_guide.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_guide)

        # 2. Lienzo de Forma de Onda y Línea de Tiempo
        self.canvas = AudioTimelineCanvas(self)
        self.canvas.segment_selected.connect(self._on_segment_selected)
        self.canvas.segments_changed.connect(self._on_segments_changed)
        self.canvas.seek_requested.connect(self.seek_requested)
        self.canvas.view_changed.connect(self._on_canvas_view_changed)
        layout.addWidget(self.canvas)

        # 2.1 Barra de desplazamiento horizontal para vista ampliada (Zoom)
        self.scrollbar = QScrollBar(Qt.Horizontal, self)
        self.scrollbar.setRange(0, 1000)
        self.scrollbar.setValue(0)
        self.scrollbar.setSingleStep(20)
        self.scrollbar.setPageStep(200)
        self.scrollbar.setStyleSheet("""
            QScrollBar:horizontal {
                height: 8px;
                background: #0b1329;
                border-radius: 4px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #334155;
                min-width: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #0284c7;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #38bdf8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                height: 0px;
            }
        """)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_value_changed)
        self.scrollbar.setVisible(False)
        layout.addWidget(self.scrollbar)

        # 3. Barra de Controles y Herramientas
        h_tools = QHBoxLayout()
        h_tools.setSpacing(8)

        style = self.style()

        # Botón 1: Reproducir normalmente desde el marcador rojo
        self.btn_play_normal = QPushButton(" Reproducir")
        self.btn_play_normal.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.btn_play_normal.setStyleSheet("padding: 3px 10px; font-weight: 500;")
        self.btn_play_normal.setToolTip("Reproduce el audio normalmente a partir de donde esté el marcador rojo.")
        self.btn_play_normal.clicked.connect(self._on_play_normal_clicked)

        # Botón 2: Reproducir únicamente la selección
        self.btn_play_seg = QPushButton(" Reproducir Selección")
        self.btn_play_seg.setIcon(style.standardIcon(QStyle.SP_MediaSeekForward))
        self.btn_play_seg.setStyleSheet("padding: 3px 10px; font-weight: 500;")
        self.btn_play_seg.setToolTip("Reproduce únicamente el tramo o selección de voz marcado.")
        self.btn_play_seg.clicked.connect(self._on_play_selection_clicked)

        # Botón 3: Eliminar Segmento
        self.btn_del_seg = QPushButton(" Quitar Selección")
        self.btn_del_seg.setIcon(style.standardIcon(QStyle.SP_TrashIcon))
        self.btn_del_seg.setStyleSheet("padding: 3px 8px;")
        self.btn_del_seg.setToolTip("Elimina el tramo de audio actualmente seleccionado (tecla Supr).")
        self.btn_del_seg.clicked.connect(self.canvas.delete_selected_segment)

        # Botón 4: Limpiar Todos
        self.btn_clear_all = QPushButton(" Limpiar Todo")
        self.btn_clear_all.setIcon(style.standardIcon(QStyle.SP_DialogResetButton))
        self.btn_clear_all.setStyleSheet("padding: 3px 8px;")
        self.btn_clear_all.clicked.connect(self.canvas.clear_all_segments)

        # Etiqueta de información de tiempo
        self.lbl_info = QLabel("Seleccione o dibuje un tramo de audio.")
        self.lbl_info.setStyleSheet("color: #38bdf8; font-weight: 500; font-size: 11px;")

        # Controles de Zoom
        self.lbl_zoom_title = QLabel("Zoom:")
        self.lbl_zoom_title.setStyleSheet("color: #94a3b8; font-size: 11px; margin-left: 6px;")

        self.btn_zoom_out = QPushButton(" 🔍- ")
        self.btn_zoom_out.setToolTip("Reducir zoom (o Ctrl + Rueda hacia abajo)")
        self.btn_zoom_out.setStyleSheet("padding: 3px 8px; font-weight: bold;")
        self.btn_zoom_out.setEnabled(False)
        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 11px; min-width: 44px; padding: 2px 6px; background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;")

        self.btn_zoom_in = QPushButton(" 🔍+ ")
        self.btn_zoom_in.setToolTip("Aumentar zoom (o Ctrl + Rueda hacia arriba)")
        self.btn_zoom_in.setStyleSheet("padding: 3px 8px; font-weight: bold;")
        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)

        self.btn_zoom_fit = QPushButton(" 100% ")
        self.btn_zoom_fit.setToolTip("Restablecer zoom al 100% (ajustar vista)")
        self.btn_zoom_fit.setStyleSheet("padding: 3px 6px;")
        self.btn_zoom_fit.setEnabled(False)
        self.btn_zoom_fit.clicked.connect(self.canvas.reset_zoom)

        h_tools.addWidget(self.btn_play_normal)
        h_tools.addWidget(self.btn_play_seg)
        h_tools.addWidget(self.btn_del_seg)
        h_tools.addWidget(self.btn_clear_all)
        h_tools.addSpacing(10)
        h_tools.addWidget(self.lbl_info)
        h_tools.addStretch()
        h_tools.addWidget(self.lbl_zoom_title)
        h_tools.addWidget(self.btn_zoom_out)
        h_tools.addWidget(self.lbl_zoom)
        h_tools.addWidget(self.btn_zoom_in)
        h_tools.addWidget(self.btn_zoom_fit)

        layout.addLayout(h_tools)

        self.is_playing = False
        self.playing_mode = None  # 'normal' o 'selection'

    def load_audio_file(self, ffmpeg_path: str, media_file: str, duration: float):
        """Carga el audio y calcula la forma de onda visual."""
        peaks = extract_waveform_peaks(ffmpeg_path, media_file, num_peaks=2400)
        self.canvas.set_media(duration, peaks)
        self._update_info_label()

    def set_segments(self, segments: List[Tuple[float, float]]):
        self.canvas.set_segments(segments)

    def get_segments(self) -> List[Tuple[float, float]]:
        return self.canvas.segments

    def set_playhead_pos(self, seconds: float):
        self.canvas.set_playhead(seconds)

    def set_playing_state(self, playing: bool, mode: str = "selection"):
        self.is_playing = playing
        self.playing_mode = mode if playing else None
        style = self.style()

        if playing:
            if mode == "normal":
                self.btn_play_normal.setText(" Detener")
                self.btn_play_normal.setIcon(style.standardIcon(QStyle.SP_MediaStop))
                self.btn_play_normal.setStyleSheet("padding: 3px 10px; font-weight: bold; background-color: #dc2626; color: white;")

                self.btn_play_seg.setText(" Reproducir Selección")
                self.btn_play_seg.setIcon(style.standardIcon(QStyle.SP_MediaSeekForward))
                self.btn_play_seg.setStyleSheet("padding: 3px 10px; font-weight: 500;")
            else:
                self.btn_play_seg.setText(" Detener")
                self.btn_play_seg.setIcon(style.standardIcon(QStyle.SP_MediaStop))
                self.btn_play_seg.setStyleSheet("padding: 3px 10px; font-weight: bold; background-color: #dc2626; color: white;")

                self.btn_play_normal.setText(" Reproducir")
                self.btn_play_normal.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
                self.btn_play_normal.setStyleSheet("padding: 3px 10px; font-weight: 500;")
        else:
            self.btn_play_normal.setText(" Reproducir")
            self.btn_play_normal.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
            self.btn_play_normal.setStyleSheet("padding: 3px 10px; font-weight: 500;")

            self.btn_play_seg.setText(" Reproducir Selección")
            self.btn_play_seg.setIcon(style.standardIcon(QStyle.SP_MediaSeekForward))
            self.btn_play_seg.setStyleSheet("padding: 3px 10px; font-weight: 500;")

    def _on_play_normal_clicked(self):
        """Reproduce normalmente a partir de donde esté el marcador rojo."""
        if self.is_playing and self.playing_mode == "normal":
            self.stop_requested.emit()
            self.set_playing_state(False)
            return

        if self.is_playing:
            self.stop_requested.emit()

        st = self.canvas.playhead_pos
        self.play_normal_requested.emit(st)
        self.set_playing_state(True, mode="normal")

    def _on_play_selection_clicked(self):
        """Reproduce únicamente el tramo o selección activa."""
        if self.is_playing and self.playing_mode == "selection":
            self.stop_requested.emit()
            self.set_playing_state(False)
            return

        if self.is_playing:
            self.stop_requested.emit()

        seg = self.canvas.get_selected_segment()
        if seg:
            st, en = seg
            self.play_selection_requested.emit(st, en)
            self.play_requested.emit(st, en)
            self.set_playing_state(True, mode="selection")
        elif self.canvas.segments:
            st, en = self.canvas.segments[0]
            self.play_selection_requested.emit(st, en)
            self.play_requested.emit(st, en)
            self.set_playing_state(True, mode="selection")
        else:
            st = self.canvas.playhead_pos
            self.play_normal_requested.emit(st)
            self.set_playing_state(True, mode="normal")

    # Método de compatibilidad hacia atrás
    def _on_play_clicked(self):
        self._on_play_selection_clicked()

    def _on_segment_selected(self, idx: int, st: float, en: float):
        self._update_info_label()

    def _on_segments_changed(self, segs: list):
        self._update_info_label()
        self.segments_updated.emit(segs)

    def _on_canvas_view_changed(self, view_start: float, zoom_level: float):
        self.lbl_zoom.setText(f"{int(round(zoom_level * 100))}%")
        if zoom_level <= 1.01:
            self.scrollbar.setVisible(False)
            self.btn_zoom_out.setEnabled(False)
            self.btn_zoom_fit.setEnabled(False)
        else:
            self.scrollbar.setVisible(True)
            self.btn_zoom_out.setEnabled(True)
            self.btn_zoom_fit.setEnabled(True)

            vis_dur = max(0.001, self.canvas.total_duration / zoom_level)
            max_start = max(0.001, self.canvas.total_duration - vis_dur)
            val = int(round((view_start / max_start) * 1000))
            page = max(50, int((vis_dur / self.canvas.total_duration) * 1000))

            self.scrollbar.blockSignals(True)
            self.scrollbar.setPageStep(page)
            self.scrollbar.setValue(min(1000, max(0, val)))
            self.scrollbar.blockSignals(False)

        self.btn_zoom_in.setEnabled(zoom_level < 19.9)

    def _on_scrollbar_value_changed(self, value: int):
        if self.canvas.total_duration <= 0 or self.canvas.zoom_level <= 1.0:
            return
        vis_dur = max(0.001, self.canvas.total_duration / self.canvas.zoom_level)
        max_start = max(0.0, self.canvas.total_duration - vis_dur)
        new_start = (value / 1000.0) * max_start
        self.canvas.set_view_start(new_start)

    def _update_info_label(self):
        segs = self.canvas.segments
        total_dur = sum((en - st) for st, en in segs)
        curr = self.canvas.get_selected_segment()
        if curr:
            st, en = curr
            dur = en - st
            self.lbl_info.setText(
                f"Tramo activo: {format_seconds_exact(st)} - {format_seconds_exact(en)} ({dur:.2f}s) | "
                f"Total seleccionado: {len(segs)} tramos ({total_dur:.2f}s)"
            )
        elif segs:
            self.lbl_info.setText(f"Total seleccionado: {len(segs)} tramos ({total_dur:.2f}s)")
        else:
            self.lbl_info.setText("Sin tramos seleccionados. Arrastra el ratón sobre la onda para marcar voz.")
