#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Extraer fotogramas de un video sin pérdida de resolución ni calidad
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QCheckBox, QLineEdit, QDoubleSpinBox, QStyle
)
from ui.widgets import FileSelector, FolderSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class TabExtractFrames(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.media_duration = 0.0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Video de Entrada
        group_input = QGroupBox("1. Video de Entrada")
        layout_input = QVBoxLayout(group_input)

        self.input_selector = FileSelector(
            placeholder="Seleccione el video del cual extraer fotogramas...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.ts);;Todos (*.*)"
        )
        self.input_selector.file_selected.connect(self._on_file_selected)

        self.lbl_info = QLabel("Duración: --:--:-- | Resolución: -- x -- | FPS: --")
        self.lbl_info.setObjectName("lbl_meta")

        layout_input.addWidget(self.input_selector)
        layout_input.addWidget(self.lbl_info)
        layout.addWidget(group_input)

        # 2. Configuración de extracción
        group_opts = QGroupBox("2. Formato y Modo de Extracción (Sin Pérdida)")
        layout_opts = QVBoxLayout(group_opts)

        h_row1 = QHBoxLayout()
        lbl_fmt = QLabel("Formato de imagen:")
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItem("PNG - 100% Sin Pérdida (Recomendado)", "png")
        self.combo_fmt.addItem("TIFF - Sin Pérdida Profesional", "tiff")
        self.combo_fmt.addItem("WebP - Sin Pérdida (Lossless)", "webp")
        self.combo_fmt.addItem("JPEG - Calidad Máxima (q:v 1)", "jpg")
        self.combo_fmt.currentIndexChanged.connect(self._update_pattern_placeholder)

        lbl_mode = QLabel("Frecuencia:")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Todos los fotogramas originales (Completo)", "all")
        self.combo_mode.addItem("1 fotograma por segundo (1 FPS)", "1fps")
        self.combo_mode.addItem("Solo Fotogramas Clave (Keyframes / I-Frames)", "keyframes")
        self.combo_mode.addItem("FPS personalizado...", "custom_fps")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        self.spin_fps = QDoubleSpinBox()
        self.spin_fps.setRange(0.01, 240.0)
        self.spin_fps.setValue(1.0)
        self.spin_fps.setSingleStep(0.5)
        self.spin_fps.setEnabled(False)

        h_row1.addWidget(lbl_fmt)
        h_row1.addWidget(self.combo_fmt, 1)
        h_row1.addWidget(lbl_mode)
        h_row1.addWidget(self.combo_mode, 1)
        h_row1.addWidget(self.spin_fps)
        layout_opts.addLayout(h_row1)

        # Rango de tiempo
        h_row2 = QHBoxLayout()
        self.chk_range = QCheckBox("Limitar a rango de tiempo:")
        self.chk_range.stateChanged.connect(self._toggle_range)

        self.edit_start = QLineEdit("00:00:00")
        self.edit_start.setPlaceholderText("Inicio (HH:MM:SS)")
        self.edit_start.setEnabled(False)

        self.edit_duration = QLineEdit("10")
        self.edit_duration.setPlaceholderText("Duración en segundos")
        self.edit_duration.setEnabled(False)

        h_row2.addWidget(self.chk_range)
        h_row2.addWidget(QLabel("Desde:"))
        h_row2.addWidget(self.edit_start)
        h_row2.addWidget(QLabel("Duración (seg):"))
        h_row2.addWidget(self.edit_duration)
        layout_opts.addLayout(h_row2)

        layout.addWidget(group_opts)

        # 3. Carpeta de destino
        group_out = QGroupBox("3. Carpeta de Destino de los Fotogramas")
        layout_out = QVBoxLayout(group_out)

        h_sub_opt = QHBoxLayout()
        self.chk_use_base = QCheckBox("Guardar en Carpeta Base configurada")
        self.chk_use_base.setChecked(True)
        self.chk_use_base.stateChanged.connect(self._on_use_base_changed)

        self.chk_subfolder = QCheckBox("Crear subcarpeta con el nombre del archivo")
        self.chk_subfolder.setChecked(config_manager.is_auto_suggest_subfolders())
        self.chk_subfolder.stateChanged.connect(self._update_folder_suggestion)

        h_sub_opt.addWidget(self.chk_use_base)
        h_sub_opt.addWidget(self.chk_subfolder)
        h_sub_opt.addStretch()
        layout_out.addLayout(h_sub_opt)

        h_base = QHBoxLayout()
        h_base.setContentsMargins(0, 0, 0, 0)
        h_base.setSpacing(6)
        self.icon_base_dir = QLabel()
        self.icon_base_dir.setPixmap(self.style().standardIcon(QStyle.SP_DirIcon).pixmap(16, 16))
        self.lbl_base_info = QLabel()
        self.lbl_base_info.setStyleSheet("color: #38bdf8; font-size: 11px; padding: 2px 0px;")
        h_base.addWidget(self.icon_base_dir)
        h_base.addWidget(self.lbl_base_info)
        h_base.addStretch()
        layout_out.addLayout(h_base)

        self.folder_selector = FolderSelector("Seleccione la carpeta donde se guardarán las imágenes...")
        self.folder_selector.folder_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.folder_selector)

        h_pattern = QHBoxLayout()
        h_pattern.addWidget(QLabel("Patrón de nombres:"))
        self.edit_pattern = QLineEdit("frame_%06d.png")
        self.edit_pattern.textChanged.connect(lambda _: self._update_command_preview())
        h_pattern.addWidget(self.edit_pattern, 1)
        layout_out.addLayout(h_pattern)

        layout.addWidget(group_out)

        # 4. Vista Previa del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout.addWidget(self.cmd_preview)

        # 5. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout.addWidget(self.progress_widget)

        self.output_actions = OutputActionsWidget(file_label="Abrir Carpeta", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Extraer Fotogramas", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_extraction)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)

        h_btn_layout.addWidget(self.btn_run, 2)
        h_btn_layout.addWidget(self.btn_cancel, 1)
        layout.addLayout(h_btn_layout)

        # 6. Consola
        self.log_console = LogConsole(self)
        layout.addWidget(self.log_console, 1)

        # Conectar cambios de opciones a la vista previa del comando
        self.combo_fmt.currentIndexChanged.connect(lambda _: self._update_command_preview())
        self.combo_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())
        self.spin_fps.valueChanged.connect(lambda _: self._update_command_preview())
        self.chk_range.stateChanged.connect(lambda _: self._update_command_preview())
        self.edit_start.textChanged.connect(lambda _: self._update_command_preview())
        self.edit_duration.textChanged.connect(lambda _: self._update_command_preview())

        self.update_base_dir_display()

    def _on_file_selected(self, path: str):
        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Resolución: -- x -- | FPS: --")
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info["duration"]

        self.lbl_info.setText(
            f"Duración: {info['duration_str']} | Resolución: {info['width']}x{info['height']} | "
            f"Códec: {(info['video_codec'] or 'N/A').upper()} | FPS: {info['fps']}"
        )
        self._update_folder_suggestion()

    def _on_use_base_changed(self):
        use_base = self.chk_use_base.isChecked()
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_folder_suggestion()

    def update_base_dir_display(self):
        base_dir = config_manager.get_base_output_dir()
        self.lbl_base_info.setText(
            f"<b>Carpeta Base actual:</b> <a href='base' style='color: #38bdf8; text-decoration: underline;'>{base_dir}</a> "
            f"<span style='color: #94a3b8; font-size: 10px;'>(clic para abrir)</span>"
        )
        config_manager.make_clickable_folder_label(self.lbl_base_info, config_manager.get_base_output_dir)
        use_base = self.chk_use_base.isChecked()
        self.icon_base_dir.setVisible(use_base)
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_folder_suggestion()

    def _update_folder_suggestion(self):
        path = self.input_selector.get_path()
        if not path:
            self.cmd_preview.set_command("")
            return

        if self.chk_use_base.isChecked():
            suggested = config_manager.suggest_output_path(
                path,
                suffix="_fotogramas",
                is_destination_folder=True,
                override_auto_subfolders=self.chk_subfolder.isChecked()
            )
        else:
            p = Path(path)
            suggested = str(p.parent / f"{p.stem}_fotogramas")

        self.folder_selector.set_path(suggested)
        self._update_command_preview()

    def _update_command_preview(self):
        in_path = self.input_selector.get_path()
        out_folder = self.folder_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        fmt = self.combo_fmt.currentData() or "png"
        fps_mode = self.combo_mode.currentData()
        custom_fps = self.spin_fps.value()
        start_time = self.edit_start.text().strip() if self.chk_range.isChecked() else None
        duration = self.edit_duration.text().strip() if self.chk_range.isChecked() else None

        pattern = self.edit_pattern.text().strip() or f"frame_%06d.{fmt}"
        target_folder = out_folder if out_folder else f"{Path(in_path).stem}_fotogramas"
        output_pattern_path = os.path.join(target_folder, pattern)

        cmd = ffmpeg_core.build_extract_frames_command(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            input_file=in_path,
            output_pattern=output_pattern_path,
            fmt=fmt,
            fps_mode=fps_mode,
            custom_fps=custom_fps,
            start_time=start_time,
            duration=duration
        )
        self.cmd_preview.set_command(cmd)

    def _on_mode_changed(self):
        is_custom = self.combo_mode.currentData() == "custom_fps"
        self.spin_fps.setEnabled(is_custom)
        self._update_command_preview()

    def _toggle_range(self):
        enabled = self.chk_range.isChecked()
        self.edit_start.setEnabled(enabled)
        self.edit_duration.setEnabled(enabled)
        self._update_command_preview()

    def _update_pattern_placeholder(self):
        ext = self.combo_fmt.currentData()
        self.edit_pattern.setText(f"frame_%06d.{ext}")
        self._update_command_preview()

    def _start_extraction(self):
        in_path = self.input_selector.get_path()
        out_folder = self.folder_selector.get_path()

        if not in_path or not os.path.isfile(in_path):
            QMessageBox.warning(self, "Video inválido", "Seleccione un archivo de video válido.")
            return

        if not out_folder:
            QMessageBox.warning(self, "Carpeta de destino", "Seleccione una carpeta de destino para guardar los fotogramas.")
            return

        os.makedirs(out_folder, exist_ok=True)

        pattern = self.edit_pattern.text().strip()
        if not pattern:
            ext = self.combo_fmt.currentData()
            pattern = f"frame_%06d.{ext}"

        output_pattern_path = os.path.join(out_folder, pattern)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        fmt = self.combo_fmt.currentData()
        fps_mode = self.combo_mode.currentData()
        custom_fps = self.spin_fps.value()

        start_time = self.edit_start.text().strip() if self.chk_range.isChecked() else None
        duration = self.edit_duration.text().strip() if self.chk_range.isChecked() else None

        cmd = ffmpeg_core.build_extract_frames_command(
            ffmpeg_path=ffmpeg_path,
            input_file=in_path,
            output_pattern=output_pattern_path,
            fmt=fmt,
            fps_mode=fps_mode,
            custom_fps=custom_fps,
            start_time=start_time,
            duration=duration
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        calc_duration = float(duration) if duration and duration.replace(".", "", 1).isdigit() else self.media_duration

        self.worker = FFmpegWorker(cmd, total_duration=calc_duration, output_path=out_folder)
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

        if success:
            self.output_actions.show_output(out_path, is_folder_only=True, custom_status="Fotogramas extraídos exitosamente:")
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Fotogramas Extraídos")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>{message}</b></p>"
                f"<p><b>Carpeta destino:</b><br><span style='color: #38bdf8;'>{out_path}</span></p>"
                f"</div>"
            )
            msg_box.setIcon(QMessageBox.Information)
            btn_folder = msg_box.addButton("Abrir Carpeta", QMessageBox.ActionRole)
            btn_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            msg_box.addButton("Aceptar", QMessageBox.AcceptRole)
            msg_box.exec_()

            if msg_box.clickedButton() == btn_folder:
                config_manager.open_path_in_os(out_path, is_directory=True)
        else:
            QMessageBox.warning(self, "Atención", message)
