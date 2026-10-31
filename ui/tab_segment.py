#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Dividir video en segmentos (automático o avanzado mediante línea de tiempo interactiva)
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Optional

from PyQt5.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QSpinBox, QLineEdit, QCheckBox, QStyle,
    QRadioButton
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from ui.widgets import (
    FileSelector, FolderSelector, ProgressBarWithStatus, LogConsole,
    CommandPreviewWidget, OutputActionsWidget, setup_tab_console_layout
)
from ui.timeline_waveform import AudioSegmentSelectorWidget, format_seconds_exact
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker


class BatchVideoCutWorker(QThread):
    """
    Hilo de trabajo para extraer secuencialmente una lista de segmentos de video
    con monitoreo de progreso continuo y cancelación limpia.
    """
    progress_signal = pyqtSignal(float, str, str)  # (porcentaje, tiempo_str, info_status)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, str)

    def __init__(
        self,
        ffmpeg_path: str,
        input_file: str,
        segments: List[Tuple[float, float]],
        out_folder: str,
        pattern: str,
        mode: str = "exact",
        parent=None
    ):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.input_file = input_file
        self.segments = segments
        self.out_folder = out_folder
        self.pattern = pattern
        self.mode = mode
        self._is_cancelled = False
        self._current_process = None

    def run(self):
        self._is_cancelled = False
        total_segs = len(self.segments)
        total_cut_duration = sum(max(0.0, en - st) for st, en in self.segments)
        accumulated_duration = 0.0

        self.log_signal.emit(f"==> Iniciando extracción de {total_segs} segmentos de video (Modo: {self.mode})...\n")

        for idx, (st, en) in enumerate(self.segments, start=1):
            if self._is_cancelled:
                break

            seg_dur = max(0.001, en - st)
            if "%" in self.pattern:
                try:
                    filename = self.pattern % idx
                except Exception:
                    ext = Path(self.input_file).suffix or ".mp4"
                    filename = f"segmento_{idx:03d}{ext}"
            else:
                p = Path(self.pattern)
                filename = f"{p.stem}_{idx:03d}{p.suffix or '.mp4'}"

            out_file = os.path.join(self.out_folder, filename)
            cmd = ffmpeg_core.build_cut_video_segment_command(
                ffmpeg_path=self.ffmpeg_path,
                input_file=self.input_file,
                output_file=out_file,
                start_sec=st,
                end_sec=en,
                mode=self.mode
            )

            cmd_disp = ffmpeg_core.format_command_for_display(cmd)
            self.log_signal.emit(f"[{idx}/{total_segs}] Extrayendo {format_seconds_exact(st)} a {format_seconds_exact(en)} ({seg_dur:.2f}s):\n$ {cmd_disp}\n")

            startupinfo = None
            creationflags = 0
            if sys.platform.startswith("win"):
                import subprocess
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

            import subprocess
            try:
                self._current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )

                time_regex = __import__("re").compile(r"time=(\d{2}:\d{2}:\d{2}\.\d+)")
                speed_regex = __import__("re").compile(r"speed=\s*([\d\.]+x)")

                for line in self._current_process.stderr:
                    if self._is_cancelled:
                        break
                    l_str = line.strip()
                    if l_str:
                        self.log_signal.emit(l_str)

                    m_t = time_regex.search(line)
                    if m_t:
                        t_str = m_t.group(1)
                        curr_sec = ffmpeg_core.parse_time_to_seconds(t_str) if hasattr(ffmpeg_core, "parse_time_to_seconds") else 0.0
                        if total_cut_duration > 0:
                            overall_pct = min(100.0, max(0.0, ((accumulated_duration + min(curr_sec, seg_dur)) / total_cut_duration) * 100.0))
                        else:
                            overall_pct = (idx / total_segs) * 100.0

                        speed = "1x"
                        m_sp = speed_regex.search(line)
                        if m_sp:
                            speed = m_sp.group(1)

                        self.progress_signal.emit(overall_pct, f"Parte {idx}/{total_segs}", f"Vel: {speed} | {format_seconds_exact(st)}→{format_seconds_exact(en)}")

                self._current_process.wait()
                ret = self._current_process.returncode

                if self._is_cancelled:
                    break
                if ret != 0:
                    self.finished_signal.emit(False, f"Error extrayendo segmento #{idx} ({filename}). Código FFmpeg: {ret}", self.out_folder)
                    return

                accumulated_duration += seg_dur

            except Exception as e:
                self.finished_signal.emit(False, f"Excepción extrayendo segmento #{idx}: {e}", self.out_folder)
                return
            finally:
                self._current_process = None

        if self._is_cancelled:
            self.log_signal.emit("\n[PROCESO CANCELADO POR EL USUARIO]")
            self.finished_signal.emit(False, "Operación cancelada por el usuario.", self.out_folder)
        else:
            self.progress_signal.emit(100.0, "Completado", f"{total_segs} partes listas")
            self.log_signal.emit(f"\n[PROCESO COMPLETADO EXITOSAMENTE: {total_segs} segmentos generados]")
            self.finished_signal.emit(True, f"¡Se extrajeron exitosamente {total_segs} segmentos!", self.out_folder)

    def cancel(self):
        self._is_cancelled = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                try:
                    self._current_process.kill()
                except Exception:
                    pass


class TabSegment(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.media_duration = 0.0

        # Reproductor interno para la línea de tiempo interactiva
        self.player = QMediaPlayer(self)
        self.player.stateChanged.connect(self._on_player_state_changed)
        self.player.positionChanged.connect(self._on_player_position_changed)
        self._timeline_stop_ms: Optional[int] = None

        # Temporizador de alta resolución para playhead suave a 40 FPS
        self._smooth_timer = QTimer(self)
        self._smooth_timer.setInterval(25)
        self._smooth_timer.timeout.connect(self._on_smooth_playhead_tick)
        self._play_sync_pos: float = 0.0
        self._play_sync_perf: float = 0.0

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(10, 10, 10, 10)

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
        form_layout.addWidget(group_input)

        # 2. Configuración y Selección de Modo de Segmentación
        group_opts = QGroupBox("2. Modo de Segmentación y Calidad")
        layout_opts = QVBoxLayout(group_opts)

        # Selector de Modo: Automático vs Avanzado Manual
        h_mode_choice = QHBoxLayout()
        self.radio_mode_auto = QRadioButton("⏱️ Automático (Dividir cada N segundos)")
        self.radio_mode_advanced = QRadioButton("✂️ Avanzado (Selección Gráfica en Línea de Tiempo)")
        self.radio_mode_auto.setChecked(True)
        self.radio_mode_auto.toggled.connect(self._on_segment_mode_changed)
        self.radio_mode_advanced.toggled.connect(self._on_segment_mode_changed)

        h_mode_choice.addWidget(self.radio_mode_auto)
        h_mode_choice.addWidget(self.radio_mode_advanced)
        h_mode_choice.addStretch()
        layout_opts.addLayout(h_mode_choice)

        # 2.1 Panel para Modo Automático (Intervalo fijo de segundos)
        self.panel_auto = QWidget()
        layout_auto = QVBoxLayout(self.panel_auto)
        layout_auto.setContentsMargins(0, 4, 0, 0)
        layout_auto.setSpacing(8)

        h_dur = QHBoxLayout()
        h_dur.addWidget(QLabel("Duración de cada segmento (segundos):"))
        self.spin_seconds = QSpinBox()
        self.spin_seconds.setRange(1, 86400)
        self.spin_seconds.setValue(15)
        self.spin_seconds.setSuffix(" seg")
        self.spin_seconds.valueChanged.connect(self._update_estimate)
        h_dur.addWidget(self.spin_seconds)

        self.lbl_estimate = QLabel("Segmentos estimados: ~0")
        self.lbl_estimate.setObjectName("lbl_meta")
        h_dur.addWidget(self.lbl_estimate)
        h_dur.addStretch()
        layout_auto.addLayout(h_dur)

        layout_opts.addWidget(self.panel_auto)

        # 2.2 Panel para Modo Avanzado (Línea de tiempo gráfica interactiva)
        self.panel_advanced = QWidget()
        layout_adv = QVBoxLayout(self.panel_advanced)
        layout_adv.setContentsMargins(0, 4, 0, 0)
        layout_adv.setSpacing(8)

        guide_txt = (
            "✂️ <b>Selector Gráfico de Video:</b> Haz clic en la regla o arrastra el marcador rojo (triángulo superior) para ubicar la posición. "
            "Arrastra con el ratón sobre la onda para marcar los segmentos de video deseados y ajusta sus bordes con las manijas. "
            "Usa los botones de Zoom o <b>Ctrl + Rueda</b> para máxima precisión."
        )
        self.timeline_widget = AudioSegmentSelectorWidget(guide_text=guide_txt, parent=self)
        self.timeline_widget.play_normal_requested.connect(self._on_timeline_play_normal_requested)
        self.timeline_widget.play_selection_requested.connect(self._on_timeline_play_selection_requested)
        self.timeline_widget.play_requested.connect(self._on_timeline_play_selection_requested)
        self.timeline_widget.stop_requested.connect(self._on_timeline_stop_requested)
        self.timeline_widget.seek_requested.connect(self._on_timeline_seek_requested)
        self.timeline_widget.segments_updated.connect(lambda _: self._update_estimate())
        self.timeline_widget.segments_updated.connect(lambda _: self._update_command_preview())
        layout_adv.addWidget(self.timeline_widget)

        self.panel_advanced.setVisible(False)
        layout_opts.addWidget(self.panel_advanced)

        # Opciones comunes: Método de corte
        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Método de corte:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(
            "Corte Exacto al Segundo (Fuerza Keyframes, Visualmente Idéntico CRF 17 - Predeterminado)", "exact"
        )
        self.combo_mode.addItem(
            "Copia Directa (Stream Copy - 100% Sin Pérdida, Ultra Rápido)", "copy"
        )
        self.combo_mode.setCurrentIndex(0)
        h_mode.addWidget(self.combo_mode, 1)
        layout_opts.addLayout(h_mode)

        lbl_desc = QLabel(
            "• Corte Exacto (Predeterminado): Garantiza la duración exacta al milisegundo insertando keyframes sin pérdida perceptible.\n"
            "• Stream Copy: Mantiene exactamente los bits y códecs originales sin procesar. Corta en keyframes más cercanos."
        )
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_opts.addWidget(lbl_desc)

        form_layout.addWidget(group_opts)

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

        self.folder_selector = FolderSelector("Seleccione la carpeta donde se guardarán los fragmentos...")
        self.folder_selector.folder_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.folder_selector)

        h_pat = QHBoxLayout()
        h_pat.addWidget(QLabel("Patrón de nombres de los fragmentos:"))
        self.edit_pattern = QLineEdit("segmento_%03d.mp4")
        self.edit_pattern.textChanged.connect(lambda _: self._update_command_preview())
        h_pat.addWidget(self.edit_pattern, 1)
        layout_out.addLayout(h_pat)

        form_layout.addWidget(group_out)

        # 4. Progreso y Acciones
        self.progress_widget = ProgressBarWithStatus(self)
        form_layout.addWidget(self.progress_widget)

        # 4.5 Acciones post-generación (Abrir Carpeta)
        self.output_actions = OutputActionsWidget(file_label="Abrir Segmentos", parent=self)
        form_layout.addWidget(self.output_actions)

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
        form_layout.addLayout(h_btn_layout)
        form_layout.addStretch()

        # Configurar panel de consola y comando (ocultable / inferior o lateral)
        setup_tab_console_layout(self, form_widget, "Comando FFmpeg a ejecutar:")

        # Conectar cambios de opciones
        self.spin_seconds.valueChanged.connect(lambda _: self._update_command_preview())
        self.combo_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())

        self.update_base_dir_display()

    def _on_segment_mode_changed(self):
        is_adv = self.radio_mode_advanced.isChecked()
        self.panel_auto.setVisible(not is_adv)
        self.panel_advanced.setVisible(is_adv)

        if is_adv:
            self.btn_run.setText("Extraer Segmentos Seleccionados")
        else:
            self.btn_run.setText("Dividir Video en Segmentos")

        self._update_estimate()
        self._update_command_preview()

    def _on_file_selected(self, path: str):
        if hasattr(self, "player") and self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        if hasattr(self, "_smooth_timer"):
            self._smooth_timer.stop()

        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Resolución: -- x --")
            self.media_duration = 0.0
            if hasattr(self, "timeline_widget"):
                self.timeline_widget.canvas.set_media(0.0, None)
                self.timeline_widget.set_segments([])
            self._update_estimate()
            self._update_command_preview()
            return

        ffmpeg_path, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info["duration"]

        self.lbl_info.setText(
            f"Duración: {info['duration_str']} ({self.media_duration:.1f} seg) | "
            f"Resolución: {info['width']}x{info['height']} | Códec: {info['video_codec'].upper()}"
        )

        p = Path(path)
        self.edit_pattern.setText(f"{p.stem}_part_%03d{p.suffix}")

        # Cargar onda en el selector de línea de tiempo interactiva
        if hasattr(self, "timeline_widget") and ffmpeg_path:
            self.timeline_widget.load_audio_file(ffmpeg_path, path, self.media_duration)

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
            f'<b>Carpeta Base actual:</b> <a href="{base_dir}" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">{base_dir}</a> '
            f'<span style="color: #94a3b8; font-size: 11px;">(Haz clic para abrir)</span>'
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
        mode = self.combo_mode.currentData()
        pattern = self.edit_pattern.text().strip()
        if not pattern:
            ext = Path(in_path).suffix or ".mp4"
            pattern = f"segment_%03d{ext}"

        target_folder = out_folder if out_folder else f"{Path(in_path).stem}_segmentos"
        output_pattern_path = os.path.join(target_folder, pattern)

        if self.radio_mode_advanced.isChecked():
            # Modo Avanzado Manual
            segs = self.timeline_widget.get_segments() if hasattr(self, "timeline_widget") else []
            if not segs:
                self.cmd_preview.set_command("Modo Avanzado: Marque uno o más segmentos arrastrando sobre la línea de tiempo gráfica.")
                return

            preview_lines = []
            for idx, (st, en) in enumerate(segs, start=1):
                try:
                    fname = pattern % idx
                except Exception:
                    ext = Path(in_path).suffix or ".mp4"
                    fname = f"segmento_{idx:03d}{ext}"
                out_file = os.path.join(target_folder, fname)
                cmd = ffmpeg_core.build_cut_video_segment_command(
                    ffmpeg_path=ffmpeg_path or "ffmpeg",
                    input_file=in_path,
                    output_file=out_file,
                    start_sec=st,
                    end_sec=en,
                    mode=mode
                )
                preview_lines.append(f"# [{idx}/{len(segs)}] {format_seconds_exact(st)} - {format_seconds_exact(en)} ({en - st:.2f}s)\n$ " + ffmpeg_core.format_command_for_display(cmd))

            self.cmd_preview.set_command("\n\n".join(preview_lines))
        else:
            # Modo Automático por intervalo de segundos
            seg_seconds = self.spin_seconds.value()
            cmd = ffmpeg_core.build_segment_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                input_file=in_path,
                output_pattern=output_pattern_path,
                segment_duration_sec=seg_seconds,
                mode=mode
            )
            self.cmd_preview.set_command(cmd)

    def _update_estimate(self):
        if self.radio_mode_advanced.isChecked():
            segs = self.timeline_widget.get_segments() if hasattr(self, "timeline_widget") else []
            count = len(segs)
            tot_dur = sum((en - st) for st, en in segs)
            self.lbl_estimate.setText(f"Segmentos marcados: {count} ({tot_dur:.2f} seg total)")
        else:
            seg_sec = self.spin_seconds.value()
            if self.media_duration > 0 and seg_sec > 0:
                count = int(self.media_duration // seg_sec) + (1 if (self.media_duration % seg_sec) > 0.05 else 0)
                self.lbl_estimate.setText(f"Segmentos estimados: ~{count} archivos ({seg_sec}s c/u)")
            else:
                self.lbl_estimate.setText("Segmentos estimados: ~0")

    # Métodos de reproducción e interacción con la línea de tiempo
    def _on_smooth_playhead_tick(self):
        if self.player.state() != QMediaPlayer.PlayingState:
            self._smooth_timer.stop()
            return

        elapsed = time.perf_counter() - self._play_sync_perf
        est_sec = self._play_sync_pos + elapsed

        if self._timeline_stop_ms is not None:
            stop_sec = self._timeline_stop_ms / 1000.0
            if est_sec >= stop_sec:
                self._smooth_timer.stop()
                self._timeline_stop_ms = None
                self.player.pause()
                self.timeline_widget.set_playhead_pos(stop_sec)
                self.timeline_widget.set_playing_state(False)
                return

        if self.media_duration > 0 and est_sec >= self.media_duration:
            self._smooth_timer.stop()
            self._timeline_stop_ms = None
            self.player.pause()
            self.timeline_widget.set_playhead_pos(self.media_duration)
            self.timeline_widget.set_playing_state(False)
            return

        self.timeline_widget.set_playhead_pos(est_sec)

    def _on_timeline_play_normal_requested(self, start_sec: float):
        input_path = self.input_selector.get_path()
        if not input_path or not os.path.isfile(input_path):
            self.timeline_widget.set_playing_state(False)
            return

        try:
            self._timeline_stop_ms = None
            self._smooth_timer.stop()
            self.player.stop()
            content = QMediaContent(QUrl.fromLocalFile(input_path))
            self.player.setMedia(content)
            self.player.setPosition(int(start_sec * 1000))
            self.player.play()

            self._play_sync_pos = float(start_sec)
            self._play_sync_perf = time.perf_counter()
            self._smooth_timer.start()

            self.timeline_widget.set_playhead_pos(start_sec)
            self.timeline_widget.set_playing_state(True, mode="normal")
            self.progress_widget.set_status("Reproduciendo video normalmente...")
        except Exception:
            self._smooth_timer.stop()
            self.timeline_widget.set_playing_state(False)

    def _on_timeline_play_selection_requested(self, start_sec: float, end_sec: float):
        input_path = self.input_selector.get_path()
        if not input_path or not os.path.isfile(input_path):
            self.timeline_widget.set_playing_state(False)
            return

        try:
            self._timeline_stop_ms = int(end_sec * 1000)
            self._smooth_timer.stop()
            self.player.stop()
            content = QMediaContent(QUrl.fromLocalFile(input_path))
            self.player.setMedia(content)
            self.player.setPosition(int(start_sec * 1000))
            self.player.play()

            self._play_sync_pos = float(start_sec)
            self._play_sync_perf = time.perf_counter()
            self._smooth_timer.start()

            self.timeline_widget.set_playhead_pos(start_sec)
            self.timeline_widget.set_playing_state(True, mode="selection")
            self.progress_widget.set_status(f"Reproduciendo selección ({end_sec - start_sec:.2f}s)...")
        except Exception:
            self._smooth_timer.stop()
            self.timeline_widget.set_playing_state(False)

    def _on_timeline_stop_requested(self):
        self._smooth_timer.stop()
        self._timeline_stop_ms = None
        cur_pos_sec = self.timeline_widget.canvas.playhead_pos
        self.player.pause()
        self.timeline_widget.set_playing_state(False)
        self.timeline_widget.set_playhead_pos(cur_pos_sec)
        self.progress_widget.set_status("Reproducción detenida.")

    def _on_timeline_seek_requested(self, sec: float):
        self._play_sync_pos = float(sec)
        self._play_sync_perf = time.perf_counter()
        self.player.setPosition(int(sec * 1000))

    def _on_player_position_changed(self, pos_ms: int):
        if self.player.state() != QMediaPlayer.PlayingState:
            return

        if self.radio_mode_advanced.isChecked():
            real_sec = pos_ms / 1000.0
            self._play_sync_pos = real_sec
            self._play_sync_perf = time.perf_counter()

            if hasattr(self, "_timeline_stop_ms") and self._timeline_stop_ms is not None and pos_ms >= self._timeline_stop_ms:
                stop_sec = self._timeline_stop_ms / 1000.0
                self._smooth_timer.stop()
                self._timeline_stop_ms = None
                self.player.pause()
                self.timeline_widget.set_playhead_pos(stop_sec)
                self.timeline_widget.set_playing_state(False)

    def _on_player_state_changed(self, state):
        if state != QMediaPlayer.PlayingState:
            self._smooth_timer.stop()
            if hasattr(self, "timeline_widget"):
                self.timeline_widget.set_playing_state(False)

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

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        mode = self.combo_mode.currentData()

        # Detener reproducción antes de procesar
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        self._smooth_timer.stop()

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        if self.radio_mode_advanced.isChecked():
            # Modo Avanzado Manual
            segs = self.timeline_widget.get_segments()
            if not segs:
                QMessageBox.warning(self, "Sin segmentos", "Marque al menos un segmento en la línea de tiempo interactiva.")
                self.btn_run.setEnabled(True)
                self.btn_cancel.setEnabled(False)
                return

            self.worker = BatchVideoCutWorker(
                ffmpeg_path=ffmpeg_path,
                input_file=in_path,
                segments=segs,
                out_folder=out_folder,
                pattern=pattern,
                mode=mode
            )
            self.worker.progress_signal.connect(self.progress_widget.set_progress)
            self.worker.log_signal.connect(self.log_console.append_log)
            self.worker.finished_signal.connect(self._on_finished)
            self.worker.start()

        else:
            # Modo Automático
            output_pattern_path = os.path.join(out_folder, pattern)
            seg_seconds = self.spin_seconds.value()
            cmd = ffmpeg_core.build_segment_command(
                ffmpeg_path=ffmpeg_path,
                input_file=in_path,
                output_pattern=output_pattern_path,
                segment_duration_sec=seg_seconds,
                mode=mode
            )

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
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>{message}</b></p>"
                f"<p><b>Fragmentos guardados en:</b><br><span style='color: #38bdf8;'>{out_path}</span></p>"
                f"</div>"
            )
            msg_box.setIcon(QMessageBox.Information)
            btn_folder = msg_box.addButton("Abrir Carpeta de Segmentos", QMessageBox.ActionRole)
            btn_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            msg_box.addButton("Aceptar", QMessageBox.AcceptRole)
            msg_box.exec_()

            if msg_box.clickedButton() == btn_folder:
                config_manager.open_path_in_os(out_path, is_directory=True)
        else:
            QMessageBox.warning(self, "Atención", message)
