#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Conversor entre Formatos de Video (MP4, MKV, MOV, AVI, WebM, TS, GIF)
Soporta Stream Copy (Sin Pérdida), Carpeta Base y Creación Automática de Carpetas.
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QCheckBox, QRadioButton, QStyle
)
from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class TabConvertVideo(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.media_duration = 0.0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Video de Entrada
        group_input = QGroupBox("1. Video de Entrada a Convertir")
        layout_input = QVBoxLayout(group_input)

        self.input_selector = FileSelector(
            placeholder="Seleccione o arrastre el video (MP4, MKV, AVI, MOV, WebM, etc.)...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.ts *.m4v *.vob);;Todos (*.*)"
        )
        self.input_selector.file_selected.connect(self._on_file_selected)

        self.lbl_info = QLabel("Duración: --:--:-- | Resolución: -- x -- | Códec: No cargado")
        self.lbl_info.setObjectName("lbl_meta")

        layout_input.addWidget(self.input_selector)
        layout_input.addWidget(self.lbl_info)
        layout.addWidget(group_input)

        # 2. Configuración de Formato y Calidad
        group_opts = QGroupBox("2. Formato de Destino y Calidad")
        layout_opts = QVBoxLayout(group_opts)

        grid_opts = QGridLayout()
        grid_opts.setSpacing(10)
        grid_opts.setContentsMargins(4, 8, 4, 8)

        grid_opts.addWidget(QLabel("Formato / Contenedor:"), 0, 0)
        self.combo_container = QComboBox()
        self.combo_container.addItem("MP4 (H.264 / AAC - Universal)", ".mp4")
        self.combo_container.addItem("MKV (Matroska - Multi-Pistas)", ".mkv")
        self.combo_container.addItem("MOV (Apple QuickTime)", ".mov")
        self.combo_container.addItem("WebM (HTML5 / Libre)", ".webm")
        self.combo_container.addItem("AVI (Compatibilidad clásica)", ".avi")
        self.combo_container.addItem("TS (Transport Stream para TV)", ".ts")
        self.combo_container.addItem("GIF Animado de Alta Calidad", ".gif")
        self.combo_container.currentIndexChanged.connect(self._on_container_changed)
        grid_opts.addWidget(self.combo_container, 0, 1)

        grid_opts.addWidget(QLabel("Modo / Calidad:"), 0, 2)
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("Copia Directa (Stream Copy - 100% Sin Pérdida)", "copy")
        self.combo_quality.addItem("H.264 Lossless (CRF 0 - Sin Pérdida)", "h264_lossless")
        self.combo_quality.addItem("H.264 Visualmente Idéntico (CRF 17)", "h264_visually_lossless")
        self.combo_quality.addItem("H.264 Equilibrado Web (CRF 22)", "h264_standard")
        self.combo_quality.addItem("H.265 / HEVC Alta Eficiencia (CRF 20)", "h265")
        self.combo_quality.addItem("Apple ProRes 422 HQ (Edición)", "prores")
        self.combo_quality.addItem("WebM VP9 (Google VP9)", "vp9")
        grid_opts.addWidget(self.combo_quality, 0, 3)

        grid_opts.addWidget(QLabel("Resolución:"), 1, 0)
        self.combo_res = QComboBox()
        self.combo_res.addItem("Mantener Original", "original")
        self.combo_res.addItem("4K Ultra HD (3840x2160)", "3840x2160")
        self.combo_res.addItem("1080p Full HD (1920x1080)", "1920x1080")
        self.combo_res.addItem("720p HD (1280x720)", "1280x720")
        self.combo_res.addItem("480p SD (854x480)", "854x480")
        grid_opts.addWidget(self.combo_res, 1, 1)

        grid_opts.addWidget(QLabel("Códec de Audio:"), 1, 2)
        self.combo_audio = QComboBox()
        self.combo_audio.addItem("Copiar original (Sin tocar)", "copy")
        self.combo_audio.addItem("AAC 256k (Estándar)", "aac")
        self.combo_audio.addItem("MP3 320k (Máxima calidad)", "mp3")
        self.combo_audio.addItem("FLAC (Sin pérdida)", "flac")
        self.combo_audio.addItem("Silenciar (Sin pista de audio)", "none")
        grid_opts.addWidget(self.combo_audio, 1, 3)

        self.combo_quality.currentIndexChanged.connect(lambda _: self._update_command_preview())
        self.combo_res.currentIndexChanged.connect(lambda _: self._update_command_preview())
        self.combo_audio.currentIndexChanged.connect(lambda _: self._update_command_preview())

        self.chk_map_streams = QCheckBox("Conservar todas las pistas de audio y subtítulos (-map 0)")
        self.chk_map_streams.setChecked(True)
        self.chk_map_streams.stateChanged.connect(lambda _: self._update_command_preview())
        grid_opts.addWidget(self.chk_map_streams, 2, 0, 1, 4)

        layout_opts.addLayout(grid_opts)

        lbl_tip = QLabel(
            "• Copia Directa (Stream Copy): Cambia el formato del contenedor (ej. MKV a MP4) en segundos sin procesar los píxeles."
        )
        lbl_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_opts.addWidget(lbl_tip)

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
            placeholder="Ruta y nombre del video resultante...",
            is_save_dialog=True,
            file_filter="Videos (*.mp4 *.mkv *.mov *.webm *.avi *.ts *.gif);;Todos (*.*)"
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

        # 5.5 Acciones post-generación (Abrir Video / Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Video Convertido", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Convertir Video", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_conversion)

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

        # Inicializar estado visual de carpeta base
        self.update_base_dir_display()

    def _on_file_selected(self, path: str):
        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Resolución: -- x -- | Códec: No cargado")
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info["duration"]

        v_codec = info.get("video_codec") or "Desconocido"
        a_codec = info.get("audio_codec") or "Sin audio"

        self.lbl_info.setText(
            f"Duración: {info['duration_str']} | Resolución: {info['width']}x{info['height']} | "
            f"Video: {v_codec.upper()} | Audio: {a_codec.upper()} | FPS: {info['fps']}"
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

    def _on_container_changed(self):
        ext = self.combo_container.currentData()
        if ext == ".gif":
            # Forzar modo GIF
            self.combo_quality.setCurrentIndex(0)
            self.combo_audio.setEnabled(False)
        else:
            self.combo_audio.setEnabled(True)
        self._update_output_suggestion()

    def _update_output_suggestion(self):
        in_path = self.input_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        ext = self.combo_container.currentData() or ".mp4"

        is_same_folder = self.radio_same_folder.isChecked()
        if is_same_folder:
            # Misma carpeta con mismo nombre y nueva extensión
            # exactamente como en comando ffmpeg -i "mi_archivo.mp4" "mi_archivo.mkv"
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
                suffix="_convertido",
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
        ext = self.combo_container.currentData() or ".mp4"
        mode = "gif" if ext == ".gif" else self.combo_quality.currentData()
        resolution = self.combo_res.currentData()
        audio_mode = self.combo_audio.currentData()
        map_all = self.chk_map_streams.isChecked()
        target_out = out_path if out_path else f"{Path(in_path).stem}{ext}"

        cmd = ffmpeg_core.build_convert_video_command(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            input_file=in_path,
            output_file=target_out,
            mode=mode,
            resolution=resolution,
            audio_mode=audio_mode,
            map_all_streams=map_all
        )
        self.cmd_preview.set_command(cmd)

    def _start_conversion(self):
        in_path = self.input_selector.get_path()
        out_path = self.output_selector.get_path()

        if not in_path or not os.path.isfile(in_path):
            QMessageBox.warning(self, "Video no válido", "Seleccione un archivo de video válido para convertir.")
            return

        if not out_path:
            QMessageBox.warning(self, "Ruta de salida", "Especifique el archivo resultante.")
            return

        # Crear carpeta de destino si no existe
        out_dir = os.path.dirname(out_path)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        ext = self.combo_container.currentData()
        mode = "gif" if ext == ".gif" else self.combo_quality.currentData()
        resolution = self.combo_res.currentData()
        audio_mode = self.combo_audio.currentData()
        map_all = self.chk_map_streams.isChecked()

        cmd = ffmpeg_core.build_convert_video_command(
            ffmpeg_path=ffmpeg_path,
            input_file=in_path,
            output_file=out_path,
            mode=mode,
            resolution=resolution,
            audio_mode=audio_mode,
            map_all_streams=map_all
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

    def _cancel(self):
        if self.worker:
            self.worker.cancel()

    def _on_finished(self, success: bool, message: str, out_path: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if success:
            self.output_actions.show_output(out_path)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Conversión Completada")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>{message}</b></p>"
                f"<p><b>Archivo guardado en:</b><br><span style='color: #38bdf8;'>{out_path}</span></p>"
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
