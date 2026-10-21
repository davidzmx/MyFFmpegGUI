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
    QSplitter, QSizePolicy
)
from PyQt5.QtCore import Qt
from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget
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
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)

        # Divisor vertical interactivo (Splitter) para permitir redimensionar la lista de segmentos
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)

        # 1. Lista interactiva de segmentos (Panel superior)
        group_list = QGroupBox("1. Lista de Segmentos a Unir (Orden Secuencial - Ajustable arrastrando la barra divisoria)")
        layout_list = QVBoxLayout(group_list)
        layout_list.setSpacing(8)

        self.list_widget = SegmentListWidget(on_files_dropped=self._insert_paths, parent=self)
        self.list_widget.setMinimumHeight(160)
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_list.addWidget(self.list_widget)

        # Botones de gestión de lista
        h_tools = QHBoxLayout()
        btn_add_files = QPushButton("Añadir Archivos...")
        btn_add_files.clicked.connect(self._add_files)

        btn_add_folder = QPushButton("Añadir Carpeta...")
        btn_add_folder.clicked.connect(self._add_folder)

        btn_up = QPushButton("▲ Subir")
        btn_up.clicked.connect(self._move_up)

        btn_down = QPushButton("▼ Bajar")
        btn_down.clicked.connect(self._move_down)

        btn_remove = QPushButton("Eliminar")
        btn_remove.clicked.connect(self._remove_selected)

        btn_clear = QPushButton("Limpiar Todo")
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

        # Contenedor inferior para opciones, comandos y consola
        bottom_panel = QWidget(self)
        layout_bottom = QVBoxLayout(bottom_panel)
        layout_bottom.setContentsMargins(0, 0, 0, 0)
        layout_bottom.setSpacing(10)

        # 2. Configuración de unión
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
        layout_bottom.addWidget(group_opts)

        # 3. Archivo Resultante
        group_out = QGroupBox("3. Archivo Final Unificado")
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

        self.lbl_base_info = QLabel()
        self.lbl_base_info.setStyleSheet("color: #38bdf8; font-size: 11px; padding: 2px 0px;")
        layout_out.addWidget(self.lbl_base_info)

        self.output_selector = FileSelector(
            placeholder="Ruta y nombre del video unificado...",
            is_save_dialog=True,
            file_filter="Videos (*.mp4 *.mkv *.mov *.avi);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.output_selector)
        layout_bottom.addWidget(group_out)

        # 4. Vista Previa del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout_bottom.addWidget(self.cmd_preview)

        # 5. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout_bottom.addWidget(self.progress_widget)

        # 5.5 Acciones post-generación (Abrir Video / Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Video Unido", parent=self)
        layout_bottom.addWidget(self.output_actions)

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
        layout_bottom.addLayout(h_btn_layout)

        # 6. Consola
        self.log_console = LogConsole(self)
        layout_bottom.addWidget(self.log_console, 1)

        self.splitter.addWidget(bottom_panel)

        # Proporciones iniciales: 250px para la lista, 450px para el panel inferior
        self.splitter.setSizes([250, 450])
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        layout.addWidget(self.splitter)

        self.update_base_dir_display()

    def _update_count(self):
        count = self.list_widget.count()
        self.lbl_count.setText(f"Total: {count} segmentos listados para unir")
        self._update_output_suggestion()

    def _on_use_base_changed(self):
        use_base = self.chk_use_base.isChecked()
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_output_suggestion()

    def update_base_dir_display(self):
        base_dir = config_manager.get_base_output_dir()
        self.lbl_base_info.setText(
            f'📁 <b>Carpeta Base actual:</b> <a href="{base_dir}" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">{base_dir}</a> '
            f'<span style="color: #94a3b8; font-size: 11px;">(Haz clic para abrir)</span>'
        )
        config_manager.make_clickable_folder_label(self.lbl_base_info, config_manager.get_base_output_dir)
        use_base = self.chk_use_base.isChecked()
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

        if self.chk_use_base.isChecked():
            suggested = config_manager.suggest_output_path(
                first_path,
                suffix="_unido",
                extension=p.suffix or ".mp4",
                override_auto_subfolders=self.chk_subfolder.isChecked()
            )
        else:
            suggested = str(p.parent / f"{p.stem}_unido{p.suffix}")

        self.output_selector.set_path(suggested)
        self._update_command_preview()

    def _update_command_preview(self):
        count = self.list_widget.count()
        out_video = self.output_selector.get_path()
        if count < 2:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        target_out = out_video if out_video else "video_unido.mp4"
        mode = self.combo_mode.currentData() if hasattr(self, "combo_mode") else "copy"
        try:
            cmd = ffmpeg_core.build_concat_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                list_file_path="/ruta/lista_segmentos.txt",
                output_file=target_out,
                mode=mode
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

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        # Recoger rutas en orden
        files = [self.list_widget.item(i).text() for i in range(count)]

        # Crear archivo temporal para concat demuxer
        temp_dir = os.path.dirname(out_file) if os.path.isdir(os.path.dirname(out_file)) else tempfile.gettempdir()
        self.temp_list_file = os.path.join(temp_dir, f"concat_list_{os.getpid()}.txt")
        ffmpeg_core.create_concat_list_file(files, self.temp_list_file)

        mode = self.combo_mode.currentData()
        cmd = ffmpeg_core.build_concat_command(
            ffmpeg_path=ffmpeg_path,
            list_file_path=self.temp_list_file,
            output_file=out_file,
            mode=mode
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
            msg_box.setText(f"{message}\n\n<b>Archivo resultante:</b>\n{out_path}")
            msg_box.setIcon(QMessageBox.Information)
            btn_play = msg_box.addButton("▶ Abrir Video", QMessageBox.ActionRole)
            btn_folder = msg_box.addButton("📁 Abrir Carpeta", QMessageBox.ActionRole)
            msg_box.addButton("Aceptar", QMessageBox.AcceptRole)
            msg_box.exec_()

            clicked = msg_box.clickedButton()
            if clicked == btn_play:
                config_manager.open_path_in_os(out_path, is_directory=False)
            elif clicked == btn_folder:
                config_manager.open_path_in_os(out_path, is_directory=True)
        else:
            QMessageBox.warning(self, "Atención", message)
