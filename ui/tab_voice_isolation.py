#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Aislar Voces y Diarización de Hablantes
Permite la extracción de voces limpias con reducción de ruido y la separación de muestras por interlocutor.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QCheckBox, QRadioButton, QSpinBox,
    QScrollArea, QFrame, QStyle, QApplication, QFileDialog
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole, CommandPreviewWidget, OutputActionsWidget,
    setup_tab_console_layout
)
from ui.timeline_waveform import AudioSegmentSelectorWidget, format_seconds_exact
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker
from voice_worker import DiarizationWorker


class SpeakerCard(QFrame):
    """
    Tarjeta visual para representar un interlocutor detectado durante la diarización,
    con botones para reproducir vista previa, exportar muestra limpia o exportar diálogo completo.
    """
    def __init__(
        self,
        speaker_data: dict,
        on_play_sample_fn,
        on_export_sample_fn,
        on_export_full_fn,
        on_edit_timeline_fn=None,
        parent=None
    ):
        super().__init__(parent)
        self.speaker_data = speaker_data
        self.on_play_sample_fn = on_play_sample_fn
        self.on_export_sample_fn = on_export_sample_fn
        self.on_export_full_fn = on_export_full_fn
        self.on_edit_timeline_fn = on_edit_timeline_fn

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            SpeakerCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
            }
            SpeakerCard:hover {
                border-color: #38bdf8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Encabezado
        h_head = QHBoxLayout()
        spk_name = speaker_data.get("name", "Hablante")
        seg_count = speaker_data.get("segment_count", 0)
        tot_dur_fmt = speaker_data.get("total_duration_fmt", "00:00")

        lbl_title = QLabel(f"👤 {spk_name}")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #38bdf8;")

        lbl_stats = QLabel(f"{seg_count} intervenciones | Tiempo total: {tot_dur_fmt}")
        lbl_stats.setStyleSheet("color: #94a3b8; font-size: 12px;")

        h_head.addWidget(lbl_title)
        h_head.addSpacing(10)
        h_head.addWidget(lbl_stats)
        h_head.addStretch()

        layout.addLayout(h_head)

        # Fila de acciones
        h_actions = QHBoxLayout()
        h_actions.setSpacing(8)

        style = self.style()

        # Botón Reproducir / Vista Previa
        self.btn_play = QPushButton(" Reproducir Muestra")
        self.btn_play.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.setStyleSheet("padding: 4px 10px; font-weight: 500;")
        self.btn_play.clicked.connect(lambda: self.on_play_sample_fn(self.speaker_data))

        # Botón Exportar Muestra Limpia
        self.btn_export_sample = QPushButton(" Exportar Muestra Limpia")
        self.btn_export_sample.setIcon(style.standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_export_sample.setStyleSheet("padding: 4px 10px; font-weight: bold; background-color: #0284c7; color: white;")
        self.btn_export_sample.clicked.connect(lambda: self.on_export_sample_fn(self.speaker_data))

        # Botón Ajustar en Línea de Tiempo
        self.btn_edit_timeline = QPushButton(" ✂️ Ajustar en Línea de Tiempo")
        self.btn_edit_timeline.setIcon(style.standardIcon(QStyle.SP_FileDialogContentsView))
        self.btn_edit_timeline.setStyleSheet("padding: 4px 10px; font-weight: 500; background-color: #334155; color: #f1f5f9;")
        if self.on_edit_timeline_fn:
            self.btn_edit_timeline.clicked.connect(lambda: self.on_edit_timeline_fn(self.speaker_data))

        # Botón Exportar Todo el Diálogo
        self.btn_export_full = QPushButton(" Exportar Diálogo Completo")
        self.btn_export_full.setIcon(style.standardIcon(QStyle.SP_ArrowDown))
        self.btn_export_full.setStyleSheet("padding: 4px 10px; font-weight: 500;")
        self.btn_export_full.clicked.connect(lambda: self.on_export_full_fn(self.speaker_data))

        h_actions.addWidget(self.btn_play)
        h_actions.addWidget(self.btn_edit_timeline)
        h_actions.addWidget(self.btn_export_sample)
        h_actions.addWidget(self.btn_export_full)
        h_actions.addStretch()

        layout.addLayout(h_actions)

    def set_playing(self, is_playing: bool):
        """Alterna el botón entre Reproducir y Detener según el estado de reproducción."""
        style = self.style()
        if is_playing:
            self.btn_play.setText(" Detener")
            self.btn_play.setIcon(style.standardIcon(QStyle.SP_MediaStop))
            self.btn_play.setStyleSheet("padding: 4px 10px; font-weight: bold; background-color: #dc2626; color: white;")
        else:
            self.btn_play.setText(" Reproducir Muestra")
            self.btn_play.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
            self.btn_play.setStyleSheet("padding: 4px 10px; font-weight: 500;")


class TabVoiceIsolation(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker: Optional[FFmpegWorker] = None
        self.diar_worker: Optional[DiarizationWorker] = None
        self.media_duration = 0.0
        self.diarization_results: Optional[dict] = None
        self.temp_sample_cache: Dict[int, str] = {}

        # Reproductor interno para vista previa de voz
        self.player = QMediaPlayer(self)
        self.player.stateChanged.connect(self._on_player_state_changed)
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.current_playing_spk_id: Optional[int] = None
        self.speaker_cards: Dict[int, SpeakerCard] = {}
        self._timeline_stop_ms: Optional[int] = None

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(10, 10, 10, 10)

        # 1. Selector de archivo de entrada
        group_input = QGroupBox("1. Video o Audio de Entrada")
        layout_input = QVBoxLayout(group_input)

        self.input_selector = FileSelector(
            placeholder="Seleccione o arrastre un video o audio con diálogo/entrevistas...",
            file_filter="Archivos Multimedia (*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;Todos (*.*)"
        )
        self.input_selector.file_selected.connect(self._on_file_selected)

        self.lbl_info = QLabel("Duración: --:--:-- | Códec de audio: No cargado | Frecuencia: -- Hz")
        self.lbl_info.setObjectName("lbl_meta")

        layout_input.addWidget(self.input_selector)
        layout_input.addWidget(self.lbl_info)
        form_layout.addWidget(group_input)

        # 2. Selección de Modo de Operación
        group_mode = QGroupBox("2. Modo de Operación")
        layout_mode = QVBoxLayout(group_mode)

        h_modes = QHBoxLayout()
        self.radio_mode_clean = QRadioButton("🎙️ Limpieza y Aislamiento Vocal (Pista de Voz Pura)")
        self.radio_mode_manual = QRadioButton("✂️ Selección Gráfica de Voz (Línea de Tiempo)")
        self.radio_mode_diar = QRadioButton("👥 Separar por Hablante y Extraer Muestras (Diarización)")
        self.radio_mode_clean.setChecked(True)

        self.radio_mode_clean.toggled.connect(self._on_operation_mode_changed)
        self.radio_mode_manual.toggled.connect(self._on_operation_mode_changed)
        self.radio_mode_diar.toggled.connect(self._on_operation_mode_changed)

        h_modes.addWidget(self.radio_mode_clean)
        h_modes.addWidget(self.radio_mode_manual)
        h_modes.addWidget(self.radio_mode_diar)
        h_modes.addStretch()
        layout_mode.addLayout(h_modes)

        # Panel de Opciones para Modo A: Limpieza Vocal
        self.panel_clean = QWidget()
        layout_clean = QVBoxLayout(self.panel_clean)
        layout_clean.setContentsMargins(0, 4, 0, 0)
        layout_clean.setSpacing(8)

        grid_clean = QGridLayout()
        grid_clean.setSpacing(8)

        lbl_prof = QLabel("Nivel de Limpieza:")
        self.combo_profile = QComboBox()
        self.combo_profile.addItem("Voz Estándar (Paso de banda 80Hz-11kHz + Reducción de ruido equilibrada)", "moderate")
        self.combo_profile.addItem("Acústica / Ligera (Conserva dinámica vocal en audios con poco ruido)", "light")
        self.combo_profile.addItem("Aislamiento Agresivo (Elimina ruidos de fondo intensos y murmullos)", "aggressive")
        self.combo_profile.addItem("Estudio y Locución (Limpieza + Normalización speechnorm integrada)", "studio")
        self.combo_profile.currentIndexChanged.connect(lambda _: self._update_command_preview())
        grid_clean.addWidget(lbl_prof, 0, 0)
        grid_clean.addWidget(self.combo_profile, 0, 1)

        lbl_clean_fmt = QLabel("Formato de Salida:")
        self.combo_clean_fmt = QComboBox()
        self.combo_clean_fmt.addItem("WAV - 16-bit PCM (Calidad CD Sin Pérdida)", "wav_16")
        self.combo_clean_fmt.addItem("WAV - 24-bit PCM (Estudio Alta Definición)", "wav_24")
        self.combo_clean_fmt.addItem("MP3 - 320 kbps (Máxima Fidelidad MP3)", "mp3_320k")
        self.combo_clean_fmt.addItem("FLAC (Comprimido Sin Pérdida)", "flac")
        self.combo_clean_fmt.currentIndexChanged.connect(self._update_output_suggestion)
        grid_clean.addWidget(lbl_clean_fmt, 1, 0)
        grid_clean.addWidget(self.combo_clean_fmt, 1, 1)

        layout_clean.addLayout(grid_clean)

        h_checks_clean = QHBoxLayout()
        self.chk_norm_speech = QCheckBox("Normalizar volumen vocal automáticamente (speechnorm)")
        self.chk_norm_speech.setChecked(True)
        self.chk_norm_speech.stateChanged.connect(lambda _: self._update_command_preview())

        self.chk_remove_silence = QCheckBox("Eliminar silencios largos y pausas")
        self.chk_remove_silence.setChecked(False)
        self.chk_remove_silence.stateChanged.connect(lambda _: self._update_command_preview())

        h_checks_clean.addWidget(self.chk_norm_speech)
        h_checks_clean.addWidget(self.chk_remove_silence)
        h_checks_clean.addStretch()
        layout_clean.addLayout(h_checks_clean)

        layout_mode.addWidget(self.panel_clean)

        # Panel de Opciones para Modo B: Selección Gráfica en Línea de Tiempo
        self.panel_manual = QWidget()
        layout_manual = QVBoxLayout(self.panel_manual)
        layout_manual.setContentsMargins(0, 4, 0, 0)
        layout_manual.setSpacing(8)

        # Widget de Forma de Onda y Línea de Tiempo interactiva
        self.timeline_widget = AudioSegmentSelectorWidget(self)
        self.timeline_widget.play_requested.connect(self._on_timeline_play_requested)
        self.timeline_widget.stop_requested.connect(self._on_timeline_stop_requested)
        self.timeline_widget.seek_requested.connect(self._on_timeline_seek_requested)
        self.timeline_widget.segments_updated.connect(lambda _: self._update_manual_command_preview())
        layout_manual.addWidget(self.timeline_widget)

        # Opciones de exportación para la selección manual
        grid_manual = QGridLayout()
        grid_manual.setSpacing(8)

        lbl_manual_fmt = QLabel("Formato de Exportación:")
        self.combo_manual_fmt = QComboBox()
        self.combo_manual_fmt.addItem("WAV - 16-bit PCM (Calidad Estudio Sin Pérdida)", "wav_16")
        self.combo_manual_fmt.addItem("WAV - 24-bit PCM (Estudio Alta Definición)", "wav_24")
        self.combo_manual_fmt.addItem("MP3 - 320 kbps (Máxima Fidelidad MP3)", "mp3_320k")
        self.combo_manual_fmt.addItem("FLAC (Comprimido Sin Pérdida)", "flac")
        self.combo_manual_fmt.currentIndexChanged.connect(self._update_output_suggestion)
        grid_manual.addWidget(lbl_manual_fmt, 0, 0)
        grid_manual.addWidget(self.combo_manual_fmt, 0, 1)

        layout_manual.addLayout(grid_manual)

        h_checks_manual = QHBoxLayout()
        self.chk_manual_cleanup = QCheckBox("Aplicar ecualización vocal y reducción de ruido a los tramos seleccionados")
        self.chk_manual_cleanup.setChecked(True)
        self.chk_manual_cleanup.stateChanged.connect(lambda _: self._update_manual_command_preview())
        h_checks_manual.addWidget(self.chk_manual_cleanup)
        h_checks_manual.addStretch()
        layout_manual.addLayout(h_checks_manual)

        lbl_manual_tips = QLabel(
            "💡 Consejo: Haga clic y arrastre con el ratón sobre la onda de audio para dibujar tramos de voz. "
            "Arrastre los bordes izquierdo/derecho para ajustar el inicio o fin con precisión, o use 'Quitar Selección' (Supr) "
            "para eliminar risas o ruidos no deseados."
        )
        lbl_manual_tips.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        lbl_manual_tips.setWordWrap(True)
        layout_manual.addWidget(lbl_manual_tips)

        self.panel_manual.setVisible(False)
        layout_mode.addWidget(self.panel_manual)

        # Panel de Opciones para Modo B: Diarización por Hablante
        self.panel_diar = QWidget()
        layout_diar = QVBoxLayout(self.panel_diar)
        layout_diar.setContentsMargins(0, 4, 0, 0)
        layout_diar.setSpacing(8)

        grid_diar = QGridLayout()
        grid_diar.setSpacing(8)

        lbl_spk_num = QLabel("Interlocutores:")
        h_spk_opt = QHBoxLayout()
        self.radio_spk_auto = QRadioButton("Autodetectar")
        self.radio_spk_fixed = QRadioButton("Fijar número:")
        self.spin_spk_count = QSpinBox()
        self.spin_spk_count.setRange(1, 6)
        self.spin_spk_count.setValue(2)
        self.spin_spk_count.setEnabled(False)

        self.radio_spk_auto.setChecked(True)
        self.radio_spk_auto.toggled.connect(lambda chk: self.spin_spk_count.setEnabled(not chk))

        h_spk_opt.addWidget(self.radio_spk_auto)
        h_spk_opt.addWidget(self.radio_spk_fixed)
        h_spk_opt.addWidget(self.spin_spk_count)
        h_spk_opt.addStretch()
        grid_diar.addWidget(lbl_spk_num, 0, 0)
        grid_diar.addLayout(h_spk_opt, 0, 1)

        lbl_sample_len = QLabel("Muestra Limpia:")
        self.combo_sample_target = QComboBox()
        self.combo_sample_target.addItem("Muestra condensada de 15 segundos (Ideal para Clonación / ElevenLabs)", 15.0)
        self.combo_sample_target.addItem("Muestra condensada de 30 segundos (Equilibrada / Recomendada)", 30.0)
        self.combo_sample_target.addItem("Muestra condensada de 60 segundos (Muestra Extensa)", 60.0)
        self.combo_sample_target.addItem("Todo el diálogo continuo de la persona", -1.0)
        self.combo_sample_target.setCurrentIndex(1)
        grid_diar.addWidget(lbl_sample_len, 1, 0)
        grid_diar.addWidget(self.combo_sample_target, 1, 1)

        lbl_diar_fmt = QLabel("Formato de Exportación:")
        self.combo_diar_fmt = QComboBox()
        self.combo_diar_fmt.addItem("WAV - 16-bit PCM (Calidad Estudio Sin Pérdida)", "wav_16")
        self.combo_diar_fmt.addItem("MP3 - 320 kbps (Máxima Fidelidad MP3)", "mp3_320k")
        self.combo_diar_fmt.addItem("FLAC (Lossless)", "flac")
        grid_diar.addWidget(lbl_diar_fmt, 2, 0)
        grid_diar.addWidget(self.combo_diar_fmt, 2, 1)

        layout_diar.addLayout(grid_diar)

        self.chk_diar_cleanup = QCheckBox("Aplicar filtro de limpieza y ecualización vocal a las muestras extraídas")
        self.chk_diar_cleanup.setChecked(True)
        layout_diar.addWidget(self.chk_diar_cleanup)

        self.panel_diar.setVisible(False)
        layout_mode.addWidget(self.panel_diar)

        form_layout.addWidget(group_mode)

        # 3. Carpeta de Salida
        group_out = QGroupBox("3. Carpeta de Destino")
        layout_out = QVBoxLayout(group_out)

        h_dest_mode = QHBoxLayout()
        self.radio_same_folder = QRadioButton("Misma carpeta que el archivo original")
        self.radio_base_folder = QRadioButton("Carpeta Base configurada")

        pref = config_manager.get_default_save_location()
        if pref == "base_dir":
            self.radio_base_folder.setChecked(True)
        else:
            self.radio_same_folder.setChecked(True)

        self.radio_same_folder.toggled.connect(lambda _: self._update_output_suggestion())
        self.radio_base_folder.toggled.connect(lambda _: self._update_output_suggestion())

        h_dest_mode.addWidget(self.radio_same_folder)
        h_dest_mode.addWidget(self.radio_base_folder)
        h_dest_mode.addStretch()
        layout_out.addLayout(h_dest_mode)

        # Selector de archivo de salida
        self.output_selector = FileSelector(
            is_save_dialog=True,
            placeholder="Ruta del archivo de audio resultante...",
            file_filter="Audio WAV (*.wav);;Audio MP3 (*.mp3);;Audio FLAC (*.flac)"
        )
        layout_out.addWidget(self.output_selector)
        form_layout.addWidget(group_out)

        # 4. Panel de Resultados de Diarización (Aparece tras analizar)
        self.group_results = QGroupBox("4. Interlocutores Detectados y Muestras de Voz")
        self.layout_results = QVBoxLayout(self.group_results)
        self.layout_results.setSpacing(10)

        self.lbl_results_summary = QLabel("Aún no se ha realizado el análisis de diarización.")
        self.lbl_results_summary.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        self.layout_results.addWidget(self.lbl_results_summary)

        self.cards_container = QWidget()
        self.layout_cards = QVBoxLayout(self.cards_container)
        self.layout_cards.setContentsMargins(0, 0, 0, 0)
        self.layout_cards.setSpacing(8)
        self.layout_results.addWidget(self.cards_container)

        self.group_results.setVisible(False)
        form_layout.addWidget(self.group_results)

        # 5. Barra de progreso y acciones de salida
        self.progress_bar = ProgressBarWithStatus()
        form_layout.addWidget(self.progress_bar)

        self.output_actions = OutputActionsWidget(file_label="Abrir Audio Limpio")
        form_layout.addWidget(self.output_actions)

        # Botones de ejecución
        h_exec = QHBoxLayout()
        self.btn_run = QPushButton(" Extraer y Limpiar Voz")
        self.btn_run.setObjectName("btn_run_primary")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.btn_cancel = QPushButton(" Cancelar")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        h_exec.addWidget(self.btn_run, 3)
        h_exec.addWidget(self.btn_cancel, 1)
        form_layout.addLayout(h_exec)

        form_layout.addStretch()

        # Configurar panel de consola y comando (ocultable / inferior o lateral)
        setup_tab_console_layout(
            self, form_widget, "Comando FFmpeg a ejecutar:",
            initial_bottom_sizes=[550, 180]
        )

        # Inicializar estado
        self.update_base_dir_display()

    def update_base_dir_display(self):
        """Actualiza el texto del radio button de carpeta base si ha cambiado."""
        base = config_manager.get_base_output_dir()
        if base:
            truncated = base if len(base) <= 35 else base[:16] + "..." + base[-16:]
            self.radio_base_folder.setText(f"Carpeta Base ({truncated})")
            self.radio_base_folder.setEnabled(True)
        else:
            self.radio_base_folder.setText("Carpeta Base (No configurada)")
            self.radio_base_folder.setEnabled(False)
            if self.radio_base_folder.isChecked():
                self.radio_same_folder.setChecked(True)

    def _on_operation_mode_changed(self):
        is_clean = self.radio_mode_clean.isChecked()
        is_manual = self.radio_mode_manual.isChecked()
        is_diar = self.radio_mode_diar.isChecked()

        self.panel_clean.setVisible(is_clean)
        self.panel_manual.setVisible(is_manual)
        self.panel_diar.setVisible(is_diar)

        if is_clean:
            self.btn_run.setText(" Extraer y Limpiar Voz")
            self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.output_selector.setVisible(True)
            self._update_output_suggestion()
            self._update_command_preview()
        elif is_manual:
            self.btn_run.setText(" Exportar Tramos Seleccionados")
            self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
            self.output_selector.setVisible(True)
            self._update_output_suggestion()
            self._update_manual_command_preview()
        else:
            self.btn_run.setText(" Analizar y Diarizar Hablantes")
            self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
            self.output_selector.setVisible(False)
            self.cmd_preview.set_command("Diarización con detección VAD acústica y clustering tímbrico en segundo plano.")

    def _on_file_selected(self, path: str):
        # Limpiar resultados, tarjetas y reproducción del archivo anterior
        self._cleanup_playback_procs()
        self._clear_speaker_cards()
        self.group_results.setVisible(False)
        self.diarization_results = None
        self.output_actions.hide_output()
        self.progress_bar.reset()
        self.progress_bar.set_status("Listo para procesar.")

        if not path or not os.path.isfile(path):
            self.lbl_info.setText("Duración: --:--:-- | Códec de audio: No cargado | Frecuencia: -- Hz")
            self.media_duration = 0.0
            if hasattr(self, "timeline_widget"):
                self.timeline_widget.canvas.set_media(0.0, None)
                self.timeline_widget.set_segments([])
            self._update_command_preview()
            return

        ffmpeg_path, ffprobe_path = self.get_ffmpeg_paths()
        info = ffmpeg_core.get_media_info(path, ffprobe_path)
        self.media_duration = info.get("duration", 0.0)

        acodec = info.get("audio_codec", "Desconocido").upper()
        sr = ""
        streams = info.get("audio_streams", [])
        if streams and "sample_rate" in streams[0]:
            sr = f" | {streams[0]['sample_rate']} Hz"

        dur_fmt = ffmpeg_core.format_seconds_to_time_str(self.media_duration)
        self.lbl_info.setText(f"Duración: {dur_fmt} | Códec: {acodec}{sr}")

        # Cargar forma de onda en la línea de tiempo interactiva
        if hasattr(self, "timeline_widget") and ffmpeg_path:
            self.timeline_widget.load_audio_file(ffmpeg_path, path, self.media_duration)

        self._update_output_suggestion()
        self._update_command_preview()

    def _update_output_suggestion(self):
        input_path = self.input_selector.get_path()
        if not input_path:
            return

        p = Path(input_path)
        stem = p.stem
        if self.radio_mode_manual.isChecked():
            fmt = self.combo_manual_fmt.currentData() if hasattr(self, "combo_manual_fmt") else "wav_16"
            ext = ".mp3" if "mp3" in fmt else (".flac" if fmt == "flac" else ".wav")
            new_filename = f"{stem}_voz_seleccionada{ext}"
        else:
            fmt = self.combo_clean_fmt.currentData() if hasattr(self, "combo_clean_fmt") else "wav_16"
            ext = ".mp3" if "mp3" in fmt else (".flac" if fmt == "flac" else ".wav")
            new_filename = f"{stem}_voz_limpia{ext}"

        if self.radio_base_folder.isChecked():
            base_dir = config_manager.get_base_output_dir()
            if base_dir and os.path.isdir(base_dir):
                target_dir = Path(base_dir)
            else:
                target_dir = p.parent
        else:
            target_dir = p.parent

        self.output_selector.set_path(str(target_dir / new_filename))
        self._update_command_preview()

    def _update_command_preview(self):
        if self.radio_mode_clean.isChecked():
            input_path = self.input_selector.get_path()
            out_path = self.output_selector.get_path()
            if not input_path or not out_path:
                self.cmd_preview.set_command("")
                return

            ffmpeg_path, _ = self.get_ffmpeg_paths()
            profile = self.combo_profile.currentData()
            fmt = self.combo_clean_fmt.currentData()
            norm = self.chk_norm_speech.isChecked()
            rem_sil = self.chk_remove_silence.isChecked()

            cmd = ffmpeg_core.build_voice_isolation_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                input_file=input_path,
                output_file=out_path,
                profile=profile,
                normalize_speech=norm,
                remove_silence=rem_sil,
                audio_format=fmt
            )
            self.cmd_preview.set_command(cmd)
        elif self.radio_mode_manual.isChecked():
            self._update_manual_command_preview()
        else:
            self.cmd_preview.set_command("Diarización con detección VAD acústica y clustering tímbrico en segundo plano.")

    def _update_manual_command_preview(self):
        if not self.radio_mode_manual.isChecked():
            return
        ffmpeg_path, _ = self.get_ffmpeg_paths()
        input_path = self.input_selector.get_path()
        out_path = self.output_selector.get_path()
        segs = self.timeline_widget.get_segments() if hasattr(self, "timeline_widget") else []
        if not input_path or not segs:
            self.cmd_preview.set_command("Seleccione un archivo y marque al menos un tramo de voz en la línea de tiempo gráfica.")
            return

        fmt = self.combo_manual_fmt.currentData() if hasattr(self, "combo_manual_fmt") else "wav_16"
        cleanup = self.chk_manual_cleanup.isChecked() if hasattr(self, "chk_manual_cleanup") else True

        try:
            cmd = ffmpeg_core.build_stitch_segments_command(
                ffmpeg_path=ffmpeg_path or "ffmpeg",
                input_file=input_path,
                segments=segs,
                output_file=out_path or "salida.wav",
                apply_cleanup=cleanup,
                audio_format=fmt
            )
            self.cmd_preview.set_command(cmd)
        except Exception as e:
            self.cmd_preview.set_command(f"Error generando comando: {e}")

    def _on_run_clicked(self):
        input_path = self.input_selector.get_path()
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, "Archivo no encontrado", "Por favor seleccione un archivo multimedia válido.")
            return

        ffmpeg_path, ffprobe_path = self.get_ffmpeg_paths()
        if not ffmpeg_path:
            QMessageBox.critical(self, "FFmpeg requerido", "No se encontró el ejecutable FFmpeg en el sistema o ruta local.")
            return

        if self.radio_mode_clean.isChecked():
            self._run_voice_cleaning(ffmpeg_path)
        elif self.radio_mode_manual.isChecked():
            self._run_manual_segments(ffmpeg_path)
        else:
            self._run_speaker_diarization(ffmpeg_path, ffprobe_path)

    def _run_manual_segments(self, ffmpeg_path: str):
        segs = self.timeline_widget.get_segments()
        if not segs:
            QMessageBox.warning(self, "Sin segmentos", "Debe marcar al menos un tramo de audio en la línea de tiempo.")
            return

        out_path = self.output_selector.get_path()
        if not out_path:
            QMessageBox.warning(self, "Ruta de salida requerida", "Por favor especifique la ruta del archivo de salida.")
            return

        fmt = self.combo_manual_fmt.currentData()
        cleanup = self.chk_manual_cleanup.isChecked()

        cmd = ffmpeg_core.build_stitch_segments_command(
            ffmpeg_path=ffmpeg_path,
            input_file=self.input_selector.get_path(),
            segments=segs,
            output_file=out_path,
            apply_cleanup=cleanup,
            audio_format=fmt
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.reset()
        self.progress_bar.set_status("Exportando y procesando tramos seleccionados...")
        self.log_console.clear_logs()

        tot_dur = sum((en - st) for st, en in segs)
        self.worker = FFmpegWorker(
            command=cmd,
            total_duration=tot_dur,
            output_path=out_path,
            parent=self
        )
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_clean_finished)
        self.worker.start()

    def _run_voice_cleaning(self, ffmpeg_path: str):
        out_path = self.output_selector.get_path()
        if not out_path:
            QMessageBox.warning(self, "Ruta de salida requerida", "Por favor especifique la ruta del archivo de salida.")
            return

        profile = self.combo_profile.currentData()
        fmt = self.combo_clean_fmt.currentData()
        norm = self.chk_norm_speech.isChecked()
        rem_sil = self.chk_remove_silence.isChecked()

        cmd = ffmpeg_core.build_voice_isolation_command(
            ffmpeg_path=ffmpeg_path,
            input_file=self.input_selector.get_path(),
            output_file=out_path,
            profile=profile,
            normalize_speech=norm,
            remove_silence=rem_sil,
            audio_format=fmt
        )

        self.output_actions.hide_output()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.reset()
        self.progress_bar.set_status("Iniciando aislamiento y limpieza vocal...")
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(
            command=cmd,
            total_duration=self.media_duration,
            output_path=out_path,
            parent=self
        )
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_clean_finished)
        self.worker.start()

    def _run_speaker_diarization(self, ffmpeg_path: str, ffprobe_path: str):
        num_spk = self.spin_spk_count.value() if self.radio_spk_fixed.isChecked() else None

        self.output_actions.hide_output()
        self.group_results.setVisible(False)
        self._clear_speaker_cards()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.reset()
        self.progress_bar.set_status("Iniciando análisis acústico de interlocutores...")
        self.log_console.clear_logs()

        self.diar_worker = DiarizationWorker(
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            input_file=self.input_selector.get_path(),
            num_speakers=num_spk,
            parent=self
        )
        self.diar_worker.progress_signal.connect(self._on_progress)
        self.diar_worker.log_signal.connect(self.log_console.append_log)
        self.diar_worker.finished_signal.connect(self._on_diar_finished)
        self.diar_worker.start()

    def _on_progress(self, pct: float, time_str: str, speed_info: str):
        detail = f"[{speed_info}]" if speed_info else ""
        self.progress_bar.set_progress(pct, time_str, detail)

    def _on_clean_finished(self, success: bool, message: str, output_path: str):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if success:
            self.progress_bar.set_progress(100.0, "Listo", "Completado")
            self.progress_bar.set_status("¡Aislamiento vocal completado exitosamente!")
            self.output_actions.show_output(output_path)
            QMessageBox.information(self, "Aislamiento Exitoso", f"Voz aislada guardada en:\n{output_path}")
        else:
            self.progress_bar.set_status("Error o cancelación en el proceso.")
            QMessageBox.critical(self, "Error en el procesamiento", message)

    def _on_diar_finished(self, success: bool, message: str, results: dict):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        if success:
            self.diarization_results = results
            num_spk = results.get("num_speakers", 0)
            tot_speech = results.get("total_speech_duration", 0.0)
            tot_fmt = ffmpeg_core.format_seconds_to_time_str(tot_speech)

            self.progress_bar.set_progress(100.0, "Listo", f"{num_spk} detectados")
            self.progress_bar.set_status(f"¡Diarización completada! {num_spk} interlocutores identificados.")

            self.lbl_results_summary.setText(
                f"Se detectaron {num_spk} interlocutores distintos con un total de {tot_fmt} de diálogo activo."
            )
            self._render_speaker_cards(results.get("speakers", []))
            self.group_results.setVisible(True)
        else:
            self.progress_bar.set_status("Diarización no completada.")
            QMessageBox.warning(self, "Diarización no completada", message)

    def _clear_speaker_cards(self):
        self.speaker_cards.clear()
        while self.layout_cards.count():
            item = self.layout_cards.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_speaker_cards(self, speakers: List[dict]):
        self._clear_speaker_cards()
        for spk in speakers:
            spk_id = spk.get("id", 1)
            card = SpeakerCard(
                speaker_data=spk,
                on_play_sample_fn=self._play_speaker_sample,
                on_export_sample_fn=self._export_speaker_sample,
                on_export_full_fn=self._export_speaker_full,
                on_edit_timeline_fn=self._edit_speaker_in_timeline,
                parent=self.cards_container
            )
            self.speaker_cards[spk_id] = card
            self.layout_cards.addWidget(card)

    def _edit_speaker_in_timeline(self, speaker_data: dict):
        """Carga los segmentos del interlocutor en la línea de tiempo gráfica para revisión y ajuste manual."""
        segs = speaker_data.get("segments", [])
        if not segs:
            QMessageBox.information(self, "Sin segmentos", "No hay intervenciones registradas para este hablante.")
            return

        self.timeline_widget.set_segments(segs)
        self.radio_mode_manual.setChecked(True)
        spk_name = speaker_data.get("name", "Hablante")
        self.progress_bar.set_status(f"Tramos de {spk_name} cargados en la Línea de Tiempo. Puede escuchar, ajustar bordes o borrar tramos no deseados.")

    def _on_timeline_play_requested(self, start_sec: float, end_sec: float):
        input_path = self.input_selector.get_path()
        if not input_path or not os.path.isfile(input_path):
            self.timeline_widget.set_playing_state(False)
            return

        try:
            self._timeline_stop_ms = int(end_sec * 1000)
            self.player.stop()
            content = QMediaContent(QUrl.fromLocalFile(input_path))
            self.player.setMedia(content)
            self.player.setPosition(int(start_sec * 1000))
            self.player.play()
            self.current_playing_spk_id = None
            self._update_speaker_cards_playing_state()
        except Exception:
            self.timeline_widget.set_playing_state(False)

    def _on_timeline_stop_requested(self):
        self.player.stop()
        self.timeline_widget.set_playing_state(False)
        self._timeline_stop_ms = None

    def _on_timeline_seek_requested(self, sec: float):
        self.player.setPosition(int(sec * 1000))

    def _on_player_position_changed(self, pos_ms: int):
        if self.radio_mode_manual.isChecked():
            self.timeline_widget.set_playhead_pos(pos_ms / 1000.0)
            if hasattr(self, "_timeline_stop_ms") and self._timeline_stop_ms is not None and pos_ms >= self._timeline_stop_ms:
                self.player.stop()
                self.timeline_widget.set_playing_state(False)
                self._timeline_stop_ms = None

    def _on_player_state_changed(self, state):
        """Maneja el fin o cambio de estado de la reproducción de audio."""
        if state != QMediaPlayer.PlayingState:
            self.current_playing_spk_id = None
            self._update_speaker_cards_playing_state()
            if hasattr(self, "timeline_widget"):
                self.timeline_widget.set_playing_state(False)

    def _update_speaker_cards_playing_state(self):
        """Sincroniza el botón de reproducir/detener en todas las tarjetas de interlocutor."""
        for spk_id, card in self.speaker_cards.items():
            card.set_playing(self.current_playing_spk_id == spk_id)

    def _play_speaker_sample(self, speaker_data: dict):
        """Genera y reproduce una vista previa temporal de la muestra de ese interlocutor, o la detiene si ya está activa."""
        spk_id = speaker_data.get("id", 1)

        # Si ya se está reproduciendo este hablante, detenerlo inmediatamente
        if self.current_playing_spk_id == spk_id and self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
            self.current_playing_spk_id = None
            self._update_speaker_cards_playing_state()
            self.progress_bar.set_status("Reproducción de muestra detenida.")
            return

        target_dur = self.combo_sample_target.currentData()
        if target_dur == 15.0:
            segs = speaker_data.get("sample_15") or speaker_data.get("segments", [])[:3]
        elif target_dur == 60.0:
            segs = speaker_data.get("sample_60") or speaker_data.get("segments", [])
        else:
            segs = speaker_data.get("sample_30") or speaker_data.get("segments", [])

        if not segs:
            QMessageBox.information(self, "Sin segmentos", "No hay segmentos disponibles para este interlocutor.")
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        cached = self.temp_sample_cache.get(spk_id)

        if not cached or not os.path.isfile(cached):
            import tempfile
            tmp_wav = os.path.join(tempfile.gettempdir(), f"preview_spk_{spk_id}_{os.getpid()}.wav")
            try:
                cmd = ffmpeg_core.build_stitch_segments_command(
                    ffmpeg_path=ffmpeg_path,
                    input_file=self.input_selector.get_path(),
                    segments=segs,
                    output_file=tmp_wav,
                    apply_cleanup=self.chk_diar_cleanup.isChecked(),
                    audio_format="wav_16"
                )
                startupinfo = None
                creationflags = 0
                if sys.platform.startswith("win"):
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )
                cached = tmp_wav
                self.temp_sample_cache[spk_id] = cached
            except Exception as e:
                QMessageBox.critical(self, "Error generando vista previa", f"No se pudo generar el audio: {e}")
                return

        # Reproducir con QMediaPlayer
        self.player.stop()
        content = QMediaContent(QUrl.fromLocalFile(cached))
        self.player.setMedia(content)
        self.player.play()
        self.current_playing_spk_id = spk_id
        self._update_speaker_cards_playing_state()
        self.progress_bar.set_status(f"Reproduciendo muestra de {speaker_data.get('name')}... (Haga clic en Detener para pausar)")

    def _export_speaker_sample(self, speaker_data: dict):
        """Exporta la muestra condensada pura (15s, 30s o 60s) de ese interlocutor."""
        target_dur = self.combo_sample_target.currentData()
        dur_tag = "15s" if target_dur == 15.0 else ("60s" if target_dur == 60.0 else "30s")
        if target_dur == -1.0:
            dur_tag = "dialogo"

        if target_dur == 15.0:
            segs = speaker_data.get("sample_15") or speaker_data.get("segments", [])
        elif target_dur == 60.0:
            segs = speaker_data.get("sample_60") or speaker_data.get("segments", [])
        elif target_dur == -1.0:
            segs = speaker_data.get("segments", [])
        else:
            segs = speaker_data.get("sample_30") or speaker_data.get("segments", [])

        self._export_segments_to_file(speaker_data, segs, suffix=f"muestra_{dur_tag}")

    def _export_speaker_full(self, speaker_data: dict):
        """Exporta todo el diálogo continuo pronunciado por esa persona."""
        segs = speaker_data.get("segments", [])
        self._export_segments_to_file(speaker_data, segs, suffix="dialogo_completo")

    def _export_segments_to_file(self, speaker_data: dict, segments: List[tuple], suffix: str):
        if not segments:
            QMessageBox.warning(self, "Sin segmentos", "No hay intervenciones registradas para exportar.")
            return

        spk_name = speaker_data.get("name", "Hablante").replace(" ", "_")
        in_p = Path(self.input_selector.get_path())
        fmt = self.combo_diar_fmt.currentData()
        ext = ".mp3" if "mp3" in fmt else (".flac" if fmt == "flac" else ".wav")

        default_name = f"{in_p.stem}_{spk_name}_{suffix}{ext}"

        if self.radio_base_folder.isChecked():
            base_dir = config_manager.get_base_output_dir()
            target_dir = Path(base_dir) if (base_dir and os.path.isdir(base_dir)) else in_p.parent
        else:
            target_dir = in_p.parent

        dest_candidate = str(target_dir / default_name)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar Audio de {speaker_data.get('name')}",
            dest_candidate,
            f"Audio (*{ext});;Todos (*.*)"
        )
        if not save_path:
            return

        ffmpeg_path, _ = self.get_ffmpeg_paths()
        cmd = ffmpeg_core.build_stitch_segments_command(
            ffmpeg_path=ffmpeg_path,
            input_file=self.input_selector.get_path(),
            segments=segments,
            output_file=save_path,
            apply_cleanup=self.chk_diar_cleanup.isChecked(),
            audio_format=fmt
        )

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.set_status(f"Exportando {spk_name}...")

        self.worker = FFmpegWorker(
            command=cmd,
            total_duration=sum((en - st) for st, en in segments),
            output_path=save_path,
            parent=self
        )
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_clean_finished)
        self.worker.start()

    def _on_cancel_clicked(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        if self.diar_worker and self.diar_worker.isRunning():
            self.diar_worker.cancel()
        self.progress_bar.set_status("Cancelando proceso...")
        self.btn_cancel.setEnabled(False)

    def _cleanup_playback_procs(self):
        """Detiene reproducción activa y elimina archivos temporales de vista previa."""
        if hasattr(self, "player") and self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self.current_playing_spk_id = None
        self._update_speaker_cards_playing_state()
        for p in list(self.temp_sample_cache.values()):
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        self.temp_sample_cache.clear()
