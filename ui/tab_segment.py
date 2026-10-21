#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Dividir video en segmentos (chunks) de duración configurable sin pérdida de calidad
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QSpinBox, QLineEdit, QCheckBox
)
from ui.widgets import (
    FileSelector, FolderSelector, ProgressBarWithStatus, LogConsole,
    CommandPreviewWidget, OutputActionsWidget
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class TabSegment(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.media_duration = 0.0

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Video de Entrada
        group_input = QGroupBox("1. Video Original a Segmentar")
        layout_input = QVBoxLayout(group_input)

        self.input_selector = FileSelector(
            placeholder="Seleccione el video a dividir en partes...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts);;Todos (*.*)"
        )
        self.input_selector.file_selected.connect(self._on_file_selected)

        self.lbl_info = QLabel("Duración: --:--:-- | Resolución: -- x --")
        self.lbl_info.setObjectName("lbl_meta")

        layout_input.addWidget(self.input_selector)
        layout_input.addWidget(self.lbl_info)
        layout.addWidget(group_input)

        # 2. Configuración de Segmentación
        group_opts = QGroupBox("2. Configuración de Duración y Calidad")
        layout_opts = QVBoxLayout(group_opts)

        h_dur = QHBoxLayout()
        h_dur.addWidget(QLabel("Duración de cada segmento (segundos):"))
        self.spin_seconds = QSpinBox()
        self.spin_seconds.setRange(1, 86400)
        self.spin_seconds.setValue(15)  # Ejemplo del usuario: 15 segundos
        self.spin_seconds.setSuffix(" seg")
        self.spin_seconds.valueChanged.connect(self._update_estimate)
        h_dur.addWidget(self.spin_seconds)

        self.lbl_estimate = QLabel("Segmentos estimados: ~0")
        self.lbl_estimate.setObjectName("lbl_meta")
        h_dur.addWidget(self.lbl_estimate)
        h_dur.addStretch()
        layout_opts.addLayout(h_dur)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Método de corte:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(
            "Copia Directa (Stream Copy - 100% Sin Pérdida, Ultra Rápido)", "copy"
        )
        self.combo_mode.addItem(
            "Corte Exacto al Segundo (Fuerza Keyframes, Visualmente Idéntico CRF 17)", "exact"
        )
        h_mode.addWidget(self.combo_mode, 1)
        layout_opts.addLayout(h_mode)

        lbl_desc = QLabel(
            "• Stream Copy: Mantiene exactamente los bits y códecs originales sin procesar. Corta en keyframes.\n"
            "• Corte Exacto: Garantiza la duración exacta al segundo insertando keyframes sin pérdida perceptible."
        )
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_opts.addWidget(lbl_desc)

        layout.addWidget(group_opts)

        # 3. Carpeta de Salida y Nombres
        group_out = QGroupBox("3. Carpeta y Nomenclatura de Segmentos")
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

        self.lbl_base_info = QLabel()
        self.lbl_base_info.setStyleSheet("color: #38bdf8; font-size: 11px; padding: 2px 0px;")
        layout_out.addWidget(self.lbl_base_info)

        self.folder_selector = FolderSelector("Seleccione la carpeta donde se guardarán los fragmentos...")
        self.folder_selector.folder_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.folder_selector)

        h_pat = QHBoxLayout()
        h_pat.addWidget(QLabel("Patrón de nombres de los fragmentos:"))
        self.edit_pattern = QLineEdit("segmento_%03d.mp4")
        self.edit_pattern.textChanged.connect(lambda _: self._update_command_preview())
        h_pat.addWidget(self.edit_pattern, 1)
        layout_out.addLayout(h_pat)

        layout.addWidget(group_out)

        # 4. Vista Previa del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout.addWidget(self.cmd_preview)

        # 5. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        layout.addWidget(self.progress_widget)

        # 5.5 Acciones post-generación (Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Segmentos", parent=self)
        layout.addWidget(self.output_actions)

        h_btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("Dividir Video en Segmentos", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_segmenting)

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

        # Conectar cambios de opciones
        self.spin_seconds.valueChanged.connect(lambda _: self._update_command_preview())
        self.combo_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())

        self.update_base_dir_display()

    def _on_file_selected(self, path: str):
        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Resolución: -- x --")
            return

        _, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info["duration"]

        self.lbl_info.setText(
            f"Duración: {info['duration_str']} ({self.media_duration:.1f} seg) | "
            f"Resolución: {info['width']}x{info['height']} | Códec: {info['video_codec'].upper()}"
        )

        p = Path(path)
        self.edit_pattern.setText(f"{p.stem}_part_%03d{p.suffix}")
        self._update_folder_suggestion()
        self._update_estimate()

    def _on_use_base_changed(self):
        use_base = self.chk_use_base.isChecked()
        self.lbl_base_info.setVisible(use_base)
        self.chk_subfolder.setVisible(use_base)
        self._update_folder_suggestion()

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
        self._update_folder_suggestion()

    def _update_folder_suggestion(self):
        path = self.input_selector.get_path()
        if not path:
            self.cmd_preview.set_command("")
            return

        if self.chk_use_base.isChecked():
            suggested = config_manager.suggest_output_path(
                path,
                suffix="_segmentos",
                is_destination_folder=True,
                override_auto_subfolders=self.chk_subfolder.isChecked()
            )
        else:
            p = Path(path)
            suggested = str(p.parent / f"{p.stem}_segmentos")

        self.folder_selector.set_path(suggested)
        self._update_estimate()
        self._update_command_preview()

    def _update_command_preview(self):
        in_path = self.input_selector.get_path()
        out_folder = self.folder_selector.get_path()
        if not in_path:
            self.cmd_preview.set_command("")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        seg_seconds = self.spin_seconds.value()
        mode = self.combo_mode.currentData()

        pattern = self.edit_pattern.text().strip()
        if not pattern:
            ext = Path(in_path).suffix or ".mp4"
            pattern = f"segment_%03d{ext}"

        target_folder = out_folder if out_folder else f"{Path(in_path).stem}_segmentos"
        output_pattern_path = os.path.join(target_folder, pattern)

        cmd = ffmpeg_core.build_segment_command(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            input_file=in_path,
            output_pattern=output_pattern_path,
            segment_duration_sec=seg_seconds,
            mode=mode
        )
        self.cmd_preview.set_command(cmd)

    def _update_estimate(self):
        seg_sec = self.spin_seconds.value()
        if self.media_duration > 0 and seg_sec > 0:
            count = int(self.media_duration // seg_sec) + (1 if (self.media_duration % seg_sec) > 0.05 else 0)
            self.lbl_estimate.setText(f"Segmentos estimados: ~{count} archivos ({seg_sec}s c/u)")
        else:
            self.lbl_estimate.setText("Segmentos estimados: ~0")

    def _start_segmenting(self):
        in_path = self.input_selector.get_path()
        out_folder = self.folder_selector.get_path()

        if not in_path or not os.path.isfile(in_path):
            QMessageBox.warning(self, "Archivo no encontrado", "Seleccione un video de entrada válido.")
            return

        if not out_folder:
            QMessageBox.warning(self, "Carpeta de destino", "Seleccione una carpeta de destino para guardar los segmentos.")
            return

        os.makedirs(out_folder, exist_ok=True)

        pattern = self.edit_pattern.text().strip()
        if not pattern:
            ext = Path(in_path).suffix or ".mp4"
            pattern = f"segment_%03d{ext}"

        output_pattern_path = os.path.join(out_folder, pattern)

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        seg_seconds = self.spin_seconds.value()
        mode = self.combo_mode.currentData()

        cmd = ffmpeg_core.build_segment_command(
            ffmpeg_path=ffmpeg_path,
            input_file=in_path,
            output_pattern=output_pattern_path,
            segment_duration_sec=seg_seconds,
            mode=mode
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=self.media_duration, output_path=out_folder)
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
            self.output_actions.show_output(out_path, is_folder_only=True)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Video Segmentado")
            msg_box.setText(f"{message}\n\n<b>Fragmentos guardados en:</b>\n{out_path}")
            msg_box.setIcon(QMessageBox.Information)
            btn_folder = msg_box.addButton("📁 Abrir Carpeta de Segmentos", QMessageBox.ActionRole)
            msg_box.addButton("Aceptar", QMessageBox.AcceptRole)
            msg_box.exec_()

            if msg_box.clickedButton() == btn_folder:
                config_manager.open_path_in_os(out_path, is_directory=True)
        else:
            QMessageBox.warning(self, "Atención", message)
