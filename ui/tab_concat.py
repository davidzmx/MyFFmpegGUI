#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Unir / Concatenar segmentos de video sin pérdida de calidad (Stream Copy)
"""

import os
import tempfile
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QListWidget, QFileDialog, QCheckBox,
    QSplitter, QSizePolicy, QScrollArea, QFrame, QStyle, QRadioButton, QSpinBox, QSlider
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget,
    ConsoleOutputPanel, setup_tab_console_layout
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class SegmentListWidget(QListWidget):
    """Lista interactiva con soporte de reordenamiento interno y arrastrar archivos desde el explorador."""
    def __init__(self, on_files_dropped=None, parent=None):
        super().__init__(parent)
        self.on_files_dropped = on_files_dropped
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
            if paths and self.on_files_dropped:
                self.on_files_dropped(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class TabConcat(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.temp_list_file = None

        # 1. Lista interactiva de segmentos (Panel superior de contenido - Redimensionable mediante divisor)
        group_list = QGroupBox("1. Lista de Segmentos a Unir (Orden Secuencial - Redimensionable)")
        group_list.setMinimumHeight(110)
        layout_list = QVBoxLayout(group_list)
        layout_list.setSpacing(6)

        self.list_widget = SegmentListWidget(on_files_dropped=self._insert_paths, parent=self)
        self.list_widget.setMinimumHeight(60)
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_list.addWidget(self.list_widget, 1)

        # Botones de gestión de lista
        self.btn_add_files = QPushButton("Añadir Archivos...")
        self.btn_add_files.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_add_files.clicked.connect(self._add_files)

        self.btn_add_folder = QPushButton("Añadir Carpeta...")
        self.btn_add_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        self.btn_add_folder.clicked.connect(self._add_folder)

        self.btn_clear = QPushButton("Limpiar Todo")
        self.btn_clear.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.btn_clear.clicked.connect(self._clear_list)

        self.btn_up = QPushButton("Subir")
        self.btn_up.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        self.btn_up.clicked.connect(self._move_up)

        self.btn_down = QPushButton("Bajar")
        self.btn_down.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.btn_down.clicked.connect(self._move_down)

        self.btn_remove = QPushButton("Eliminar")
        self.btn_remove.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_remove.clicked.connect(self._remove_selected)

        self.tools_container = QWidget()
        layout_list.addWidget(self.tools_container)

        self.lbl_count = QLabel("Total: 0 segmentos seleccionados")
        self.lbl_count.setObjectName("lbl_meta")
        layout_list.addWidget(self.lbl_count)

        # 2. Panel Central de Opciones y Configuración (con scroll interno fluido)
        middle_scroll = QScrollArea(self)
        middle_scroll.setWidgetResizable(True)
        middle_scroll.setFrameShape(QFrame.NoFrame)
        middle_scroll.setMinimumHeight(100)

        middle_container = QWidget()
        layout_middle = QVBoxLayout(middle_container)
        layout_middle.setContentsMargins(0, 4, 0, 4)
        layout_middle.setSpacing(10)

        # 2.1 Modo de Unión
        group_opts = QGroupBox("2. Modo de Unión")
        layout_opts = QVBoxLayout(group_opts)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Método:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(
            "Concat Demuxer (Stream Copy - 100% Sin Pérdida de Calidad)", "copy"
        )
        self.combo_mode.addItem(
            "Recodificación Inteligente (Para videos con diferente resolución o códec)", "reencode"
        )
        self.combo_mode.currentIndexChanged.connect(self._on_mode_combo_changed)
        h_mode.addWidget(self.combo_mode, 1)
        layout_opts.addLayout(h_mode)

        # Control de eliminación de micro-stutter / solapamiento
        self.chk_anti_stutter = QCheckBox("Eliminar micro-stutter / solapamiento entre segmentos")
        self.chk_anti_stutter.setToolTip(
            "Elimina fotogramas duplicados o congelados en las uniones entre segmentos (requiere recodificación inteligente)."
        )
        self.chk_anti_stutter.toggled.connect(self._on_anti_stutter_toggled)
        layout_opts.addWidget(self.chk_anti_stutter)

        self.widget_anti_stutter_opts = QWidget()
        layout_stutter_box = QVBoxLayout(self.widget_anti_stutter_opts)
        layout_stutter_box.setContentsMargins(16, 2, 0, 4)
        layout_stutter_box.setSpacing(6)

        self.radio_stutter_auto = QRadioButton("Automático inteligente (mpdecimate - detecta y descarta cuadros duplicados)")
        self.radio_stutter_auto.setChecked(True)
        self.radio_stutter_auto.setToolTip("Analiza el flujo de video y descarta automáticamente cuadros idénticos generados en la unión.")
        self.radio_stutter_auto.toggled.connect(self._on_stutter_mode_changed)
        layout_stutter_box.addWidget(self.radio_stutter_auto)

        h_stutter_manual = QHBoxLayout()
        h_stutter_manual.setSpacing(8)
        self.radio_stutter_manual = QRadioButton("Manual: Omitir primeros fotogramas de cada segmento siguiente:")
        self.radio_stutter_manual.setToolTip("Descarta un número fijo de fotogramas al inicio de cada segmento posterior para eliminar fotogramas clave duplicados.")
        self.radio_stutter_manual.toggled.connect(self._on_stutter_mode_changed)
        h_stutter_manual.addWidget(self.radio_stutter_manual)

        self.spin_drop_frames = QSpinBox()
        self.spin_drop_frames.setRange(1, 10)
        self.spin_drop_frames.setValue(1)
        self.spin_drop_frames.setSuffix(" fotograma(s)")
        self.spin_drop_frames.setEnabled(False)
        self.spin_drop_frames.valueChanged.connect(lambda _: self._update_command_preview())
        h_stutter_manual.addWidget(self.spin_drop_frames)
        h_stutter_manual.addStretch()
        layout_stutter_box.addLayout(h_stutter_manual)

        self.lbl_stutter_hint = QLabel(
            "• Automático: Recomendado si no sabes cuántos fotogramas se duplican.\n"
            "• Manual: Recomendado si tus cortes siempre dejan 1 o 2 fotogramas idénticos al inicio del segmento posterior."
        )
        self.lbl_stutter_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout_stutter_box.addWidget(self.lbl_stutter_hint)

        self.widget_anti_stutter_opts.setVisible(False)
        layout_opts.addWidget(self.widget_anti_stutter_opts)

        lbl_note = QLabel(
            "• Stream Copy une los archivos a la velocidad de lectura del disco sin alterar un solo píxel.\n"
            "• La eliminación de micro-stutter analiza o descarta fotogramas duplicados mediante recodificación inteligente."
        )
        lbl_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_opts.addWidget(lbl_note)
        layout_middle.addWidget(group_opts)

        # 2.2 Pista de Audio Opcional para el Video Unido
        group_audio = QGroupBox("3. Pista de Audio Opcional (Música / Voz / Banda Sonora)")
        layout_audio = QVBoxLayout(group_audio)

        h_audio_top = QHBoxLayout()
        self.audio_selector = FileSelector(
            placeholder="Opcional: Seleccione o arrastre un archivo de audio (MP3, WAV, AAC, M4A, FLAC)...",
            file_filter="Archivos de Audio (*.mp3 *.wav *.aac *.m4a *.flac *.ogg *.wma *.opus);;Todos (*.*)"
        )
        self.audio_selector.file_selected.connect(self._on_audio_file_changed)
        h_audio_top.addWidget(self.audio_selector, 1)

        self.btn_clear_audio = QPushButton("Quitar Audio")
        self.btn_clear_audio.setIcon(self.style().standardIcon(QStyle.SP_DialogDiscardButton))
        self.btn_clear_audio.setToolTip("Quitar la pista de audio seleccionada")
        self.btn_clear_audio.clicked.connect(self._clear_audio)
        self.btn_clear_audio.setEnabled(False)
        h_audio_top.addWidget(self.btn_clear_audio)
        layout_audio.addLayout(h_audio_top)

        # Opciones avanzadas de audio
        self.widget_audio_opts = QWidget()
        h_audio_opts = QHBoxLayout(self.widget_audio_opts)
        h_audio_opts.setContentsMargins(0, 0, 0, 0)
        h_audio_opts.addWidget(QLabel("Modo de audio:"))
        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.addItem("Reemplazar audio de los videos (o añadir si son mudos)", "replace")
        self.combo_audio_mode.addItem("Mezclar con el audio original de los videos", "mix")
        self.combo_audio_mode.addItem("Añadir como pista secundaria de audio", "add_track")
        self.combo_audio_mode.currentIndexChanged.connect(self._on_concat_audio_mode_changed)
        h_audio_opts.addWidget(self.combo_audio_mode, 1)

        self.chk_shortest = QCheckBox("Ajustar al final del video (cortar audio sobrante)")
        self.chk_shortest.setChecked(True)
        self.chk_shortest.setToolTip("Si el audio es más largo que el video unido, corta el audio para que el video no se quede congelado.")
        self.chk_shortest.stateChanged.connect(lambda _: self._update_command_preview())
        h_audio_opts.addWidget(self.chk_shortest)

        self.widget_audio_opts.setVisible(False)
        layout_audio.addWidget(self.widget_audio_opts)

        # Subpanel de ajuste de volúmenes para modo Mezcla en Concat
        self.widget_concat_mix_vol = QWidget()
        layout_mix_vol = QVBoxLayout(self.widget_concat_mix_vol)
        layout_mix_vol.setContentsMargins(8, 2, 8, 2)
        layout_mix_vol.setSpacing(6)

        # Fila 1: Audio Original
        h_vol_orig = QHBoxLayout()
        self.icon_vol_orig = QLabel()
        icon_orig = QIcon.fromTheme("audio-volume-high", self.style().standardIcon(QStyle.SP_MediaVolume))
        self.icon_vol_orig.setPixmap(icon_orig.pixmap(16, 16))
        lbl_text_orig = QLabel("Volumen audio original:")
        lbl_text_orig.setStyleSheet("font-weight: 500; font-size: 12px; color: #cbd5e1;")
        lbl_text_orig.setMinimumWidth(160)
        self.slider_vol_orig = QSlider(Qt.Horizontal)
        self.slider_vol_orig.setRange(0, 200)
        self.slider_vol_orig.setValue(100)
        self.slider_vol_orig.setTickPosition(QSlider.TicksBelow)
        self.slider_vol_orig.setTickInterval(50)
        self.slider_vol_orig.valueChanged.connect(self._on_vol_orig_changed)
        self.lbl_vol_orig_val = QLabel("100%")
        self.lbl_vol_orig_val.setFixedWidth(46)
        self.lbl_vol_orig_val.setStyleSheet("font-weight: bold; color: #38bdf8;")
        btn_reset_orig = QPushButton("100%")
        btn_reset_orig.setToolTip("Restablecer volumen original a 100%")
        btn_reset_orig.setStyleSheet("padding: 2px 4px; font-size: 11px; font-weight: bold; min-width: 54px;")
        btn_reset_orig.setFixedWidth(58)
        btn_reset_orig.setFixedHeight(24)
        btn_reset_orig.clicked.connect(lambda: self.slider_vol_orig.setValue(100))

        h_vol_orig.addWidget(self.icon_vol_orig)
        h_vol_orig.addWidget(lbl_text_orig)
        h_vol_orig.addWidget(self.slider_vol_orig, 1)
        h_vol_orig.addWidget(self.lbl_vol_orig_val)
        h_vol_orig.addWidget(btn_reset_orig)
        layout_mix_vol.addLayout(h_vol_orig)

        # Fila 2: Audio Agregado
        h_vol_added = QHBoxLayout()
        self.icon_vol_added = QLabel()
        icon_added = QIcon.fromTheme("audio-x-generic", self.style().standardIcon(QStyle.SP_MediaVolume))
        self.icon_vol_added.setPixmap(icon_added.pixmap(16, 16))
        lbl_text_added = QLabel("Volumen audio agregado:")
        lbl_text_added.setStyleSheet("font-weight: 500; font-size: 12px; color: #cbd5e1;")
        lbl_text_added.setMinimumWidth(160)
        self.slider_vol_added = QSlider(Qt.Horizontal)
        self.slider_vol_added.setRange(0, 200)
        self.slider_vol_added.setValue(100)
        self.slider_vol_added.setTickPosition(QSlider.TicksBelow)
        self.slider_vol_added.setTickInterval(50)
        self.slider_vol_added.valueChanged.connect(self._on_vol_added_changed)
        self.lbl_vol_added_val = QLabel("100%")
        self.lbl_vol_added_val.setFixedWidth(46)
        self.lbl_vol_added_val.setStyleSheet("font-weight: bold; color: #38bdf8;")
        btn_reset_added = QPushButton("100%")
        btn_reset_added.setToolTip("Restablecer volumen agregado a 100%")
        btn_reset_added.setStyleSheet("padding: 2px 4px; font-size: 11px; font-weight: bold; min-width: 54px;")
        btn_reset_added.setFixedWidth(58)
        btn_reset_added.setFixedHeight(24)
        btn_reset_added.clicked.connect(lambda: self.slider_vol_added.setValue(100))

        h_vol_added.addWidget(self.icon_vol_added)
        h_vol_added.addWidget(lbl_text_added)
        h_vol_added.addWidget(self.slider_vol_added, 1)
        h_vol_added.addWidget(self.lbl_vol_added_val)
        h_vol_added.addWidget(btn_reset_added)
        layout_mix_vol.addLayout(h_vol_added)

        self.widget_concat_mix_vol.setVisible(False)
        layout_audio.addWidget(self.widget_concat_mix_vol)

        lbl_audio_note = QLabel(
            "• El video se une a máxima velocidad sin pérdida (Stream Copy) y el audio se sincroniza en AAC de alta fidelidad."
        )
        lbl_audio_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_audio.addWidget(lbl_audio_note)
        layout_middle.addWidget(group_audio)

        # 2.3 Archivo Final Unificado
        group_out = QGroupBox("4. Archivo Final Unificado")
        layout_out = QVBoxLayout(group_out)

        h_sub_opt = QHBoxLayout()
        self.chk_use_base = QCheckBox("Guardar en Carpeta Base configurada")
        self.chk_use_base.setChecked(True)
        self.chk_use_base.stateChanged.connect(self._on_use_base_changed)

        self.chk_subfolder = QCheckBox("Crear subcarpeta con el nombre del video unificado")
        self.chk_subfolder.setChecked(config_manager.is_auto_suggest_subfolders())
        self.chk_subfolder.stateChanged.connect(self._update_output_suggestion)

        h_sub_opt.addWidget(self.chk_use_base)
        h_sub_opt.addWidget(self.chk_subfolder)
        h_sub_opt.addStretch()
        layout_out.addLayout(h_sub_opt)

        h_base_layout = QHBoxLayout()
        h_base_layout.setContentsMargins(0, 0, 0, 0)
        h_base_layout.setSpacing(6)
        self.icon_base_dir = QLabel()
        self.icon_base_dir.setPixmap(self.style().standardIcon(QStyle.SP_DirIcon).pixmap(16, 16))
        self.lbl_base_info = QLabel()
        self.lbl_base_info.setStyleSheet("color: #38bdf8; font-size: 11px; padding: 2px 0px;")
        h_base_layout.addWidget(self.icon_base_dir)
        h_base_layout.addWidget(self.lbl_base_info)
        h_base_layout.addStretch()
        layout_out.addLayout(h_base_layout)

        self.output_selector = FileSelector(
            placeholder="Ruta y nombre del video unificado...",
            is_save_dialog=True,
            file_filter="Videos (*.mp4 *.mkv *.mov *.avi);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.output_selector)
        layout_middle.addWidget(group_out)

        # 2.4 Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout_middle.addWidget(self.progress_widget)

        self.output_actions = OutputActionsWidget(file_label="Abrir Video Unido", parent=self)
        layout_middle.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Unir Segmentos", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_concat)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)

        h_btn_layout.addWidget(self.btn_run, 2)
        h_btn_layout.addWidget(self.btn_cancel, 1)
        layout_middle.addLayout(h_btn_layout)

        middle_scroll.setWidget(middle_container)

        # Divisor vertical interactivo entre la Lista de Segmentos y las Opciones
        self.content_splitter = QSplitter(Qt.Vertical, self)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(group_list)
        self.content_splitter.addWidget(middle_scroll)
        self.content_splitter.setSizes([200, 320])
        self.content_splitter.setStretchFactor(0, 2)
        self.content_splitter.setStretchFactor(1, 3)

        # Inicializar botones en fila única o dos filas según configuración inicial
        is_visible = config_manager.get_console_panel_visible()
        pos = config_manager.get_console_panel_position()
        self._update_tools_layout(single_row=(not is_visible) or (pos == "bottom"))

        # Configurar panel de consola y comando (ocultable / inferior o lateral)
        setup_tab_console_layout(self, self.content_splitter, "Comando FFmpeg a ejecutar:", wrap_in_scroll=False)
        self.update_base_dir_display()

    def _update_tools_layout(self, single_row: bool):
        """Organiza los botones en una sola fila (cuando la terminal no está visible o abajo) o en dos filas compactas (lateral)."""
        old_layout = self.tools_container.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            from PyQt5.QtWidgets import QWidget
            QWidget().setLayout(old_layout)

        if single_row:
            h_layout = QHBoxLayout(self.tools_container)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(6)
            h_layout.addWidget(self.btn_add_files)
            h_layout.addWidget(self.btn_add_folder)
            h_layout.addWidget(self.btn_up)
            h_layout.addWidget(self.btn_down)
            h_layout.addWidget(self.btn_remove)
            h_layout.addWidget(self.btn_clear)
        else:
            grid = QGridLayout(self.tools_container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            grid.addWidget(self.btn_add_files, 0, 0)
            grid.addWidget(self.btn_add_folder, 0, 1)
            grid.addWidget(self.btn_clear, 0, 2)
            grid.addWidget(self.btn_up, 1, 0)
            grid.addWidget(self.btn_down, 1, 1)
            grid.addWidget(self.btn_remove, 1, 2)

    def on_console_panel_settings_changed(self, pos: str, visible: bool):
        """Ajusta la fila de botones según la visibilidad y posición de la terminal."""
        single_row = (not visible) or (pos == "bottom")
        self._update_tools_layout(single_row)

    def _update_count(self):
        count = self.list_widget.count()
        self.lbl_count.setText(f"Total: {count} segmentos listados para unir")
        self._update_output_suggestion()

    def _on_use_base_changed(self):
        use_base = self.chk_use_base.isChecked()
        self.icon_base_dir.setVisible(use_base)
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_output_suggestion()

    def update_base_dir_display(self):
        base_dir = config_manager.get_base_output_dir()
        self.lbl_base_info.setText(
            f'<b>Carpeta Base actual:</b> <a href="{base_dir}" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">{base_dir}</a> '
            f'<span style="color: #94a3b8; font-size: 11px;">(Haz clic para abrir)</span>'
        )
        config_manager.make_clickable_folder_label(self.lbl_base_info, config_manager.get_base_output_dir)
        use_base = self.chk_use_base.isChecked()
        self.icon_base_dir.setVisible(use_base)
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_output_suggestion()

    def _insert_paths(self, paths: list):
        """Inserta archivos de video en la lista con ordenamiento natural y sin duplicados."""
        if not paths:
            return

        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

        valid_exts = {".mp4", ".mkv", ".avi", ".mov", ".ts", ".webm", ".m4v", ".flv", ".vob", ".wmv"}
        expanded = []
        for p in paths:
            p_str = str(p)
            if os.path.isdir(p_str):
                try:
                    for item in os.listdir(p_str):
                        full = os.path.join(p_str, item)
                        if os.path.isfile(full) and Path(full).suffix.lower() in valid_exts:
                            expanded.append(full)
                except Exception:
                    pass
            elif os.path.isfile(p_str):
                if Path(p_str).suffix.lower() in valid_exts or not Path(p_str).suffix:
                    expanded.append(p_str)

        existing = {self.list_widget.item(i).text() for i in range(self.list_widget.count())}
        added_count = 0
        for f in sorted(expanded, key=natural_sort_key):
            if f not in existing:
                self.list_widget.addItem(f)
                existing.add(f)
                added_count += 1

        if added_count > 0:
            self._update_count()

    def _update_output_suggestion(self):
        count = self.list_widget.count()
        if count == 0:
            self.output_selector.set_path("")
            self.cmd_preview.set_command("")
            return

        first_item = self.list_widget.item(0)
        if not first_item:
            self.cmd_preview.set_command("")
            return

        first_path = first_item.text()
        p = Path(first_path)

        # Limpiar sufijos típicos de fragmentación (_part_XXX, _segment_XXX, etc.) para que el video resultante
        # y la subcarpeta sugerida tengan un nombre limpio (ej. "video_unido.mp4" y no "video_part_000_unido.mp4")
        import re
        clean_stem = re.sub(r'(_part_\d+|_segment_\d+|_fotograma_\d+|\bpart\d+|\bseg\d+)$', '', p.stem, flags=re.IGNORECASE).rstrip('_- ')
        if not clean_stem:
            clean_stem = p.stem
        clean_path = str(p.parent / f"{clean_stem}{p.suffix}")

        if self.chk_use_base.isChecked():
            suggested = config_manager.suggest_output_path(
                clean_path,
                suffix="_unido",
                extension=p.suffix or ".mp4",
                override_auto_subfolders=self.chk_subfolder.isChecked()
            )
        else:
            suggested = str(p.parent / f"{clean_stem}_unido{p.suffix}")

        self.output_selector.set_path(suggested)
        self._update_command_preview()

    def _on_anti_stutter_toggled(self, checked: bool):
        self.widget_anti_stutter_opts.setVisible(checked)
        if checked:
            # La eliminación de micro-stutter requiere recodificación
            if self.combo_mode.currentData() == "copy":
                self.combo_mode.setCurrentIndex(1)  # "reencode"
        self._update_command_preview()

    def _on_stutter_mode_changed(self):
        is_manual = self.radio_stutter_manual.isChecked()
        self.spin_drop_frames.setEnabled(is_manual)
        self._update_command_preview()

    def _on_mode_combo_changed(self, index: int):
        # Si el usuario selecciona Stream Copy con anti-stutter activo, desactivar anti-stutter
        if self.combo_mode.currentData() == "copy" and hasattr(self, "chk_anti_stutter") and self.chk_anti_stutter.isChecked():
            self.chk_anti_stutter.blockSignals(True)
            self.chk_anti_stutter.setChecked(False)
            self.widget_anti_stutter_opts.setVisible(False)
            self.chk_anti_stutter.blockSignals(False)
        self._update_command_preview()

    def _on_vol_orig_changed(self, val: int):
        self.lbl_vol_orig_val.setText(f"{val}%")
        self._update_command_preview()

    def _on_vol_added_changed(self, val: int):
        self.lbl_vol_added_val.setText(f"{val}%")
        self._update_command_preview()

    def _on_concat_audio_mode_changed(self):
        has_file = bool(self.audio_selector.get_path().strip())
        is_mix = has_file and (self.combo_audio_mode.currentData() == "mix")
        if hasattr(self, "widget_concat_mix_vol"):
            self.widget_concat_mix_vol.setVisible(is_mix)
        self._update_command_preview()

    def _on_audio_file_changed(self, path: str):
        has_file = bool(path and path.strip())
        self.btn_clear_audio.setEnabled(has_file)
        self.widget_audio_opts.setVisible(has_file)
        is_mix = has_file and (self.combo_audio_mode.currentData() == "mix")
        if hasattr(self, "widget_concat_mix_vol"):
            self.widget_concat_mix_vol.setVisible(is_mix)
        self._update_command_preview()

    def _clear_audio(self):
        self.audio_selector.set_path("")
        self._on_audio_file_changed("")

    def _update_command_preview(self):
        count = self.list_widget.count()
        out_video = self.output_selector.get_path()
        if count < 2:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        target_out = out_video if out_video else "video_unido.mp4"
        mode = self.combo_mode.currentData() if hasattr(self, "combo_mode") else "copy"

        audio_path = self.audio_selector.get_path() if hasattr(self, "audio_selector") else ""
        audio_mode = self.combo_audio_mode.currentData() if hasattr(self, "combo_audio_mode") else "replace"
        shortest = self.chk_shortest.isChecked() if hasattr(self, "chk_shortest") else True

        anti_stutter = self.chk_anti_stutter.isChecked() if hasattr(self, "chk_anti_stutter") else False
        stutter_mode = "manual" if (anti_stutter and hasattr(self, "radio_stutter_manual") and self.radio_stutter_manual.isChecked()) else "auto"
        drop_frames = self.spin_drop_frames.value() if hasattr(self, "spin_drop_frames") else 1
        files = [self.list_widget.item(i).text() for i in range(count)] if count >= 2 else []

        vol_orig = (self.slider_vol_orig.value() / 100.0) if hasattr(self, "slider_vol_orig") else 1.0
        vol_added = (self.slider_vol_added.value() / 100.0) if hasattr(self, "slider_vol_added") else 1.0

        try:
            cmd = ffmpeg_core.build_concat_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                list_file_path="/ruta/lista_segmentos.txt",
                output_file=target_out,
                mode=mode,
                audio_file=audio_path if audio_path else None,
                audio_mode=audio_mode,
                shortest=shortest,
                anti_stutter=anti_stutter,
                stutter_mode=stutter_mode,
                drop_start_frames=drop_frames,
                file_paths=files,
                volume_orig=vol_orig,
                volume_added=vol_added
            )
            self.cmd_preview.set_command(cmd)
        except Exception as e:
            self.cmd_preview.set_command(f"# Vista previa no disponible: {e}")

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar segmentos de video", "",
            "Videos (*.mp4 *.mkv *.avi *.mov *.ts *.webm *.m4v);;Todos (*.*)"
        )
        if files:
            self._insert_paths(files)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta con segmentos")
        if folder:
            valid_exts = {".mp4", ".mkv", ".avi", ".mov", ".ts", ".webm", ".m4v", ".flv", ".vob", ".wmv"}
            entries = []
            try:
                for item in os.listdir(folder):
                    full_p = os.path.join(folder, item)
                    if os.path.isfile(full_p) and Path(full_p).suffix.lower() in valid_exts:
                        entries.append(full_p)
            except Exception as e:
                QMessageBox.warning(self, "Error al leer carpeta", f"No se pudo acceder a la carpeta seleccionada:\n{e}")
                return

            if not entries:
                QMessageBox.information(
                    self,
                    "Sin segmentos compatibles",
                    "No se encontraron archivos de video compatibles (.mp4, .mkv, .avi, .mov, etc.) en la carpeta seleccionada."
                )
                return

            self._insert_paths(entries)

    def _move_up(self):
        curr_row = self.list_widget.currentRow()
        if curr_row > 0:
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(curr_row - 1, item)
            self.list_widget.setCurrentRow(curr_row - 1)

    def _move_down(self):
        curr_row = self.list_widget.currentRow()
        if curr_row < self.list_widget.count() - 1 and curr_row >= 0:
            item = self.list_widget.takeItem(curr_row)
            self.list_widget.insertItem(curr_row + 1, item)
            self.list_widget.setCurrentRow(curr_row + 1)

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_count()

    def _clear_list(self):
        self.list_widget.clear()
        self._update_count()

    def _start_concat(self):
        count = self.list_widget.count()
        if count < 2:
            QMessageBox.warning(self, "Segmentos insuficientes", "Añada al menos 2 segmentos para unir.")
            return

        out_file = self.output_selector.get_path()
        if not out_file:
            QMessageBox.warning(self, "Ruta de salida", "Especifique el archivo resultante.")
            return

        # Crear carpeta de destino automáticamente si no existe en disco
        out_dir = os.path.dirname(out_file)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        # Recoger rutas en orden
        files = [self.list_widget.item(i).text() for i in range(count)]

        # Crear archivo temporal para concat demuxer
        temp_dir = out_dir if out_dir and os.path.isdir(out_dir) else tempfile.gettempdir()
        self.temp_list_file = os.path.join(temp_dir, f"concat_list_{os.getpid()}.txt")
        ffmpeg_core.create_concat_list_file(files, self.temp_list_file)

        # Validar archivo de audio opcional si fue especificado
        audio_file = self.audio_selector.get_path() if hasattr(self, "audio_selector") else ""
        if audio_file and not os.path.isfile(audio_file):
            QMessageBox.warning(self, "Archivo de audio no encontrado", f"El archivo de audio especificado no existe:\n{audio_file}")
            return

        mode = self.combo_mode.currentData()
        audio_mode = self.combo_audio_mode.currentData() if hasattr(self, "combo_audio_mode") else "replace"
        shortest = self.chk_shortest.isChecked() if hasattr(self, "chk_shortest") else True

        anti_stutter = self.chk_anti_stutter.isChecked() if hasattr(self, "chk_anti_stutter") else False
        stutter_mode = "manual" if (anti_stutter and hasattr(self, "radio_stutter_manual") and self.radio_stutter_manual.isChecked()) else "auto"
        drop_frames = self.spin_drop_frames.value() if hasattr(self, "spin_drop_frames") else 1

        vol_orig = (self.slider_vol_orig.value() / 100.0) if hasattr(self, "slider_vol_orig") else 1.0
        vol_added = (self.slider_vol_added.value() / 100.0) if hasattr(self, "slider_vol_added") else 1.0

        cmd = ffmpeg_core.build_concat_command(
            ffmpeg_path=ffmpeg_path,
            list_file_path=self.temp_list_file,
            output_file=out_file,
            mode=mode,
            audio_file=audio_file if audio_file else None,
            audio_mode=audio_mode,
            shortest=shortest,
            anti_stutter=anti_stutter,
            stutter_mode=stutter_mode,
            drop_start_frames=drop_frames,
            file_paths=files,
            volume_orig=vol_orig,
            volume_added=vol_added
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=0.0, output_path=out_file)
        self.worker.progress_signal.connect(self.progress_widget.set_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()

    def _on_finished(self, success: bool, message: str, out_path: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        # Limpiar archivo temporal de lista
        if self.temp_list_file and os.path.isfile(self.temp_list_file):
            try:
                os.remove(self.temp_list_file)
            except Exception:
                pass
            self.temp_list_file = None

        if success:
            self.output_actions.show_output(out_path)

            # Cuadro informativo interactivo con opciones de abrir
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Videos Unidos")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>{message}</b></p>"
                f"<p><b>Archivo resultante:</b><br><span style='color: #38bdf8;'>{out_path}</span></p>"
                f"</div>"
            )
            msg_box.setIcon(QMessageBox.Information)
            btn_play = msg_box.addButton("Abrir Video", QMessageBox.ActionRole)
            btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            btn_folder = msg_box.addButton("Abrir Carpeta", QMessageBox.ActionRole)
            btn_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            msg_box.addButton("Aceptar", QMessageBox.AcceptRole)
            msg_box.exec_()

            clicked = msg_box.clickedButton()
            if clicked == btn_play:
                config_manager.open_path_in_os(out_path, is_directory=False)
            elif clicked == btn_folder:
                config_manager.open_path_in_os(out_path, is_directory=True)
        else:
            QMessageBox.warning(self, "Atención", message)
