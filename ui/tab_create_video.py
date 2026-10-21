#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Crear video a partir de fotogramas (secuencia de imágenes) sin pérdida de calidad
"""

import os
import glob
import re
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QDoubleSpinBox, QLineEdit, QCheckBox
)
from ui.widgets import (
    FileSelector, FolderSelector, ProgressBarWithStatus, LogConsole,
    CommandPreviewWidget, OutputActionsWidget
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class TabCreateVideo(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Carpeta y Patrón de Fotogramas
        group_input = QGroupBox("1. Carpeta con la Secuencia de Fotogramas")
        layout_input = QVBoxLayout(group_input)

        self.folder_selector = FolderSelector("Seleccione la carpeta con las imágenes...")
        self.folder_selector.folder_selected.connect(self._on_folder_selected)
        layout_input.addWidget(self.folder_selector)

        h_pattern = QHBoxLayout()
        h_pattern.addWidget(QLabel("Patrón de nombres:"))
        self.edit_pattern = QLineEdit("frame_%06d.png")
        self.edit_pattern.setPlaceholderText("Ej: frame_%06d.png o img_%04d.jpg")
        h_pattern.addWidget(self.edit_pattern, 1)

        self.lbl_detected = QLabel("Fotogramas detectados: 0")
        self.lbl_detected.setObjectName("lbl_meta")
        h_pattern.addWidget(self.lbl_detected)

        layout_input.addLayout(h_pattern)
        layout.addWidget(group_input)

        # 2. Configuración de Video y Calidad Sin Pérdida
        group_opts = QGroupBox("2. Configuración de Video (Lossless / Alta Fidelidad)")
        layout_opts = QVBoxLayout(group_opts)

        h_row1 = QHBoxLayout()
        h_row1.addWidget(QLabel("Velocidad (FPS):"))
        self.spin_fps = QDoubleSpinBox()
        self.spin_fps.setRange(1.0, 240.0)
        self.spin_fps.setValue(30.0)
        self.spin_fps.setSingleStep(1.0)
        h_row1.addWidget(self.spin_fps)

        h_row1.addWidget(QLabel("Calidad / Códec:"))
        self.combo_codec = QComboBox()
        self.combo_codec.addItem("H.264 Lossless (CRF 0 - 100% Sin Pérdida)", "h264_lossless")
        self.combo_codec.addItem("H.264 Visualmente Idéntico (CRF 17 - Compatible)", "h264_visually_lossless")
        self.combo_codec.addItem("Apple ProRes 422 HQ (Edición Profesional)", "prores")
        self.combo_codec.addItem("WebM VP9 Lossless (Libre de regalías)", "vp9_lossless")
        self.combo_codec.currentIndexChanged.connect(self._on_codec_changed)
        h_row1.addWidget(self.combo_codec, 1)

        layout_opts.addLayout(h_row1)

        # Audio opcional
        layout_opts.addWidget(QLabel("Audio opcional para acompañar el video (opcional):"))
        self.audio_selector = FileSelector(
            placeholder="Seleccione archivo de audio opcional (MP3, WAV, AAC, etc.)...",
            file_filter="Audio (*.mp3 *.wav *.aac *.flac *.m4a *.ogg);;Todos (*.*)"
        )
        layout_opts.addWidget(self.audio_selector)

        layout.addWidget(group_opts)

        # 3. Archivo de Salida
        group_out = QGroupBox("3. Archivo de Video Resultante")
        layout_out = QVBoxLayout(group_out)

        h_sub_opt = QHBoxLayout()
        self.chk_use_base = QCheckBox("Guardar en Carpeta Base configurada")
        self.chk_use_base.setChecked(True)
        self.chk_use_base.stateChanged.connect(self._on_use_base_changed)

        self.chk_subfolder = QCheckBox("Crear subcarpeta con el nombre de la secuencia")
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
            placeholder="Ruta y nombre del video de salida...",
            is_save_dialog=True,
            file_filter="Video MP4 (*.mp4);;Video MOV (*.mov);;Video WebM (*.webm);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.output_selector)
        layout.addWidget(group_out)

        # 4. Vista Previa del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout.addWidget(self.cmd_preview)

        # 5. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout.addWidget(self.progress_widget)

        # 5.5 Acciones post-generación (Abrir Video / Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Video Creado", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Crear Video", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_rendering)

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
        self.spin_fps.valueChanged.connect(lambda _: self._update_command_preview())
        self.combo_codec.currentIndexChanged.connect(lambda _: self._update_command_preview())
        self.audio_selector.file_selected.connect(lambda _: self._update_command_preview())

        self.update_base_dir_display()

    def _on_folder_selected(self, folder: str):
        if not folder or not os.path.isdir(folder):
            self.lbl_detected.setText("Fotogramas detectados: 0")
            return

        # Intentar inferir el patrón buscando archivos comunes
        extensions = ["png", "jpg", "jpeg", "webp", "tiff"]
        found_files = []
        found_ext = "png"
        for ext in extensions:
            matches = glob.glob(os.path.join(folder, f"*.{ext}"))
            if matches:
                found_files = matches
                found_ext = ext
                break

        count = len(found_files)
        self.lbl_detected.setText(f"Imágenes encontradas: {count}")

        if count > 0:
            sample_name = os.path.basename(sorted(found_files)[0])
            # Detectar si hay patrón numérico como frame_000001.png
            match = re.search(r"(\d+)\." + found_ext + "$", sample_name)
            if match:
                num_digits = len(match.group(1))
                prefix = sample_name[:match.start(1)]
                inferred_pattern = f"{prefix}%0{num_digits}d.{found_ext}"
                self.edit_pattern.setText(inferred_pattern)

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

    def _update_output_suggestion(self):
        folder = self.folder_selector.get_path()
        if not folder:
            self.cmd_preview.set_command("")
            return

        codec = self.combo_codec.currentData()
        ext = ".mov" if codec == "prores" else (".webm" if codec == "vp9_lossless" else ".mp4")

        if self.chk_use_base.isChecked():
            suggested = config_manager.suggest_output_path(
                folder,
                suffix="_compilado",
                extension=ext,
                override_auto_subfolders=self.chk_subfolder.isChecked()
            )
        else:
            p = Path(folder)
            suggested = str(p.parent / f"{p.name}_compilado{ext}")

        self.output_selector.set_path(suggested)
        self._update_command_preview()

    def _update_command_preview(self):
        folder = self.folder_selector.get_path()
        out_video = self.output_selector.get_path()
        pattern = self.edit_pattern.text().strip()
        if not folder or not pattern:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        input_pattern_path = os.path.join(folder, pattern)
        fps = self.spin_fps.value()
        codec_preset = self.combo_codec.currentData()
        audio_file = self.audio_selector.get_path() if self.audio_selector.get_path() else None

        ext = ".mov" if codec_preset == "prores" else (".webm" if codec_preset == "vp9_lossless" else ".mp4")
        target_out = out_video if out_video else f"video_compilado{ext}"

        cmd = ffmpeg_core.build_create_video_command(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            input_pattern=input_pattern_path,
            output_file=target_out,
            fps=fps,
            codec_preset=codec_preset,
            audio_file=audio_file
        )
        self.cmd_preview.set_command(cmd)

    def _on_codec_changed(self):
        codec = self.combo_codec.currentData()
        curr_out = self.output_selector.get_path()
        if curr_out:
            p = Path(curr_out)
            if codec == "prores":
                new_ext = ".mov"
            elif codec == "vp9_lossless":
                new_ext = ".webm"
            else:
                new_ext = ".mp4"
            self.output_selector.set_path(str(p.with_suffix(new_ext)))
        self._update_command_preview()

    def _start_rendering(self):
        folder = self.folder_selector.get_path()
        pattern = self.edit_pattern.text().strip()
        out_video = self.output_selector.get_path()

        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Carpeta no válida", "Seleccione la carpeta donde están almacenados los fotogramas.")
            return

        if not pattern:
            QMessageBox.warning(self, "Patrón no válido", "Especifique el patrón de nombres de las imágenes (ej. frame_%06d.png).")
            return

        if not out_video:
            QMessageBox.warning(self, "Ruta de salida", "Especifique el archivo de video resultante.")
            return

        # Crear carpeta de destino automáticamente si no existe en disco
        out_dir = os.path.dirname(out_video)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        input_pattern_path = os.path.join(folder, pattern)
        fps = self.spin_fps.value()
        codec_preset = self.combo_codec.currentData()
        audio_file = self.audio_selector.get_path() if self.audio_selector.get_path() else None

        cmd = ffmpeg_core.build_create_video_command(
            ffmpeg_path=ffmpeg_path,
            input_pattern=input_pattern_path,
            output_file=out_video,
            fps=fps,
            codec_preset=codec_preset,
            audio_file=audio_file
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=0.0, output_path=out_video)
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
            self.output_actions.show_output(out_path)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Video Creado")
            msg_box.setText(f"{message}\n\n<b>Guardado en:</b>\n{out_path}")
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
