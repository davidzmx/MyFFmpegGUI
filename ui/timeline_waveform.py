#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Timeline Waveform Selector Widget
Componente gráfico interactivo para visualización de forma de onda y selección manual/ajuste
de segmentos de voz mediante arrastre con el ratón, manijas de tiempo y reproducción integrada.
"""

import os
import sys
import subprocess
from typing import List, Tuple, Optional
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QStyle, QSizePolicy, QToolTip, QShortcut
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


def extract_waveform_peaks(ffmpeg_path: str, input_file: str, num_peaks: int = 800) -> np.ndarray:
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
    mover y redimensionar segmentos de tiempo arrastrando con el ratón.
    """
    segment_selected = pyqtSignal(int, float, float) # (index, start_sec, end_sec)
    segments_changed = pyqtSignal(list)              # [(st, en), ...]
    seek_requested = pyqtSignal(float)               # time in seconds

    HANDLE_WIDTH = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(125)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.total_duration: float = 0.0
        self.waveform_peaks: Optional[np.ndarray] = None
        self.segments: List[Tuple[float, float]] = []
        self.selected_idx: int = -1
        self.playhead_pos: float = 0.0

        # Estados de interacción con el ratón
        self._drag_mode: Optional[str] = None  # 'create', 'resize_left', 'resize_right', 'move'
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
        self.update()

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
        self.update()

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

    # Coordenadas X <-> Segundos
    def _time_to_x(self, t: float) -> float:
        if self.total_duration <= 0:
            return 0.0
        return (t / self.total_duration) * self.width()

    def _x_to_time(self, x: float) -> float:
        if self.width() <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, x / float(self.width())))
        return ratio * self.total_duration

    # Eventos de Ratón
    def mousePressEvent(self, event):
        if self.total_duration <= 0 or event.button() != Qt.LeftButton:
            return

        x = event.pos().x()
        t = self._x_to_time(x)
        self._drag_start_x = x
        self._drag_start_time = t

        # Comprobar si se hace clic sobre un asa o segmento existente
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
            # Clic en zona vacía: si es en la regla superior (y < 22), hacer seek
            if event.pos().y() <= 22:
                self.seek_requested.emit(t)
                self.set_playhead(t)
            else:
                # Iniciar creación de un nuevo segmento arrastrando
                self._drag_mode = 'create'
                self.selected_idx = -1
                self._orig_seg = (t, t)
                self.update()

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        t = self._x_to_time(x)

        if not self._drag_mode:
            # Actualizar cursor según posición
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
            elif event.pos().y() <= 22:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return

        # Arrastre activo
        if self._drag_mode == 'create':
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

        if self._drag_mode == 'create' and self._orig_seg:
            st, en = self._orig_seg
            if en - st >= 0.35:
                self.segments.append((round(st, 2), round(en, 2)))
                self.segments.sort(key=lambda s: s[0])
                self.selected_idx = self.segments.index((round(st, 2), round(en, 2)))
                self.segments_changed.emit(self.segments)
                self.segment_selected.emit(self.selected_idx, st, en)
            else:
                # Clic sin arrastre suficiente: mover la aguja roja a este punto
                self.seek_requested.emit(t)
                self.set_playhead(t)
            self._orig_seg = None

        elif self._drag_mode == 'move':
            # Si solo fue un clic sin arrastre (< 4px), mover la aguja roja a este punto
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

        ruler_h = 24.0
        wave_h = h - ruler_h
        center_y = ruler_h + (wave_h / 2.0)

        # 1. Fondo de la línea de tiempo (Dark Slate)
        painter.fillRect(0, 0, int(w), int(h), QColor("#0b1329"))
        painter.fillRect(0, 0, int(w), int(ruler_h), QColor("#111c38"))

        # Borde divisor de regla
        painter.setPen(QPen(QColor("#1e293b"), 1))
        painter.drawLine(0, int(ruler_h), int(w), int(ruler_h))

        # 2. Regla superior de marcas de tiempo
        painter.setFont(QFont("Consolas", 8))
        step_sec = 5.0 if self.total_duration <= 60.0 else (10.0 if self.total_duration <= 180.0 else 30.0)

        t_mark = 0.0
        while t_mark <= self.total_duration:
            x_m = self._time_to_x(t_mark)
            painter.setPen(QPen(QColor("#475569"), 1))
            painter.drawLine(int(x_m), int(ruler_h - 7), int(x_m), int(ruler_h))

            # Texto de tiempo
            lbl = format_seconds_exact(t_mark).split(".")[0]
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(int(x_m) + 3, int(ruler_h - 6), lbl)
            t_mark += step_sec

        # Línea central sutil de la forma de onda
        painter.setPen(QPen(QColor("#1e293b"), 1, Qt.DashLine))
        painter.drawLine(0, int(center_y), int(w), int(center_y))

        # 3. Dibujar Forma de Onda (Waveform)
        if self.waveform_peaks is not None and len(self.waveform_peaks) > 0:
            num_bars = len(self.waveform_peaks)
            bar_w = max(1.0, w / float(num_bars))
            max_amp = (wave_h / 2.0) - 4.0

            painter.setPen(Qt.NoPen)
            for i, peak in enumerate(self.waveform_peaks):
                bx = i * bar_w
                bh = max(2.0, float(peak) * max_amp)
                # Gradiente vertical de barra de audio
                painter.fillRect(
                    QRectF(bx, center_y - bh, max(1.0, bar_w - 0.5), bh * 2.0),
                    QColor("#1e3a8a")
                )

        # 4. Dibujar Segmentos Seleccionados (Siempre translúcidos sobre la onda)
        for idx, (st, en) in enumerate(self.segments):
            x1 = self._time_to_x(st)
            x2 = self._time_to_x(en)
            seg_w = max(4.0, x2 - x1)
            is_active = (idx == self.selected_idx)

            # Fondo del bloque de voz (Translúcido para que la onda de audio sea siempre visible)
            rect = QRectF(x1, ruler_h + 2.0, seg_w, wave_h - 4.0)
            fill_color = QColor(14, 165, 233, 75) if is_active else QColor(56, 189, 248, 38)
            painter.fillRect(rect, fill_color)

            # Borde exterior (Asegurar NoBrush para que drawRoundedRect NO rellene con pincel previo)
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
            painter.drawRoundedRect(QRectF(x1, center_y - 12, 4.0, 24.0), 2.0, 2.0)
            # Asa derecha
            painter.drawRoundedRect(QRectF(x2 - 4.0, center_y - 12, 4.0, 24.0), 2.0, 2.0)

            # Resetear pincel a NoBrush inmediatamente para la siguiente iteración
            painter.setBrush(Qt.NoBrush)

            # Etiqueta de tiempo del segmento
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold if is_active else QFont.Normal))
            painter.setPen(QColor("#f8fafc") if is_active else QColor("#cbd5e1"))
            dur_str = f"{en - st:.1f}s"
            painter.drawText(QRectF(x1 + 6, ruler_h + 6, seg_w - 12, 16), Qt.AlignLeft, f"#{idx+1} ({dur_str})")

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

        # 5. Aguja de Reproducción (Playhead)
        px = self._time_to_x(self.playhead_pos)
        painter.setPen(QPen(QColor("#ef4444"), 2.0))
        painter.drawLine(int(px), 0, int(px), int(h))

        # Cabeza triangular del playhead
        head = QPolygonF([
            QPointF(px - 5, 0),
            QPointF(px + 5, 0),
            QPointF(px, 8)
        ])
        painter.setBrush(QBrush(QColor("#ef4444")))
        painter.drawPolygon(head)


class AudioSegmentSelectorWidget(QWidget):
    """
    Contenedor completo que incluye el lienzo interactivo de la forma de onda,
    barra de transporte, controles de reproducción normal y por tramo, borrado y resumen de tiempos.
    """
    segments_updated = pyqtSignal(list)
    play_normal_requested = pyqtSignal(float)           # start_sec (hasta el final del archivo)
    play_selection_requested = pyqtSignal(float, float) # (start_sec, end_sec)
    play_requested = pyqtSignal(float, float)           # compatibilidad hacia atrás
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(float)                  # time in seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Cabecera explicativa
        self.lbl_guide = QLabel(
            "✂️ <b>Selector Gráfico de Voz:</b> Haz clic en la regla o sobre la onda para mover el marcador rojo. "
            "Arrastra con el ratón sobre la onda para marcar o recortar tramos de habla. Arrastra los bordes para ajustar con precisión."
        )
        self.lbl_guide.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_guide)

        # 2. Lienzo de Forma de Onda y Línea de Tiempo
        self.canvas = AudioTimelineCanvas(self)
        self.canvas.segment_selected.connect(self._on_segment_selected)
        self.canvas.segments_changed.connect(self._on_segments_changed)
        self.canvas.seek_requested.connect(self.seek_requested)
        layout.addWidget(self.canvas)

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

        h_tools.addWidget(self.btn_play_normal)
        h_tools.addWidget(self.btn_play_seg)
        h_tools.addWidget(self.btn_del_seg)
        h_tools.addWidget(self.btn_clear_all)
        h_tools.addSpacing(10)
        h_tools.addWidget(self.lbl_info)
        h_tools.addStretch()

        layout.addLayout(h_tools)

        self.is_playing = False
        self.playing_mode = None  # 'normal' o 'selection'

    def load_audio_file(self, ffmpeg_path: str, media_file: str, duration: float):
        """Carga el audio y calcula la forma de onda visual."""
        peaks = extract_waveform_peaks(ffmpeg_path, media_file, num_peaks=600)
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
            # Si no hay selección, reproducir desde el marcador rojo
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
