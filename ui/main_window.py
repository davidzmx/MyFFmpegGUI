#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ventana Principal de MyFFmpegGUI
Suite Multimedia Sin Pérdida con soporte para Video a Audio (MP3/WAV), Conversión de Video,
Fotogramas, Segmentación, Fusión y Carpeta Base configurable.
"""

import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QScrollArea
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

import ffmpeg_core
import config_manager
from ui.tab_audio import TabAudio
from ui.tab_convert_video import TabConvertVideo
from ui.tab_extract_frames import TabExtractFrames
from ui.tab_create_video import TabCreateVideo
from ui.tab_segment import TabSegment
from ui.tab_concat import TabConcat
from ui.tab_settings import TabSettings


class MainWindow(QMainWindow):
    def __init__(self, initial_tab: str = None, initial_file: str = None):
        super().__init__()
        self.setWindowTitle("MyFFmpeg GUI - Procesamiento Multimedia Sin Pérdida (Windows & Linux)")

        # Establecer icono de la ventana principal
        icon_path = config_manager.get_app_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1000, 780)
        self.setMinimumSize(880, 640)

        # Contenedor central
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # Encabezado con título e indicador de calidad
        header_layout = QHBoxLayout()

        title_vbox = QVBoxLayout()
        lbl_title = QLabel("🎬 MyFFmpeg GUI")
        lbl_title.setObjectName("lbl_title")
        lbl_sub = QLabel("Herramienta gráfica profesional para FFmpeg | Soporte Multiplataforma")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_vbox.addWidget(lbl_title)
        title_vbox.addWidget(lbl_sub)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        badge = QLabel("⚡ 100% Sin Pérdida (Stream Copy / Lossless)")
        badge.setObjectName("badge_lossless")
        header_layout.addWidget(badge, alignment=Qt.AlignVCenter)

        main_layout.addLayout(header_layout)

        # Tabs / Pestañas
        self.tabs = QTabWidget(self)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tab_settings = TabSettings(self, self)

        # Instanciar cada una de las pestañas
        self.tab_audio = TabAudio(self.get_active_ffmpeg_paths, self)
        self.tab_convert = TabConvertVideo(self.get_active_ffmpeg_paths, self)
        self.tab_extract = TabExtractFrames(self.get_active_ffmpeg_paths, self)
        self.tab_create = TabCreateVideo(self.get_active_ffmpeg_paths, self)
        self.tab_segment = TabSegment(self.get_active_ffmpeg_paths, self)
        self.tab_concat = TabConcat(self.get_active_ffmpeg_paths, self)

        # Títulos limpios, concisos y compatibles con fuentes de Windows y Linux
        self.tabs.addTab(self._wrap_tab(self.tab_audio), "Audio (MP3 / WAV)")
        self.tabs.addTab(self._wrap_tab(self.tab_convert), "Convertir Video")
        self.tabs.addTab(self._wrap_tab(self.tab_extract), "Extraer Fotogramas")
        self.tabs.addTab(self._wrap_tab(self.tab_create), "Crear Video")
        self.tabs.addTab(self._wrap_tab(self.tab_segment), "Segmentar Video")
        self.tabs.addTab(self.tab_concat, "Unir Segmentos")
        self.tabs.addTab(self.tab_settings, "Ajustes")

        # Mapa de nombres de pestañas para invocación desde CLI y menú contextual
        self.tab_map = {
            "audio": (0, self.tab_audio),
            "video": (1, self.tab_convert),
            "frames": (2, self.tab_extract),
            "create": (3, self.tab_create),
            "segment": (4, self.tab_segment),
            "concat": (5, self.tab_concat),
            "settings": (6, self.tab_settings),
        }

        # Forzar activación inmediata de layout al cambiar de pestaña
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Sincronizar cambios de configuración guardados con todas las pestañas
        self.tab_settings.config_saved.connect(self._on_config_saved)

        main_layout.addWidget(self.tabs)

        # Cargar archivo y pestaña inicial si fueron invocados desde el menú contextual / CLI
        if initial_file or initial_tab:
            self.load_target(initial_tab, initial_file)

    def load_target(self, tab_name: str = None, file_path: str = None):
        """Carga un archivo y activa la pestaña correspondiente solicitada por CLI o menú contextual."""
        import urllib.parse
        import os

        if file_path:
            # Soportar URIs tipo file:// pasadas por gestores de archivos (como Dolphin)
            if file_path.startswith("file://"):
                parsed = urllib.parse.urlparse(file_path)
                file_path = urllib.parse.unquote(parsed.path)
            file_path = os.path.abspath(file_path)

        # Si no se especificó pestaña pero hay archivo, deducir la pestaña más lógica
        if file_path and not tab_name:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma"):
                tab_name = "audio"
            elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                tab_name = "create"
            else:
                # Video por defecto
                tab_name = "audio"

        if tab_name and tab_name in self.tab_map:
            idx, tab_widget = self.tab_map[tab_name]
            self.tabs.setCurrentIndex(idx)
            if file_path and os.path.isfile(file_path):
                if hasattr(tab_widget, "input_selector"):
                    tab_widget.input_selector.set_path(file_path)

    def _wrap_tab(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _on_tab_changed(self, index: int):
        scroll_or_widget = self.tabs.widget(index)
        if isinstance(scroll_or_widget, QScrollArea):
            inner = scroll_or_widget.widget()
            if inner:
                inner.updateGeometry()
                if inner.layout():
                    inner.layout().activate()
                if hasattr(inner, "update_base_dir_display"):
                    inner.update_base_dir_display()
        elif scroll_or_widget:
            scroll_or_widget.updateGeometry()
            if scroll_or_widget.layout():
                scroll_or_widget.layout().activate()
            if hasattr(scroll_or_widget, "update_base_dir_display"):
                scroll_or_widget.update_base_dir_display()

    def _on_config_saved(self):
        """Actualiza la visualización de la Carpeta Base en todas las pestañas."""
        for tab in (self.tab_audio, self.tab_convert, self.tab_extract, self.tab_create, self.tab_segment, self.tab_concat):
            if hasattr(tab, "update_base_dir_display"):
                tab.update_base_dir_display()

    def get_active_ffmpeg_paths(self):
        """Devuelve las rutas activas de ffmpeg y ffprobe."""
        configured_ffmpeg, configured_ffprobe = self.tab_settings.get_paths()
        if configured_ffmpeg:
            return configured_ffmpeg, configured_ffprobe

        cfg = config_manager.load_config()
        if cfg.get("ffmpeg_path"):
            return cfg.get("ffmpeg_path"), cfg.get("ffprobe_path")

        # Fallback a detección por defecto
        return ffmpeg_core.get_default_ffmpeg_paths()
