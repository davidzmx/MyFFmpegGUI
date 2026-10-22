#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Unir / Concatenar segmentos de video sin pérdida de calidad (Stream Copy)
"""

import os
import tempfile
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QListWidget, QFileDialog, QCheckBox,
    QSplitter, QSizePolicy, QScrollArea, QFrame, QStyle
)
from PyQt5.QtCore import Qt
from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget,
    ConsoleOutputPanel
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

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(6, 6, 6, 6)

        # Divisor vertical interactivo de 3 secciones (Lista, Controles, Terminal)
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)

        # 1. Lista interactiva de segmentos (Panel superior - Redimensionable)
        group_list = QGroupBox("1. Lista de Segmentos a Unir (Orden Secuencial - Redimensionable arrastrando barra divisoria)")
        group_list.setMinimumHeight(110)
        layout_list = QVBoxLayout(group_list)
        layout_list.setSpacing(8)

        self.list_widget = SegmentListWidget(on_files_dropped=self._insert_paths, parent=self)
        self.list_widget.setMinimumHeight(60)
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_list.addWidget(self.list_widget, 1)

        # Botones de gestión de lista
        h_tools = QHBoxLayout()
        btn_add_files = QPushButton("Añadir Archivos...")
        btn_add_files.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        btn_add_files.clicked.connect(self._add_files)

        btn_add_folder = QPushButton("Añadir Carpeta...")
        btn_add_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        btn_add_folder.clicked.connect(self._add_folder)

        btn_up = QPushButton("Subir")
        btn_up.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        btn_up.clicked.connect(self._move_up)

        btn_down = QPushButton("Bajar")
        btn_down.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        btn_down.clicked.connect(self._move_down)

        btn_remove = QPushButton("Eliminar")
        btn_remove.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        btn_remove.clicked.connect(self._remove_selected)

        btn_clear = QPushButton("Limpiar Todo")
        btn_clear.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        btn_clear.clicked.connect(self._clear_list)

        h_tools.addWidget(btn_add_files)
        h_tools.addWidget(btn_add_folder)
        h_tools.addWidget(btn_up)
        h_tools.addWidget(btn_down)
        h_tools.addWidget(btn_remove)
        h_tools.addWidget(btn_clear)
        layout_list.addLayout(h_tools)

        self.lbl_count = QLabel("Total: 0 segmentos seleccionados")
        self.lbl_count.setObjectName("lbl_meta")
        layout_list.addWidget(self.lbl_count)

        self.splitter.addWidget(group_list)

        # 2. Panel Central: Opciones, Salida, Previa y Botones (Con scroll interno fluido)
        middle_scroll = QScrollArea(self)
        middle_scroll.setWidgetResizable(True)
        middle_scroll.setFrameShape(QFrame.NoFrame)
        middle_scroll.setMinimumHeight(120)

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
        self.combo_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())
        h_mode.addWidget(self.combo_mode, 1)
        layout_opts.addLayout(h_mode)

        lbl_note = QLabel(
            "• Stream Copy une los archivos a la velocidad de lectura del disco sin alterar un solo píxel.\n"
            "• Requiere que todos los segmentos provengan de la misma fuente o tengan códecs compatibles."
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
        self.combo_audio_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())
        h_audio_opts.addWidget(self.combo_audio_mode, 1)

        self.chk_shortest = QCheckBox("Ajustar al final del video (cortar audio sobrante)")
        self.chk_shortest.setChecked(True)
        self.chk_shortest.setToolTip("Si el audio es más largo que el video unido, corta el audio para que el video no se quede congelado.")
        self.chk_shortest.stateChanged.connect(lambda _: self._update_command_preview())
        h_audio_opts.addWidget(self.chk_shortest)

        self.widget_audio_opts.setVisible(False)
        layout_audio.addWidget(self.widget_audio_opts)

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
        self.splitter.addWidget(middle_scroll)

        # 3. Panel de Consola y Comando FFmpeg (ocultable / inferior o lateral)
        self.console_panel = ConsoleOutputPanel("Comando FFmpeg a ejecutar:", self)
        self.cmd_preview = self.console_panel.cmd_preview
        self.log_console = self.console_panel.log_console
        self.splitter.addWidget(self.console_panel)
        self.splitter_console = self.splitter

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)

        layout.addWidget(self.splitter, 1)

        self.btn_show_console = QPushButton("🖥️ Mostrar Comando FFmpeg y Terminal de Salida", self)
        self.btn_show_console.setObjectName("btn_show_console")
        self.btn_show_console.setCursor(Qt.PointingHandCursor)
        self.btn_show_console.setFixedHeight(28)
        self.btn_show_console.setStyleSheet("""
            QPushButton#btn_show_console {
                background-color: #1a1b2b;
                color: #38bdf8;
                border: 1px dashed #3b4261;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#btn_show_console:hover {
                background-color: #23253b;
                color: #7dd3fc;
                border: 1px solid #38bdf8;
            }
        """)
        layout.addWidget(self.btn_show_console)

        def _sync_with_main_window(pos=None, visible=None):
            main_win = self.window()
            if main_win and hasattr(main_win, "sync_console_panels"):
                main_win.sync_console_panels(pos=pos, visible=visible)

        def _on_hide():
            config_manager.set_console_panel_visible(False)
            self.apply_console_panel_settings(visible=False)
            _sync_with_main_window(visible=False)

        def _on_show():
            config_manager.set_console_panel_visible(True)
            self.apply_console_panel_settings(visible=True)
            _sync_with_main_window(visible=True)

        def _on_toggle_pos():
            curr_pos = config_manager.get_console_panel_position()
            new_pos = "side" if curr_pos == "bottom" else "bottom"
            config_manager.set_console_panel_position(new_pos)
            self.apply_console_panel_settings(pos=new_pos)
            _sync_with_main_window(pos=new_pos)

        self.console_panel.hide_requested.connect(_on_hide)
        self.btn_show_console.clicked.connect(_on_show)
        self.console_panel.toggle_position_requested.connect(_on_toggle_pos)

        def apply_settings(pos: str = None, visible: bool = None):
            if pos is None:
                pos = config_manager.get_console_panel_position()
            if visible is None:
                visible = config_manager.get_console_panel_visible()

            if pos == "side":
                self.splitter.setOrientation(Qt.Horizontal)
                self.splitter.setSizes([260, 380, 440])
                self.splitter.setStretchFactor(0, 2)
                self.splitter.setStretchFactor(1, 3)
                self.splitter.setStretchFactor(2, 3)
            else:
                self.splitter.setOrientation(Qt.Vertical)
                self.splitter.setSizes([200, 280, 200])
                self.splitter.setStretchFactor(0, 3)
                self.splitter.setStretchFactor(1, 4)
                self.splitter.setStretchFactor(2, 3)

            self.console_panel.set_position_mode(pos)
            self.console_panel.setVisible(bool(visible))
            self.btn_show_console.setVisible(not bool(visible))

        self.apply_console_panel_settings = apply_settings
        apply_settings()

        self.update_base_dir_display()

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

    def _on_audio_file_changed(self, path: str):
        has_file = bool(path and path.strip())
        self.btn_clear_audio.setEnabled(has_file)
        self.widget_audio_opts.setVisible(has_file)
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

        try:
            cmd = ffmpeg_core.build_concat_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                list_file_path="/ruta/lista_segmentos.txt",
                output_file=target_out,
                mode=mode,
                audio_file=audio_path if audio_path else None,
                audio_mode=audio_mode,
                shortest=shortest
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

        cmd = ffmpeg_core.build_concat_command(
            ffmpeg_path=ffmpeg_path,
            list_file_path=self.temp_list_file,
            output_file=out_file,
            mode=mode,
            audio_file=audio_file if audio_file else None,
            audio_mode=audio_mode,
            shortest=shortest
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
