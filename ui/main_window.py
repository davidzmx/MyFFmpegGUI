#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ventana Principal de MyFFmpegGUI
Suite Multimedia Sin Pérdida con soporte para Video a Audio (MP3/WAV), Conversión de Video,
Fotogramas, Segmentación, Fusión y Carpeta Base configurable.
"""

import os
import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QScrollArea, QStyle, QApplication
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

import ffmpeg_core
import config_manager
from ui.widgets import DragDropTabWidget, TabDropFilter, extract_mime_paths, DropLineEdit
from ui.tab_audio import TabAudio
from ui.tab_convert_video import TabConvertVideo
from ui.tab_extract_frames import TabExtractFrames
from ui.tab_create_video import TabCreateVideo
from ui.tab_segment import TabSegment
from ui.tab_concat import TabConcat
from ui.tab_compare import TabCompare
from ui.tab_add_audio import TabAddAudio
from ui.tab_voice_isolation import TabVoiceIsolation
from ui.tab_settings import TabSettings


class MainWindow(QMainWindow):
    def __init__(self, initial_tab: str = None, initial_file: str = None):
        super().__init__()
        self.setWindowTitle("MyFFmpeg GUI - Procesamiento Multimedia Sin Pérdida (Windows & Linux)")

        # Establecer icono de la ventana principal
        icon_path = config_manager.get_app_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        # Tamaño inicial adaptativo y centrado para asegurar que todas las pestañas se muestren completas
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            init_w = min(1180, max(980, avail.width() - 40))
            init_h = min(800, max(640, avail.height() - 60))
            self.resize(init_w, init_h)
            # Centrar en la pantalla
            geo = self.frameGeometry()
            geo.moveCenter(avail.center())
            self.move(geo.topLeft())
        else:
            self.resize(1180, 800)
        self.setMinimumSize(960, 640)

        # Contenedor central
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # Encabezado con título e indicador de calidad
        header_layout = QHBoxLayout()

        title_vbox = QVBoxLayout()
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        lbl_header_icon = QLabel()
        win_icon = self.windowIcon()
        if win_icon and not win_icon.isNull():
            lbl_header_icon.setPixmap(win_icon.pixmap(24, 24))
        else:
            lbl_header_icon.setPixmap(self.style().standardIcon(QStyle.SP_MediaPlay).pixmap(24, 24))

        lbl_title = QLabel("MyFFmpeg GUI")
        lbl_title.setObjectName("lbl_title")

        title_row.addWidget(lbl_header_icon)
        title_row.addWidget(lbl_title)
        title_row.addStretch()

        lbl_sub = QLabel("Herramienta gráfica profesional para FFmpeg | Soporte Multiplataforma")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_vbox.addLayout(title_row)
        title_vbox.addWidget(lbl_sub)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        badge = QLabel("100% Sin Pérdida (Stream Copy / Lossless)")
        badge.setObjectName("badge_lossless")
        header_layout.addWidget(badge, alignment=Qt.AlignVCenter)

        main_layout.addLayout(header_layout)

        # Tabs / Pestañas con soporte para Drag & Drop y autoactivación al arrastrar
        self.tabs = DragDropTabWidget(self)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.files_dropped_on_active_tab.connect(self.load_files_into_tab)
        self.tab_settings = TabSettings(self, self)

        # Instanciar cada una de las pestañas
        self.tab_audio = TabAudio(self.get_active_ffmpeg_paths, self)
        self.tab_voice = TabVoiceIsolation(self.get_active_ffmpeg_paths, self)
        self.tab_add_audio = TabAddAudio(self.get_active_ffmpeg_paths, self)
        self.tab_convert = TabConvertVideo(self.get_active_ffmpeg_paths, self)
        self.tab_extract = TabExtractFrames(self.get_active_ffmpeg_paths, self)
        self.tab_create = TabCreateVideo(self.get_active_ffmpeg_paths, self)
        self.tab_segment = TabSegment(self.get_active_ffmpeg_paths, self)
        self.tab_concat = TabConcat(self.get_active_ffmpeg_paths, self)
        self.tab_compare = TabCompare(self.get_active_ffmpeg_paths, self)

        # Títulos limpios, concisos y compatibles con fuentes de Windows y Linux
        self.tabs.addTab(self.tab_audio, "Audio (MP3 / WAV)")
        self.tabs.addTab(self.tab_convert, "Convertir Video")
        self.tabs.addTab(self.tab_add_audio, "Poner Audio a Video")
        self.tabs.addTab(self.tab_extract, "Extraer Fotogramas")
        self.tabs.addTab(self.tab_create, "Crear Video")
        self.tabs.addTab(self.tab_segment, "Segmentar Video")
        self.tabs.addTab(self.tab_concat, "Unir Segmentos")
        self.tabs.addTab(self.tab_voice, "Aislar Voces")
        self.tabs.addTab(self.tab_compare, "Comparar Videos")
        self.tabs.addTab(self.tab_settings, "Ajustes")

        # Habilitar captura de archivos arrastrados en el cuerpo de cada pestaña
        self._tab_filters = []
        for i in range(self.tabs.count()):
            self._install_tab_drop_filter(i, self.tabs.widget(i))

        # Mapa de nombres de pestañas para invocación desde CLI y menú contextual
        self.tab_map = {
            "audio": (0, self.tab_audio),
            "video": (1, self.tab_convert),
            "add_audio": (2, self.tab_add_audio),
            "frames": (3, self.tab_extract),
            "create": (4, self.tab_create),
            "segment": (5, self.tab_segment),
            "concat": (6, self.tab_concat),
            "voice": (7, self.tab_voice),
            "compare": (8, self.tab_compare),
            "settings": (9, self.tab_settings),
        }

        # Forzar activación inmediata de layout al cambiar de pestaña
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Sincronizar cambios de configuración guardados con todas las pestañas
        self.tab_settings.config_saved.connect(self._on_config_saved)

        main_layout.addWidget(self.tabs)

        # Cargar archivo y pestaña inicial si fueron invocados desde el menú contextual / CLI
        if initial_file or initial_tab:
            self.load_target(initial_tab, initial_file)

    def _install_tab_drop_filter(self, tab_index: int, widget: QWidget):
        """Instala recursivamente el filtro de arrastrar y soltar en la superficie de la pestaña."""
        if not widget:
            return
        filt = TabDropFilter(lambda: tab_index, self.load_files_into_tab)
        self._tab_filters.append(filt)

        def _enable(w):
            if isinstance(w, DropLineEdit) or getattr(w, "_has_custom_drop", False):
                return
            w.setAcceptDrops(True)
            w.installEventFilter(filt)
            for child in w.findChildren(QWidget):
                if not isinstance(child, DropLineEdit) and not getattr(child, "_has_custom_drop", False):
                    child.setAcceptDrops(True)
                    child.installEventFilter(filt)

        _enable(widget)

    def load_files_into_tab(self, tab_index: int, paths: list):
        """Carga uno o más archivos en la pestaña especificada y la activa si no lo estaba."""
        if not paths or tab_index < 0 or tab_index >= self.tabs.count():
            return

        self.tabs.setCurrentIndex(tab_index)
        tab_widget = self.tabs.widget(tab_index)
        first_path = paths[0]
        audio_exts = (".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".opus", ".wma")

        if tab_widget == self.tab_audio:
            self.tab_audio.input_selector.set_path(first_path)

        elif tab_widget == self.tab_voice:
            self.tab_voice.input_selector.set_path(first_path)

        elif tab_widget == self.tab_convert:
            self.tab_convert.input_selector.set_path(first_path)

        elif tab_widget == self.tab_add_audio:
            videos = [p for p in paths if os.path.splitext(p)[1].lower() not in audio_exts]
            audios = [p for p in paths if os.path.splitext(p)[1].lower() in audio_exts]
            if videos and audios:
                self.tab_add_audio.video_selector.set_path(videos[0])
                self.tab_add_audio.audio_selector.set_path(audios[0])
            elif audios and not videos:
                if self.tab_add_audio.video_selector.get_path():
                    self.tab_add_audio.audio_selector.set_path(audios[0])
                else:
                    self.tab_add_audio.audio_selector.set_path(audios[0])
            elif videos:
                self.tab_add_audio.video_selector.set_path(videos[0])
            else:
                self.tab_add_audio.video_selector.set_path(first_path)

        elif tab_widget == self.tab_extract:
            self.tab_extract.input_selector.set_path(first_path)

        elif tab_widget == self.tab_create:
            if os.path.isdir(first_path) or not os.path.splitext(first_path)[1]:
                self.tab_create.folder_selector.set_path(first_path)
            else:
                ext = os.path.splitext(first_path)[1].lower()
                if ext in audio_exts:
                    self.tab_create.audio_selector.set_path(first_path)
                else:
                    self.tab_create.folder_selector.set_path(os.path.dirname(first_path))

        elif tab_widget == self.tab_segment:
            self.tab_segment.input_selector.set_path(first_path)

        elif tab_widget == self.tab_concat:
            self.tab_concat._insert_paths(paths)

        elif tab_widget == self.tab_compare:
            if len(paths) >= 2:
                self.tab_compare.input_a.set_path(paths[0])
                self.tab_compare.input_b.set_path(paths[1])
            else:
                if not self.tab_compare.input_a.get_path():
                    self.tab_compare.input_a.set_path(first_path)
                elif not self.tab_compare.input_b.get_path():
                    self.tab_compare.input_b.set_path(first_path)
                else:
                    self.tab_compare.input_a.set_path(first_path)

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
            if file_path and os.path.exists(file_path):
                self.load_files_into_tab(idx, [file_path])

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
        """Actualiza la visualización de la Carpeta Base y paneles de consola en todas las pestañas."""
        for tab in (self.tab_audio, self.tab_voice, self.tab_add_audio, self.tab_convert, self.tab_extract, self.tab_create, self.tab_segment, self.tab_concat, self.tab_compare):
            if hasattr(tab, "update_base_dir_display"):
                tab.update_base_dir_display()
            if hasattr(tab, "apply_console_panel_settings"):
                tab.apply_console_panel_settings()

    def sync_console_panels(self, pos: str = None, visible: bool = None):
        """Sincroniza la posición y visibilidad del panel de consola en todas las pestañas."""
        if pos is not None:
            config_manager.set_console_panel_position(pos)
        if visible is not None:
            config_manager.set_console_panel_visible(visible)
        for tab in (self.tab_audio, self.tab_voice, self.tab_add_audio, self.tab_convert, self.tab_extract, self.tab_create, self.tab_segment, self.tab_concat):
            if hasattr(tab, "apply_console_panel_settings"):
                tab.apply_console_panel_settings(pos=pos, visible=visible)

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

    def closeEvent(self, event):
        """Asegura la cancelación y terminación limpia de todos los subprocesos y trabajadores al cerrar."""
        tabs_to_clean = (
            getattr(self, "tab_audio", None),
            getattr(self, "tab_voice", None),
            getattr(self, "tab_add_audio", None),
            getattr(self, "tab_convert", None),
            getattr(self, "tab_extract", None),
            getattr(self, "tab_create", None),
            getattr(self, "tab_segment", None),
            getattr(self, "tab_concat", None),
            getattr(self, "tab_compare", None),
        )
        for tab in tabs_to_clean:
            if tab is not None:
                if hasattr(tab, "worker") and tab.worker:
                    try:
                        if tab.worker.isRunning():
                            tab.worker.cancel()
                            tab.worker.wait(400)
                    except Exception:
                        pass
                if hasattr(tab, "_cleanup_playback_procs"):
                    try:
                        tab._cleanup_playback_procs()
                    except Exception:
                        pass
        event.accept()
        super().closeEvent(event)

