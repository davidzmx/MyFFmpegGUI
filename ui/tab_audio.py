#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Convertir Video a Audio (MP3, WAV, FLAC) y Extracción Sin Pérdida
Soporta Carpeta Base y Creación Automática de Carpetas con el Nombre del Archivo.
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QCheckBox, QRadioButton, QStyle
)
from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class TabAudio(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.media_duration = 0.0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Entrada de archivo
        group_input = QGroupBox("1. Video de Entrada")
        layout_input = QVBoxLayout(group_input)

        self.input_selector = FileSelector(
            placeholder="Seleccione o arrastre el video a procesar...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.ts *.m4v);;Todos (*.*)"
        )
        self.input_selector.file_selected.connect(self._on_file_selected)

        self.lbl_info = QLabel("Duración: --:--:-- | Códec de audio original: No cargado")
        self.lbl_info.setObjectName("lbl_meta")

        layout_input.addWidget(self.input_selector)
        layout_input.addWidget(self.lbl_info)
        layout.addWidget(group_input)

        # 2. Configuración de conversión
        group_opts = QGroupBox("2. Formato y Calidad de Audio (MP3 / WAV / Lossless)")
        layout_opts = QVBoxLayout(group_opts)

        h_layout_fmt = QHBoxLayout()
        lbl_fmt = QLabel("Formato de Salida:")
        self.combo_mode = QComboBox()

        # Opciones WAV prioritarias
        self.combo_mode.addItem("WAV - 16-bit PCM (Calidad CD Sin Pérdida)", "wav_16")
        self.combo_mode.addItem("WAV - 24-bit PCM (Alta Definición / Estudio)", "wav_24")
        self.combo_mode.addItem("WAV - 32-bit Float (Máxima Precisión)", "wav_32")

        # Opciones MP3
        self.combo_mode.addItem("MP3 - 320 kbps (CBR - Máxima Calidad MP3)", "mp3_320k")
        self.combo_mode.addItem("MP3 - VBR Calidad 0 (Máxima Fidelidad Dinámica LAME)", "mp3_vbr0")
        self.combo_mode.addItem("MP3 - 256 kbps (Excelente calidad)", "mp3_256k")
        self.combo_mode.addItem("MP3 - 192 kbps (Estándar equilibrado)", "mp3_192k")

        # Sin pérdida directa y FLAC
        self.combo_mode.addItem("Extracción Directa (Stream Copy - 100% Sin Pérdida Original)", "copy")
        self.combo_mode.addItem("FLAC (Comprimido Sin Pérdida - Lossless)", "flac")

        self.combo_mode.currentIndexChanged.connect(self._update_output_suggestion)

        h_layout_fmt.addWidget(lbl_fmt)
        h_layout_fmt.addWidget(self.combo_mode, 1)

        # Frecuencia de muestreo (Sample Rate)
        lbl_sr = QLabel("Frecuencia (Hz):")
        self.combo_sr = QComboBox()
        self.combo_sr.addItem("Original", 0)
        self.combo_sr.addItem("44100 Hz (Estándar CD)", 44100)
        self.combo_sr.addItem("48000 Hz (Estándar Video / DVD)", 48000)
        self.combo_sr.addItem("96000 Hz (Hi-Res Audio)", 96000)

        h_layout_fmt.addWidget(lbl_sr)
        h_layout_fmt.addWidget(self.combo_sr)
        self.combo_sr.currentIndexChanged.connect(lambda _: self._update_command_preview())

        layout_opts.addLayout(h_layout_fmt)

        self.chk_metadata = QCheckBox("Conservar etiquetas y metadatos del video original")
        self.chk_metadata.setChecked(True)
        self.chk_metadata.stateChanged.connect(lambda _: self._update_command_preview())
        layout_opts.addWidget(self.chk_metadata)

        layout.addWidget(group_opts)

        # 3. Salida de archivo con opción de Misma Carpeta o Carpeta Base
        group_out = QGroupBox("3. Archivo y Carpeta de Salida")
        layout_out = QVBoxLayout(group_out)

        h_dest_mode = QHBoxLayout()
        self.radio_same_folder = QRadioButton("Misma carpeta que el original (mismo nombre, nueva extensión)")
        self.radio_base_folder = QRadioButton("Carpeta Base configurada")

        pref = config_manager.get_default_save_location()
        if pref == "base_dir":
            self.radio_base_folder.setChecked(True)
        else:
            self.radio_same_folder.setChecked(True)

        self.radio_same_folder.toggled.connect(self._on_dest_mode_changed)
        self.radio_base_folder.toggled.connect(self._on_dest_mode_changed)

        h_dest_mode.addWidget(self.radio_same_folder)
        h_dest_mode.addWidget(self.radio_base_folder)
        h_dest_mode.addStretch()
        layout_out.addLayout(h_dest_mode)

        # Contenedor de opciones exclusivas de Carpeta Base (solo visible si radio_base_folder está activo)
        self.container_base_opts = QWidget()
        v_base_opts = QVBoxLayout(self.container_base_opts)
        v_base_opts.setContentsMargins(0, 2, 0, 4)
        v_base_opts.setSpacing(4)

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
        v_base_opts.addLayout(h_base)

        self.chk_subfolder = QCheckBox("Crear subcarpeta con el nombre del archivo dentro de la Carpeta Base")
        self.chk_subfolder.setChecked(config_manager.is_auto_suggest_subfolders())
        self.chk_subfolder.stateChanged.connect(self._update_output_suggestion)
        v_base_opts.addWidget(self.chk_subfolder)

        layout_out.addWidget(self.container_base_opts)

        self.output_selector = FileSelector(
            placeholder="Ruta del archivo de audio resultante...",
            is_save_dialog=True,
            file_filter="Audio (*.wav *.mp3 *.flac *.m4a);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(self._on_output_path_changed)
        layout_out.addWidget(self.output_selector)
        layout.addWidget(group_out)

        # 4. Vista Previa del Comando FFmpeg a ejecutar con botón de copiar
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout.addWidget(self.cmd_preview)

        # 5. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout.addWidget(self.progress_widget)

        # 5.5 Acciones post-generación (Abrir Audio / Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Audio Extraído", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Convertir a Audio", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_conversion)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_conversion)

        h_btn_layout.addWidget(self.btn_run, 2)
        h_btn_layout.addWidget(self.btn_cancel, 1)
        layout.addLayout(h_btn_layout)

        # 6. Consola de registros
        self.log_console = LogConsole(self)
        layout.addWidget(self.log_console, 1)

        # Inicializar estado visual de carpeta base
        self.update_base_dir_display()

    def _on_file_selected(self, path: str):
        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Códec de audio original: No cargado")
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info["duration"]

        audio_codec = info["audio_codec"] or "Ninguno / Desconocido"
        self.lbl_info.setText(
            f"Duración: {info['duration_str']} | Códec original: {audio_codec.upper()} | Tamaño: {info['size_bytes'] / (1024*1024):.2f} MB"
        )
        self._update_output_suggestion()

    def _on_dest_mode_changed(self):
        is_base = self.radio_base_folder.isChecked()
        self.container_base_opts.setVisible(is_base)
        self._update_output_suggestion()

    def update_base_dir_display(self):
        base_dir = config_manager.get_base_output_dir()
        self.lbl_base_info.setText(
            f'<b>Carpeta Base actual:</b> <a href="{base_dir}" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">{base_dir}</a> '
            f'<span style="color: #94a3b8; font-size: 11px;">(Haz clic para abrir)</span>'
        )
        config_manager.make_clickable_folder_label(self.lbl_base_info, config_manager.get_base_output_dir)
        self.radio_base_folder.setToolTip(f"Carpeta Base actual: {base_dir}")
        self.container_base_opts.setVisible(self.radio_base_folder.isChecked())
        self._update_output_suggestion()

    def _on_output_path_changed(self, path: str):
        self._update_command_preview()

    def _update_output_suggestion(self):
        in_path = self.input_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        mode = self.combo_mode.currentData()

        if mode.startswith("wav"):
            ext = ".wav"
        elif mode.startswith("mp3"):
            ext = ".mp3"
        elif mode == "flac":
            ext = ".flac"
        elif mode == "copy":
            _, ffprobe_path = self.get_ffmpeg_paths()
            info = ffmpeg_core.get_media_info(in_path, ffprobe_path)
            ac = (info.get("audio_codec") or "aac").lower()
            if "aac" in ac:
                ext = ".m4a"
            elif "opus" in ac:
                ext = ".opus"
            elif "mp3" in ac:
                ext = ".mp3"
            elif "flac" in ac:
                ext = ".flac"
            elif "pcm" in ac:
                ext = ".wav"
            else:
                ext = f".{ac}"
        else:
            ext = ".wav"

        is_same_folder = self.radio_same_folder.isChecked()
        if is_same_folder:
            # Misma carpeta que el original con mismo nombre y nueva extensión
            # exactamente como en comando ffmpeg -i "mi_archivo.mp4" "mi_archivo.mp3"
            suggested = config_manager.suggest_output_path(
                in_path,
                suffix="",
                extension=ext,
                same_folder_as_input=True
            )
        else:
            # Carpeta base configurada
            suggested = config_manager.suggest_output_path(
                in_path,
                suffix="_audio",
                extension=ext,
                override_auto_subfolders=self.chk_subfolder.isChecked(),
                same_folder_as_input=False
            )

        self.output_selector.set_path(suggested)
        self._update_command_preview()

    def _update_command_preview(self):
        in_path = self.input_selector.get_path()
        out_path = self.output_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        mode = self.combo_mode.currentData() or "mp3_320k"
        keep_meta = self.chk_metadata.isChecked()
        sr = self.combo_sr.currentData()
        sr_val = sr if sr and sr > 0 else None
        target_out = out_path if out_path else f"{Path(in_path).stem}.mp3"

        cmd = ffmpeg_core.build_audio_convert_command(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            input_file=in_path,
            output_file=target_out,
            mode=mode,
            sample_rate=sr_val,
            keep_metadata=keep_meta
        )
        self.cmd_preview.set_command(cmd)

    def _start_conversion(self):
        in_path = self.input_selector.get_path()
        out_path = self.output_selector.get_path()

        if not in_path or not os.path.isfile(in_path):
            QMessageBox.warning(self, "Archivo no encontrado", "Por favor seleccione un archivo de video válido.")
            return

        if not out_path:
            QMessageBox.warning(self, "Ruta de salida", "Por favor especifique la ruta del archivo de audio resultante.")
            return

        # Crear carpeta destino automáticamente si no existe
        out_dir = os.path.dirname(out_path)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg. Revise la pestaña de Ajustes.")
            return

        mode = self.combo_mode.currentData()
        keep_meta = self.chk_metadata.isChecked()
        sample_rate = self.combo_sr.currentData()

        cmd = ffmpeg_core.build_audio_convert_command(
            ffmpeg_path=ffmpeg_path,
            input_file=in_path,
            output_file=out_path,
            mode=mode,
            sample_rate=sample_rate,
            keep_metadata=keep_meta
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=self.media_duration, output_path=out_path)
        self.worker.progress_signal.connect(self.progress_widget.set_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel_conversion(self):
        if self.worker:
            self.worker.cancel()

    def _on_finished(self, success: bool, message: str, out_path: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if success:
            self.output_actions.show_output(out_path)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Audio Convertido")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>{message}</b></p>"
                f"<p><b>Guardado en:</b><br><span style='color: #38bdf8;'>{out_path}</span></p>"
                f"</div>"
            )
            msg_box.setIcon(QMessageBox.Information)
            btn_play = msg_box.addButton("Abrir Audio", QMessageBox.ActionRole)
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
