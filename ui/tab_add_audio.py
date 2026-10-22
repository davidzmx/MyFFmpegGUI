#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Poner / Reemplazar / Mezclar Audio en un Video
Permite incorporar una pista de audio externa (música, locución, banda sonora) a un solo archivo de video,
con modos:
- Reemplazar audio (o añadir si el video es mudo)
- Mezclar con el audio original del video
- Añadir como pista secundaria de audio
Soporta Stream Copy (-c:v copy) para conservar el 100% de la calidad de video a máxima velocidad.
"""

import os
from pathlib import Path
from PyQt5.QtCore import Qt
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


class TabAddAudio(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.video_duration = 0.0
        self.has_original_audio = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Video de Entrada
        group_video = QGroupBox("1. Video de Entrada")
        layout_video = QVBoxLayout(group_video)

        self.video_selector = FileSelector(
            placeholder="Seleccione o arrastre el archivo de video...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.ts *.m4v);;Todos (*.*)"
        )
        self.video_selector.file_selected.connect(self._on_video_selected)

        self.lbl_video_info = QLabel("Duración: --:--:-- | Resolución: -- x -- | Audio existente: No cargado")
        self.lbl_video_info.setObjectName("lbl_meta")

        layout_video.addWidget(self.video_selector)
        layout_video.addWidget(self.lbl_video_info)
        layout.addWidget(group_video)

        # 2. Pista de Audio a Incorporar
        group_audio = QGroupBox("2. Pista de Audio a Incorporar (Música / Voz / Banda Sonora)")
        layout_audio = QVBoxLayout(group_audio)

        h_audio_top = QHBoxLayout()
        self.audio_selector = FileSelector(
            placeholder="Seleccione o arrastre el archivo de audio (MP3, WAV, AAC, M4A, FLAC, etc.)...",
            file_filter="Archivos de Audio (*.mp3 *.wav *.aac *.m4a *.flac *.ogg *.opus *.wma *.mka);;Todos (*.*)"
        )
        self.audio_selector.file_selected.connect(self._on_audio_selected)
        h_audio_top.addWidget(self.audio_selector, 1)

        self.btn_clear_audio = QPushButton("Quitar Audio")
        self.btn_clear_audio.setIcon(self.style().standardIcon(QStyle.SP_DialogDiscardButton))
        self.btn_clear_audio.setToolTip("Quitar la pista de audio seleccionada")
        self.btn_clear_audio.clicked.connect(self._clear_audio)
        self.btn_clear_audio.setEnabled(False)
        h_audio_top.addWidget(self.btn_clear_audio)
        layout_audio.addLayout(h_audio_top)

        self.lbl_audio_info = QLabel("Duración: --:--:-- | Códec: No cargado | Frecuencia: -- Hz")
        self.lbl_audio_info.setObjectName("lbl_meta")
        layout_audio.addWidget(self.lbl_audio_info)
        layout.addWidget(group_audio)

        # 3. Configuración y Modo de Audio
        group_opts = QGroupBox("3. Configuración y Modo de Audio")
        layout_opts = QVBoxLayout(group_opts)

        grid_opts = QGridLayout()
        grid_opts.setSpacing(10)
        grid_opts.setContentsMargins(4, 8, 4, 8)

        grid_opts.addWidget(QLabel("Modo de audio:"), 0, 0)
        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.addItem("Reemplazar audio del video (o añadir si es mudo)", "replace")
        self.combo_audio_mode.addItem("Mezclar con el audio original del video", "mix")
        self.combo_audio_mode.addItem("Añadir como pista secundaria de audio", "add_track")
        self.combo_audio_mode.currentIndexChanged.connect(self._on_audio_mode_changed)
        grid_opts.addWidget(self.combo_audio_mode, 0, 1)

        grid_opts.addWidget(QLabel("Códec / Formato de Audio:"), 0, 2)
        self.combo_audio_codec = QComboBox()
        self.combo_audio_codec.addItem("AAC 256 kbps (Estándar de Alta Fidelidad - Recomendado)", "aac")
        self.combo_audio_codec.addItem("Copia Directa (Stream Copy - Sin recodificar audio)", "copy")
        self.combo_audio_codec.addItem("MP3 320 kbps (Máxima Calidad MP3)", "mp3")
        self.combo_audio_codec.addItem("FLAC (Comprimido Sin Pérdida)", "flac")
        self.combo_audio_codec.currentIndexChanged.connect(lambda _: self._update_command_preview())
        grid_opts.addWidget(self.combo_audio_codec, 0, 3)

        self.chk_shortest = QCheckBox("Ajustar al final del video (cortar audio sobrante)")
        self.chk_shortest.setChecked(True)
        self.chk_shortest.setToolTip("Si el audio dura más que el video, se corta automáticamente para evitar que el video se quede congelado al final.")
        self.chk_shortest.stateChanged.connect(lambda _: self._update_command_preview())
        grid_opts.addWidget(self.chk_shortest, 1, 0, 1, 4)

        layout_opts.addLayout(grid_opts)

        self.lbl_audio_warning = QLabel("")
        self.lbl_audio_warning.setStyleSheet("color: #f59e0b; font-size: 11px;")
        self.lbl_audio_warning.setVisible(False)
        layout_opts.addWidget(self.lbl_audio_warning)

        lbl_note = QLabel(
            "• El video se procesa a máxima velocidad sin pérdida (Stream Copy: 100% idéntico al original)."
        )
        lbl_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_opts.addWidget(lbl_note)

        layout.addWidget(group_opts)

        # 4. Archivo y Carpeta de Salida
        group_out = QGroupBox("4. Archivo y Carpeta de Salida")
        layout_out = QVBoxLayout(group_out)

        h_dest_mode = QHBoxLayout()
        self.radio_same_folder = QRadioButton("Misma carpeta que el original (mismo nombre con sufijo _audio)")
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

        # Contenedor de opciones exclusivas de Carpeta Base
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
            placeholder="Ruta del archivo resultante...",
            is_save_dialog=True,
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.webm);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.output_selector)
        layout.addWidget(group_out)

        # 5. Previsualización del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout.addWidget(self.cmd_preview)

        # 6. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout.addWidget(self.progress_widget)

        self.output_actions = OutputActionsWidget(file_label="Abrir Video Resultante", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Poner Audio al Video", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_run.clicked.connect(self._start_process)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_process)

        h_btn_layout.addWidget(self.btn_run, 2)
        h_btn_layout.addWidget(self.btn_cancel, 1)
        layout.addLayout(h_btn_layout)

        # 7. Consola de registros
        self.log_console = LogConsole(self)
        layout.addWidget(self.log_console, 1)

        # Inicializar estado visual de carpeta base
        self.update_base_dir_display()

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

    def _on_dest_mode_changed(self):
        self.container_base_opts.setVisible(self.radio_base_folder.isChecked())
        self._update_output_suggestion()

    def _on_video_selected(self, path: str):
        if not path or not os.path.isfile(path):
            self.lbl_video_info.setText("Duración: --:--:-- | Resolución: -- x -- | Audio existente: No cargado")
            self.video_duration = 0.0
            self.has_original_audio = False
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.video_duration = info.get("duration", 0.0)

        audio_codec = info.get("audio_codec", "")
        self.has_original_audio = bool(info.get("audio_streams")) or bool(audio_codec)
        audio_str = f"Audio: {audio_codec.upper()}" if self.has_original_audio else "Sin audio original (Mudo)"

        res_str = f"{info.get('width', 0)}x{info.get('height', 0)}"
        fps_str = f"{info.get('fps', 0):.1f} fps" if info.get('fps', 0) > 0 else ""
        self.lbl_video_info.setText(
            f"Duración: {info.get('duration_str', '00:00:00')} | Resolución: {res_str} {fps_str} | {audio_str}"
        )

        self._check_audio_warning()
        self._update_output_suggestion()

    def _on_audio_selected(self, path: str):
        has_file = bool(path and os.path.isfile(path))
        self.btn_clear_audio.setEnabled(has_file)

        if not has_file:
            self.lbl_audio_info.setText("Duración: --:--:-- | Códec: No cargado | Frecuencia: -- Hz")
            self._update_command_preview()
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        acodec = info.get("audio_codec", "Desconocido").upper()
        sr = ""
        streams = info.get("audio_streams", [])
        if streams and "sample_rate" in streams[0]:
            sr = f" | {streams[0]['sample_rate']} Hz"

        self.lbl_audio_info.setText(
            f"Duración: {info.get('duration_str', '00:00:00')} | Códec: {acodec}{sr}"
        )
        self._update_command_preview()

    def _clear_audio(self):
        self.audio_selector.set_path("")
        self._on_audio_selected("")

    def _on_audio_mode_changed(self):
        self._check_audio_warning()
        self._update_command_preview()

    def _check_audio_warning(self):
        mode = self.combo_audio_mode.currentData()
        video_path = self.video_selector.get_path()
        if video_path and os.path.isfile(video_path) and not self.has_original_audio and mode == "mix":
            self.lbl_audio_warning.setText(
                "Nota: El video seleccionado no tiene audio original para mezclar. El audio nuevo se incorporará como audio principal."
            )
            self.lbl_audio_warning.setVisible(True)
        else:
            self.lbl_audio_warning.setVisible(False)

    def _update_output_suggestion(self):
        in_path = self.video_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        orig_path = Path(in_path)
        ext = orig_path.suffix.lower() or ".mp4"

        is_same_folder = self.radio_same_folder.isChecked()
        if is_same_folder:
            suggested = config_manager.suggest_output_path(
                in_path,
                suffix="_audio",
                extension=ext,
                same_folder_as_input=True
            )
        else:
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
        ffmpeg_p, _ = self.get_ffmpeg_paths()
        ffmpeg_p = ffmpeg_p or "ffmpeg"

        v_path = self.video_selector.get_path() or "video_entrada.mp4"
        a_path = self.audio_selector.get_path() or "pista_audio.mp3"
        out_path = self.output_selector.get_path() or "video_resultado.mp4"

        mode = self.combo_audio_mode.currentData()
        codec = self.combo_audio_codec.currentData()
        shortest = self.chk_shortest.isChecked()

        cmd = ffmpeg_core.build_add_audio_to_video_command(
            ffmpeg_path=ffmpeg_p,
            video_file=v_path,
            audio_file=a_path,
            output_file=out_path,
            audio_mode=mode,
            audio_codec=codec,
            shortest=shortest,
            has_original_audio=self.has_original_audio
        )
        self.cmd_preview.set_command(ffmpeg_core.format_command_for_display(cmd))

    def _start_process(self):
        v_path = config_manager.clean_file_path(self.video_selector.get_path())
        a_path = config_manager.clean_file_path(self.audio_selector.get_path())
        out_path = config_manager.clean_file_path(self.output_selector.get_path())

        if not v_path or not os.path.isfile(v_path):
            QMessageBox.warning(self, "Archivo faltante", "Por favor seleccione un archivo de video válido.")
            return

        if not a_path or not os.path.isfile(a_path):
            QMessageBox.warning(self, "Archivo faltante", "Por favor seleccione una pista de audio válida a incorporar.")
            return

        if not out_path:
            QMessageBox.warning(self, "Ruta de salida", "Especifique el archivo resultante.")
            return

        if os.path.abspath(v_path) == os.path.abspath(out_path):
            QMessageBox.warning(
                self, "Conflicto de archivos",
                "El archivo de salida no puede ser el mismo que el video original para evitar dañarlo."
            )
            return

        out_dir = os.path.dirname(out_path)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_p, _ = self.get_ffmpeg_paths()
        if not ffmpeg_p or not os.path.isfile(ffmpeg_p):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        mode = self.combo_audio_mode.currentData()
        codec = self.combo_audio_codec.currentData()
        shortest = self.chk_shortest.isChecked()

        cmd = ffmpeg_core.build_add_audio_to_video_command(
            ffmpeg_path=ffmpeg_p,
            video_file=v_path,
            audio_file=a_path,
            output_file=out_path,
            audio_mode=mode,
            audio_codec=codec,
            shortest=shortest,
            has_original_audio=self.has_original_audio
        )

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.output_actions.hide_output()
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=self.video_duration, output_path=out_path)
        self.worker.progress_signal.connect(self.progress_widget.set_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel_process(self):
        if self.worker:
            self.worker.cancel()

    def _on_finished(self, success: bool, message: str, out_path: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if success:
            self.output_actions.show_output(out_path)
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Audio Incorporado con Éxito")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>¡Pista de audio procesada e incorporada al video con éxito!</b></p>"
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
