#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Comparar Videos (Inspección visual y análisis objetivo SSIM / PSNR)
Permite abrir o arrastrar dos videos (Referencia y Comprimido/Convertido) para:
1. Inspección técnica de metadatos (Resolución, FPS, Códecs, Bitrate, Reducción de Tamaño).
2. Generación de video comparativo (Pantalla dividida 50/50, Lado a Lado, Mapa de diferencias).
3. Cálculo matemático de similitud estructural (SSIM) y relación señal-ruido (PSNR).
4. Reproducción paralela sincronizada con reproductores del sistema.
"""

import os
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QMessageBox, QCheckBox, QStyle,
    QSplitter, QScrollArea, QFrame, QSizePolicy, QDialog, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer

from ui.widgets import (
    FileSelector, ProgressBarWithStatus, LogConsole,
    CommandPreviewWidget, OutputActionsWidget
)
import ffmpeg_core
import config_manager
from ffmpeg_worker import FFmpegWorker
from ui.compare_player import VideoComparePlayerDialog


def format_size_bytes(num_bytes: int) -> str:
    """Formatea bytes a KB, MB o GB legibles."""
    if num_bytes <= 0:
        return "0 KB"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


class ParallelPlayDialog(QDialog):
    """
    Diálogo para seleccionar el modo de reproducción paralela de videos:
    1. Reproductor integrado en 1 sola ventana con divisor interactivo y controles.
    2. Dos ventanas separadas colocadas lado a lado (FFplay).
    3. Reproductor del sistema operativo.
    """
    def __init__(self, parent=None, has_ffplay: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Modo de Reproducción en Paralelo")
        self.setMinimumWidth(680)
        self.choice = None
        self.remember = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        lbl_head = QLabel("<b>Seleccione cómo desea comparar ambos videos en pantalla:</b>")
        lbl_head.setStyleSheet("font-size: 13px; color: #f8fafc;")
        layout.addWidget(lbl_head)

        # Opción 1: Reproductor Integrado (1 Ventana)
        self.btn_opt_sync = QPushButton("Reproductor Integrado (1 Ventana con Cortina y Controles - Recomendado)", self)
        self.btn_opt_sync.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_opt_sync.setStyleSheet(
            "text-align: left; padding: 10px 14px; font-weight: bold; font-size: 13px; "
            "background-color: #1e3a8a; color: white; border: 1px solid #3b82f6; border-radius: 6px;"
        )
        self.btn_opt_sync.clicked.connect(lambda: self._choose("integrated"))
        layout.addWidget(self.btn_opt_sync)

        lbl_desc_sync = QLabel(
            "• Abre una sola ventana interactiva donde puedes arrastrar la línea divisoria (0% a 100%) sobre el video.\n"
            "• Alterna al instante entre Pantalla Dividida y Lado a Lado, con barra de búsqueda y controles de reproducción."
        )
        lbl_desc_sync.setWordWrap(True)
        lbl_desc_sync.setStyleSheet("color: #94a3b8; font-size: 11px; margin-left: 12px; margin-bottom: 4px;")
        layout.addWidget(lbl_desc_sync)

        # Opción 2: Dos Ventanas Separadas
        self.btn_opt_dual = QPushButton("Dos Ventanas Separadas (FFplay - Lado a Lado)", self)
        self.btn_opt_dual.setIcon(self.style().standardIcon(QStyle.SP_DesktopIcon))
        self.btn_opt_dual.setStyleSheet(
            "text-align: left; padding: 10px 14px; font-weight: bold; font-size: 13px; "
            "background-color: #1e293b; color: white; border: 1px solid #475569; border-radius: 6px;"
        )
        self.btn_opt_dual.clicked.connect(lambda: self._choose("dual"))
        layout.addWidget(self.btn_opt_dual)

        lbl_desc_dual = QLabel(
            "• Abre 2 ventanas independientes colocadas automáticamente una a la izquierda y otra a la derecha.\n"
            "• Ambas ventanas permanecen abiertas simultáneamente sin interferir ni cerrarse."
        )
        lbl_desc_dual.setWordWrap(True)
        lbl_desc_dual.setStyleSheet("color: #94a3b8; font-size: 11px; margin-left: 12px; margin-bottom: 4px;")
        layout.addWidget(lbl_desc_dual)

        # Opción 3: Reproductor Externo del Sistema
        self.btn_opt_os = QPushButton("Abrir en Reproductor del Sistema Operativo", self)
        self.btn_opt_os.setIcon(self.style().standardIcon(QStyle.SP_DriveCDIcon))
        self.btn_opt_os.setStyleSheet(
            "text-align: left; padding: 8px 12px; font-size: 12px; "
            "background-color: transparent; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px;"
        )
        self.btn_opt_os.clicked.connect(lambda: self._choose("os"))
        layout.addWidget(self.btn_opt_os)

        lbl_desc_os = QLabel(
            "• Envía los archivos al reproductor predeterminado del sistema (Nota: Dragon Player y Totem solo admiten 1 ventana activa a la vez)."
        )
        lbl_desc_os.setWordWrap(True)
        lbl_desc_os.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 12px; margin-bottom: 4px;")
        layout.addWidget(lbl_desc_os)

        if not has_ffplay:
            self.btn_opt_dual.setEnabled(False)

        layout.addSpacing(6)

        # Casilla de verificación: Recordar opción
        self.chk_remember = QCheckBox("Recordar esta opción y usarla directamente al pulsar el botón", self)
        self.chk_remember.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.chk_remember)

        # Botón Cancelar
        h_cancel = QHBoxLayout()
        h_cancel.addStretch()
        btn_cancel = QPushButton("Cancelar", self)
        btn_cancel.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        btn_cancel.clicked.connect(self.reject)
        h_cancel.addWidget(btn_cancel)
        layout.addLayout(h_cancel)

    def _choose(self, choice_key: str):
        self.choice = choice_key
        self.remember = self.chk_remember.isChecked()
        self.accept()


class TabCompare(QWidget):
    def __init__(self, get_ffmpeg_paths_fn, parent=None):
        super().__init__(parent)
        self.get_ffmpeg_paths = get_ffmpeg_paths_fn
        self.worker = None
        self.worker_mode = "video"  # "video" o "metrics"

        self.info_a = None
        self.info_b = None
        self._live_procs = []
        self._dual_procs = []

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(6, 6, 6, 6)

        # Divisor vertical interactivo (Controles arriba, Consola abajo)
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)

        # Panel superior compuesto (Scroll de opciones + Barra de acción fija)
        top_pane = QWidget(self)
        layout_pane = QVBoxLayout(top_pane)
        layout_pane.setContentsMargins(0, 0, 0, 4)
        layout_pane.setSpacing(6)

        # Panel con scroll fluido para las secciones de configuración
        top_scroll = QScrollArea(top_pane)
        top_scroll.setWidgetResizable(True)
        top_scroll.setFrameShape(QFrame.NoFrame)

        top_container = QWidget()
        layout_top = QVBoxLayout(top_container)
        layout_top.setContentsMargins(0, 4, 0, 4)
        layout_top.setSpacing(10)

        # 1. Videos a Comparar (Video A y Video B)
        group_inputs = QGroupBox("1. Videos a Comparar (Seleccione o arrastre ambos archivos)")
        layout_inputs = QVBoxLayout(group_inputs)
        layout_inputs.setSpacing(8)

        # Contenedor lado a lado para Video A y Video B
        h_videos = QHBoxLayout()
        h_videos.setSpacing(12)

        # Columna Video A
        v_box_a = QVBoxLayout()
        lbl_title_a = QLabel("<b>Video A (Referencia / Original):</b>")
        lbl_title_a.setTextFormat(Qt.RichText)
        lbl_title_a.setStyleSheet("color: #38bdf8;")
        self.input_a = FileSelector(
            placeholder="Seleccione o arrastre el Video Original A...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts);;Todos (*.*)"
        )
        self.input_a.file_selected.connect(self._on_file_a_selected)

        self.lbl_meta_a = QLabel("Sin archivo cargado")
        self.lbl_meta_a.setObjectName("lbl_meta")
        self.lbl_meta_a.setStyleSheet("color: #94a3b8; font-size: 11px;")

        v_box_a.addWidget(lbl_title_a)
        v_box_a.addWidget(self.input_a)
        v_box_a.addWidget(self.lbl_meta_a)
        h_videos.addLayout(v_box_a, 1)

        # Columna Video B
        v_box_b = QVBoxLayout()
        lbl_title_b = QLabel("<b>Video B (Procesado / Comprimido / Convertido):</b>")
        lbl_title_b.setTextFormat(Qt.RichText)
        lbl_title_b.setStyleSheet("color: #a78bfa;")
        self.input_b = FileSelector(
            placeholder="Seleccione o arrastre el Video Comparado B...",
            file_filter="Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts);;Todos (*.*)"
        )
        self.input_b.file_selected.connect(self._on_file_b_selected)

        self.lbl_meta_b = QLabel("Sin archivo cargado")
        self.lbl_meta_b.setObjectName("lbl_meta")
        self.lbl_meta_b.setStyleSheet("color: #94a3b8; font-size: 11px;")

        v_box_b.addWidget(lbl_title_b)
        v_box_b.addWidget(self.input_b)
        v_box_b.addWidget(self.lbl_meta_b)
        h_videos.addLayout(v_box_b, 1)

        layout_inputs.addLayout(h_videos)

        # Barra resumen de diferencias técnicas (Tamaño, Bitrate, Resolución)
        self.banner_diff = QLabel("Cargue ambos videos para analizar las diferencias técnicas de compresión.")
        self.banner_diff.setWordWrap(True)
        self.banner_diff.setStyleSheet(
            "background-color: #1e2235; border: 1px solid #334155; border-radius: 6px; "
            "padding: 6px 10px; color: #cbd5e1; font-size: 12px;"
        )
        self.lbl_diff_summary = self.banner_diff
        layout_inputs.addWidget(self.banner_diff)

        layout_top.addWidget(group_inputs)

        # 2. Modo de Comparación
        group_mode = QGroupBox("2. Método de Comparación Visual")
        layout_mode = QVBoxLayout(group_mode)

        h_mode_row = QHBoxLayout()
        h_mode_row.addWidget(QLabel("Modo de visualización:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Pantalla Dividida 50/50 (Mitad A / Mitad B con Divisor)", "split_screen")
        self.combo_mode.addItem("Lado a Lado (Side-by-Side con Etiquetas A y B)", "side_by_side")
        self.combo_mode.addItem("Mapa de Diferencias (Negro = Idéntico | Color = Cambios)", "diff")
        self.combo_mode.currentIndexChanged.connect(lambda _: self._update_command_preview())
        h_mode_row.addWidget(self.combo_mode, 2)

        h_mode_row.addWidget(QLabel("Resolución:"))
        self.combo_resolution = QComboBox()
        self.combo_resolution.addItem("Automática (Resolución del Video A)", "auto")
        self.combo_resolution.addItem("1080p Full HD (1920x1080)", "1920x1080")
        self.combo_resolution.addItem("720p HD (1280x720)", "1280x720")
        self.combo_resolution.addItem("Original A x2 (Lado a Lado Completo)", "double")
        self.combo_resolution.currentIndexChanged.connect(lambda _: self._update_command_preview())
        h_mode_row.addWidget(self.combo_resolution, 1)

        layout_mode.addLayout(h_mode_row)

        lbl_mode_desc = QLabel(
            "• Pantalla Dividida: Muestra la mitad izquierda del original y la derecha del comprimido. Ideal para comparar nitidez y grano.\n"
            "• Lado a Lado: Muestra ambos videos completos uno junto al otro para comparar color y balance general.\n"
            "• Mapa de Diferencias: Fondo negro donde los píxeles son 100% idénticos; resalta en brillo artefactos de compresión."
        )
        lbl_mode_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_mode.addWidget(lbl_mode_desc)

        layout_top.addWidget(group_mode)

        # 3. Archivo de Salida para el Video Comparativo
        group_out = QGroupBox("3. Archivo Resultante de la Comparación")
        layout_out = QVBoxLayout(group_out)

        h_sub_opt = QHBoxLayout()
        self.chk_use_base = QCheckBox("Guardar en Carpeta Base configurada")
        self.chk_use_base.setChecked(True)
        self.chk_use_base.stateChanged.connect(self._on_use_base_changed)
        h_sub_opt.addWidget(self.chk_use_base)
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

        self.output_selector = FileSelector(
            placeholder="Ruta y nombre del video de comparación resultante...",
            is_save_dialog=True,
            file_filter="Video MP4 (*.mp4);;Video MKV (*.mkv);;Todos (*.*)"
        )
        self.output_selector.file_selected.connect(lambda _: self._update_command_preview())
        layout_out.addWidget(self.output_selector)

        layout_top.addWidget(group_out)

        # 4. Ficha de Resultados Objetivos SSIM / PSNR
        self.card_metrics = QGroupBox("4. Métricas Objetivas de Calidad (SSIM y PSNR)")
        layout_metrics = QVBoxLayout(self.card_metrics)

        h_scores = QHBoxLayout()
        self.lbl_ssim_score = QLabel("<b>SSIM:</b> --")
        self.lbl_ssim_score.setStyleSheet("font-size: 14px; color: #38bdf8;")

        self.lbl_psnr_score = QLabel("<b>PSNR:</b> --")
        self.lbl_psnr_score.setStyleSheet("font-size: 14px; color: #a78bfa;")

        self.lbl_rating_badge = QLabel("Sin análisis ejecutado")
        self.lbl_rating_badge.setStyleSheet(
            "background-color: #1e293b; color: #94a3b8; font-weight: bold; "
            "padding: 4px 10px; border-radius: 4px; font-size: 12px;"
        )

        h_scores.addWidget(self.lbl_ssim_score)
        h_scores.addWidget(self.lbl_psnr_score)
        h_scores.addWidget(self.lbl_rating_badge)
        h_scores.addStretch()
        layout_metrics.addLayout(h_scores)

        self.lbl_metrics_detail = QLabel(
            "Haz clic en 'Calcular Métricas SSIM / PSNR' para medir matemáticamente la fidelidad visual de la compresión."
        )
        self.lbl_metrics_detail.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_metrics.addWidget(self.lbl_metrics_detail)

        layout_top.addWidget(self.card_metrics)

        # 5. Vista Previa del Comando FFmpeg
        self.cmd_preview = CommandPreviewWidget("Comando FFmpeg a ejecutar:", self)
        layout_top.addWidget(self.cmd_preview)

        top_scroll.setWidget(top_container)
        layout_pane.addWidget(top_scroll, 1)

        # 6. Barra de Progreso y Acciones (fija)
        self.progress_widget = ProgressBarWithStatus(self)
        layout_pane.addWidget(self.progress_widget)

        self.output_actions = OutputActionsWidget(file_label="Abrir Video Comparativo", parent=self)
        layout_pane.addWidget(self.output_actions)

        # 7. Botones de Acción (fijos)
        h_btns = QHBoxLayout()
        h_btns.setSpacing(8)

        self.btn_metrics = QPushButton("Calcular Métricas SSIM / PSNR", self)
        self.btn_metrics.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.btn_metrics.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold; padding: 7px 12px;")
        self.btn_metrics.clicked.connect(self._start_metrics)

        self.btn_run = QPushButton("Generar Video Comparativo", self)
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_run.clicked.connect(self._start_rendering)

        self.btn_play_both = QPushButton("Reproducir Ambos en Paralelo", self)
        self.btn_play_both.setIcon(self.style().standardIcon(QStyle.SP_MediaSeekForward))
        self.btn_play_both.setToolTip("Reproduce ambos videos en paralelo (Visor sincronizado en 1 ventana o en 2 ventanas). Clic derecho para cambiar modo.")
        self.btn_play_both.clicked.connect(self._play_both)
        self.btn_play_both.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_play_both.customContextMenuRequested.connect(self._show_play_context_menu)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)

        # Alias descriptivos para APIs y tests
        self.btn_gen_compare = self.btn_run
        self.btn_calc_metrics = self.btn_metrics

        h_btns.addWidget(self.btn_metrics, 2)
        h_btns.addWidget(self.btn_run, 2)
        h_btns.addWidget(self.btn_play_both, 2)
        h_btns.addWidget(self.btn_cancel, 1)
        layout_pane.addLayout(h_btns)

        self.splitter.addWidget(top_pane)

        # Panel inferior: Consola de Salida FFmpeg
        self.log_console = LogConsole(self)
        self.log_console.setMinimumHeight(60)
        self.splitter.addWidget(self.log_console)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([500, 150])
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 2)

        layout.addWidget(self.splitter)

        self.update_base_dir_display()

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
        self._update_output_suggestion()

    def _on_use_base_changed(self):
        use_base = self.chk_use_base.isChecked()
        self.icon_base_dir.setVisible(use_base)
        self.lbl_base_info.setVisible(use_base)
        self._update_output_suggestion()

    def _on_file_a_selected(self, path: str):
        path = config_manager.clean_file_path(path)
        if not path or not os.path.isfile(path):
            self.lbl_meta_a.setText("Sin archivo cargado")
            self.info_a = None
            self._update_summary()
            self._update_command_preview()
            return

        _, ffprobe_p = self.get_ffmpeg_paths()
        self.info_a = ffmpeg_core.get_media_info(path, ffprobe_p)
        size_str = format_size_bytes(self.info_a.get("size_bytes", 0))

        v_codec = self.info_a.get("video_codec", "N/D").upper()
        a_codec = self.info_a.get("audio_codec", "N/D").upper()
        res_str = f"{self.info_a.get('width', 0)}x{self.info_a.get('height', 0)}"
        bitrate_kb = self.info_a.get("bitrate_kbps", 0)

        self.lbl_meta_a.setText(
            f"<b>{res_str}</b> | {self.info_a.get('fps', 0):.2f} fps | {v_codec} / {a_codec} | "
            f"<b>{size_str}</b> | {bitrate_kb} kbps | {self.info_a.get('duration_str', '00:00')}"
        )
        self._update_output_suggestion()
        self._update_summary()
        self._update_command_preview()

    def _on_file_b_selected(self, path: str):
        path = config_manager.clean_file_path(path)
        if not path or not os.path.isfile(path):
            self.lbl_meta_b.setText("Sin archivo cargado")
            self.info_b = None
            self._update_summary()
            self._update_command_preview()
            return

        _, ffprobe_p = self.get_ffmpeg_paths()
        self.info_b = ffmpeg_core.get_media_info(path, ffprobe_p)
        size_str = format_size_bytes(self.info_b.get("size_bytes", 0))

        v_codec = self.info_b.get("video_codec", "N/D").upper()
        a_codec = self.info_b.get("audio_codec", "N/D").upper()
        res_str = f"{self.info_b.get('width', 0)}x{self.info_b.get('height', 0)}"
        bitrate_kb = self.info_b.get("bitrate_kbps", 0)

        self.lbl_meta_b.setText(
            f"<b>{res_str}</b> | {self.info_b.get('fps', 0):.2f} fps | {v_codec} / {a_codec} | "
            f"<b>{size_str}</b> | {bitrate_kb} kbps | {self.info_b.get('duration_str', '00:00')}"
        )
        self._update_output_suggestion()
        self._update_summary()
        self._update_command_preview()

    def _update_summary(self):
        if not self.info_a or not self.info_b:
            self.banner_diff.setText("Cargue ambos videos para analizar las diferencias técnicas de compresión.")
            self.banner_diff.setStyleSheet(
                "background-color: #1e2235; border: 1px solid #334155; border-radius: 6px; "
                "padding: 6px 10px; color: #cbd5e1; font-size: 12px;"
            )
            return

        size_a = self.info_a.get("size_bytes", 0)
        size_b = self.info_b.get("size_bytes", 0)
        diff_bytes = size_b - size_a
        diff_pct = (diff_bytes / size_a * 100.0) if size_a > 0 else 0.0

        if diff_bytes < 0:
            size_html = f"<span style='color: #4ade80; font-weight: bold;'>Ahorro de tamaño: {diff_pct:.1f}% ({format_size_bytes(size_a)} -> {format_size_bytes(size_b)})</span>"
        else:
            size_html = f"<span style='color: #f87171; font-weight: bold;'>Incremento de tamaño: +{diff_pct:.1f}% ({format_size_bytes(size_a)} -> {format_size_bytes(size_b)})</span>"

        res_a = f"{self.info_a.get('width', 0)}x{self.info_a.get('height', 0)}"
        res_b = f"{self.info_b.get('width', 0)}x{self.info_b.get('height', 0)}"
        res_html = f"Resolución: <b>{res_a}</b> vs <b>{res_b}</b>"

        codec_a = self.info_a.get("video_codec", "N/D").upper()
        codec_b = self.info_b.get("video_codec", "N/D").upper()
        codec_html = f"Códec: <b>{codec_a}</b> vs <b>{codec_b}</b>"

        self.banner_diff.setText(f"{size_html} &nbsp;|&nbsp; {res_html} &nbsp;|&nbsp; {codec_html}")
        self.banner_diff.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #2563eb; border-radius: 6px; "
            "padding: 8px 12px; color: #f1f5f9; font-size: 12px;"
        )

    def _update_output_suggestion(self):
        path_a = self.input_a.get_path()
        path_b = self.input_b.get_path()
        if not path_a:
            self.output_selector.set_path("")
            self.cmd_preview.set_command("")
            return

        stem_a = Path(path_a).stem
        stem_b = Path(path_b).stem if path_b else "comparado"
        out_name = f"{stem_a}_vs_{stem_b}_comparacion.mp4"

        if self.chk_use_base.isChecked():
            base_dir = config_manager.get_base_output_dir()
            suggested = os.path.join(base_dir, out_name)
        else:
            suggested = str(Path(path_a).parent / out_name)

        self.output_selector.set_path(suggested)
        self._update_command_preview()

    def _get_target_resolution(self) -> tuple:
        res_mode = self.combo_resolution.currentData()
        if res_mode == "1920x1080":
            return 1920, 1080
        elif res_mode == "1280x720":
            return 1280, 720
        elif res_mode == "double" and self.info_a:
            w = self.info_a.get("width", 1280) * 2
            h = self.info_a.get("height", 720)
            return w, h
        elif self.info_a:
            w = self.info_a.get("width", 1280)
            h = self.info_a.get("height", 720)
            return (w if w > 0 else 1280), (h if h > 0 else 720)
        return 1280, 720

    def _update_command_preview(self):
        path_a = config_manager.clean_file_path(self.input_a.get_path())
        path_b = config_manager.clean_file_path(self.input_b.get_path())
        out_path = config_manager.clean_file_path(self.output_selector.get_path())

        if not path_a or not path_b:
            self.cmd_preview.set_command("")
            return

        ffmpeg_p, _ = self.get_ffmpeg_paths()
        mode = self.combo_mode.currentData()
        target_w, target_h = self._get_target_resolution()

        try:
            cmd = ffmpeg_core.build_compare_video_command(
                ffmpeg_path=ffmpeg_p or "ffmpeg",
                video_a=path_a,
                video_b=path_b,
                output_file=out_path or "comparacion.mp4",
                mode=mode,
                target_width=target_w,
                target_height=target_h
            )
            self.cmd_preview.set_command(cmd)
        except Exception as e:
            self.cmd_preview.set_command(f"# Vista previa no disponible: {e}")

    def _play_both(self):
        """Abre ambos videos para inspección en paralelo."""
        path_a = config_manager.clean_file_path(self.input_a.get_path())
        path_b = config_manager.clean_file_path(self.input_b.get_path())
        if not path_a or not os.path.isfile(path_a):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video A existente.")
            return
        if not path_b or not os.path.isfile(path_b):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video B existente.")
            return

        pref = config_manager.get_parallel_playback_pref()
        ffmpeg_p, _ = self.get_ffmpeg_paths()
        ffplay_p = ffmpeg_core.get_ffplay_path(ffmpeg_p)

        if pref in ("integrated", "sync"):
            self._play_integrated(path_a, path_b, ffmpeg_p)
        elif pref == "dual":
            if not ffplay_p:
                self._play_integrated(path_a, path_b, ffmpeg_p)
            else:
                self._play_dual_windows(path_a, path_b, ffplay_p)
        elif pref == "os":
            self._play_os_player(path_a, path_b)
        else:  # "ask"
            dlg = ParallelPlayDialog(self, has_ffplay=bool(ffplay_p))
            if dlg.exec_() != QDialog.Accepted or not dlg.choice:
                return
            if dlg.remember:
                config_manager.set_parallel_playback_pref(dlg.choice)
            self._execute_play_mode(dlg.choice, path_a, path_b, ffmpeg_p, ffplay_p)

    def _execute_play_mode(
        self, mode: str, path_a: str = None, path_b: str = None,
        ffmpeg_p: str = None, ffplay_p: str = None
    ):
        if not path_a:
            path_a = config_manager.clean_file_path(self.input_a.get_path())
        if not path_b:
            path_b = config_manager.clean_file_path(self.input_b.get_path())
        if not path_a or not os.path.isfile(path_a) or not path_b or not os.path.isfile(path_b):
            QMessageBox.warning(self, "Archivo faltante", "Asegúrese de cargar ambos videos antes de reproducir.")
            return

        if not ffmpeg_p:
            ffmpeg_p, _ = self.get_ffmpeg_paths()
        if not ffplay_p:
            ffplay_p = ffmpeg_core.get_ffplay_path(ffmpeg_p)

        self._cleanup_playback_procs()

        if mode in ("integrated", "sync"):
            self._play_integrated(path_a, path_b, ffmpeg_p)
        elif mode == "dual":
            if not ffplay_p:
                QMessageBox.warning(
                    self, "FFplay requerido",
                    "No se encontró el ejecutable 'ffplay' para abrir dos ventanas independientes."
                )
                return
            self._play_dual_windows(path_a, path_b, ffplay_p)
        else:
            self._play_os_player(path_a, path_b)

    def _play_integrated(self, path_a: str, path_b: str, ffmpeg_p: str):
        """Abre el Reproductor Comparativo de Video en una sola ventana integrada."""
        player = VideoComparePlayerDialog(self, video_a=path_a, video_b=path_b, ffmpeg_path=ffmpeg_p)
        tab_mode = self.combo_mode.currentData()
        if tab_mode == "side_by_side":
            player._set_mode("side_by_side")
        else:
            player._set_mode("split")
        player.exec_()

    def _play_synchronized(self, path_a: str, path_b: str, ffmpeg_p: str, ffplay_p: str):
        """Inicia visor interactivo en tiempo real con FFmpeg y FFplay."""
        mode = self.combo_mode.currentData()
        target_w, target_h = self._get_target_resolution()
        cmd_ffmpeg = ffmpeg_core.build_compare_live_stream_command(
            ffmpeg_p, path_a, path_b, mode=mode, target_width=target_w, target_height=target_h
        )
        mode_text = self.combo_mode.currentText().split("(")[0].strip()
        win_title = f"Comparación Sincronizada ({mode_text}) - [Espacio: Pausa | Flechas: Buscar | F: Pantalla Completa]"
        cmd_ffplay = ffmpeg_core.build_ffplay_live_stream_command(ffplay_p, window_title=win_title)

        try:
            p_ffmpeg = subprocess.Popen(
                cmd_ffmpeg,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            p_ffplay = subprocess.Popen(
                cmd_ffplay,
                stdin=p_ffmpeg.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            p_ffmpeg.stdout.close()
            self._live_procs.append(p_ffmpeg)
            self._live_procs.append(p_ffplay)
        except Exception as e:
            QMessageBox.critical(self, "Error al reproducir", f"No se pudo iniciar el visor sincronizado:\n{e}")

    def _play_dual_windows(self, path_a: str, path_b: str, ffplay_p: str):
        """Abre dos ventanas independientes de FFplay una al lado de la otra."""
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            sw, sh, sx, sy = geo.width(), geo.height(), geo.x(), geo.y()
        else:
            sw, sh, sx, sy = 1920, 1080, 0, 0

        cmd_a, cmd_b = ffmpeg_core.build_ffplay_dual_window_commands(
            ffplay_p, path_a, path_b, screen_width=sw, screen_height=sh, screen_x=sx, screen_y=sy
        )
        try:
            p_a = subprocess.Popen(
                cmd_a,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            p_b = subprocess.Popen(
                cmd_b,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self._dual_procs.append(p_a)
            self._dual_procs.append(p_b)
        except Exception as e:
            QMessageBox.critical(self, "Error al reproducir", f"No se pudieron abrir las dos ventanas de FFplay:\n{e}")

    def _play_os_player(self, path_a: str, path_b: str):
        """Abre los videos en el reproductor predeterminado del SO."""
        config_manager.open_path_in_os(path_a, is_directory=False)
        QTimer.singleShot(350, lambda: config_manager.open_path_in_os(path_b, is_directory=False))

    def _cleanup_playback_procs(self):
        for p in getattr(self, "_live_procs", []):
            try:
                if p.poll() is None:
                    p.terminate()
                    p.kill()
                    p.wait(timeout=0.2)
            except Exception:
                pass
        self._live_procs = []
        for p in getattr(self, "_dual_procs", []):
            try:
                if p.poll() is None:
                    p.terminate()
                    p.kill()
                    p.wait(timeout=0.2)
            except Exception:
                pass
        self._dual_procs = []

    def _show_play_context_menu(self, pos):
        menu = QMenu(self)
        act_int = menu.addAction(self.style().standardIcon(QStyle.SP_MediaPlay), "Reproductor Integrado (1 Ventana - Cortina Deslizante)")
        act_int.triggered.connect(lambda: self._execute_play_mode("integrated"))

        act_dual = menu.addAction(self.style().standardIcon(QStyle.SP_DesktopIcon), "Dos Ventanas Separadas (FFplay - Lado a Lado)")
        act_dual.triggered.connect(lambda: self._execute_play_mode("dual"))

        act_os = menu.addAction(self.style().standardIcon(QStyle.SP_DriveCDIcon), "Abrir en Reproductor del Sistema")
        act_os.triggered.connect(lambda: self._execute_play_mode("os"))

        menu.addSeparator()
        act_reset = menu.addAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Preguntar siempre (Mostrar diálogo de opciones)")
        act_reset.triggered.connect(self._reset_play_pref)

        menu.exec_(self.btn_play_both.mapToGlobal(pos))

    def _reset_play_pref(self):
        config_manager.set_parallel_playback_pref("ask")
        QMessageBox.information(
            self, "Preferencia restablecida",
            "Ahora la aplicación volverá a preguntarle cómo desea reproducir la comparación al pulsar el botón."
        )

    def closeEvent(self, event):
        self._cleanup_playback_procs()
        super().closeEvent(event)

    def _start_metrics(self):
        """Calcula métricas de calidad objetiva SSIM y PSNR."""
        path_a = config_manager.clean_file_path(self.input_a.get_path())
        path_b = config_manager.clean_file_path(self.input_b.get_path())
        if not path_a or not os.path.isfile(path_a):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video Original A.")
            return
        if not path_b or not os.path.isfile(path_b):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video Comparado B.")
            return

        ffmpeg_p, _ = self.get_ffmpeg_paths()
        if not ffmpeg_p or not os.path.isfile(ffmpeg_p):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        self.worker_mode = "metrics"
        target_w, target_h = self._get_target_resolution()
        cmd = ffmpeg_core.build_compare_metrics_command(
            ffmpeg_path=ffmpeg_p,
            video_a=path_a,
            video_b=path_b,
            target_width=target_w,
            target_height=target_h
        )

        total_dur = max(
            self.info_a.get("duration", 0.0) if self.info_a else 0.0,
            self.info_b.get("duration", 0.0) if self.info_b else 0.0
        )

        self._set_ui_busy(True)
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=total_dur, output_path="")
        self.worker.progress_signal.connect(self.progress_widget.set_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _start_rendering(self):
        """Genera el video de comparación visual."""
        path_a = config_manager.clean_file_path(self.input_a.get_path())
        path_b = config_manager.clean_file_path(self.input_b.get_path())
        out_file = config_manager.clean_file_path(self.output_selector.get_path())

        if not path_a or not os.path.isfile(path_a):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video Original A.")
            return
        if not path_b or not os.path.isfile(path_b):
            QMessageBox.warning(self, "Archivo faltante", "Seleccione el Video Comparado B.")
            return
        if not out_file:
            QMessageBox.warning(self, "Ruta de salida", "Especifique el archivo resultante.")
            return

        out_dir = os.path.dirname(out_file)
        if out_dir:
            config_manager.ensure_dir_exists(out_dir)

        ffmpeg_p, _ = self.get_ffmpeg_paths()
        if not ffmpeg_p or not os.path.isfile(ffmpeg_p):
            QMessageBox.critical(self, "FFmpeg no encontrado", "No se encontró el ejecutable FFmpeg.")
            return

        self.worker_mode = "video"
        mode = self.combo_mode.currentData()
        target_w, target_h = self._get_target_resolution()

        cmd = ffmpeg_core.build_compare_video_command(
            ffmpeg_path=ffmpeg_p,
            video_a=path_a,
            video_b=path_b,
            output_file=out_file,
            mode=mode,
            target_width=target_w,
            target_height=target_h
        )

        total_dur = max(
            self.info_a.get("duration", 0.0) if self.info_a else 0.0,
            self.info_b.get("duration", 0.0) if self.info_b else 0.0
        )

        self._set_ui_busy(True)
        self.output_actions.hide_output()
        self.progress_widget.reset()
        self.log_console.clear_logs()

        self.worker = FFmpegWorker(cmd, total_duration=total_dur, output_path=out_file)
        self.worker.progress_signal.connect(self.progress_widget.set_progress)
        self.worker.log_signal.connect(self.log_console.append_log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()

    def _set_ui_busy(self, busy: bool):
        self.btn_run.setEnabled(not busy)
        self.btn_metrics.setEnabled(not busy)
        self.btn_play_both.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)

    def _on_finished(self, success: bool, message: str, out_path: str):
        self._set_ui_busy(False)

        if self.worker_mode == "metrics":
            # Extraer y analizar métricas de las líneas capturadas
            all_logs = "\n".join(self.worker.collected_logs) if hasattr(self.worker, "collected_logs") else ""
            metrics = ffmpeg_core.parse_comparison_metrics(all_logs)

            if metrics["ssim"] is not None or metrics["psnr"] is not None:
                self.lbl_ssim_score.setText(f"<b>SSIM:</b> {metrics['ssim_str']}")
                self.lbl_psnr_score.setText(f"<b>PSNR:</b> {metrics['psnr_str']}")
                self.lbl_rating_badge.setText(metrics["rating"])
                self.lbl_rating_badge.setStyleSheet(
                    f"background-color: {metrics['rating_color']}; color: white; font-weight: bold; "
                    f"padding: 4px 10px; border-radius: 4px; font-size: 12px;"
                )
                self.lbl_metrics_detail.setText(metrics["detail"] or "Análisis completado exitosamente.")

                QMessageBox.information(
                    self, "Métricas de Calidad Calculadas",
                    f"Resultados de similitud visual:\n\n"
                    f"• SSIM: {metrics['ssim_str']} (1.0000 = idéntico)\n"
                    f"• PSNR: {metrics['psnr_str']}\n\n"
                    f"Veredicto: {metrics['rating']}\n{metrics['detail']}"
                )
            else:
                QMessageBox.warning(
                    self, "Métricas no disponibles",
                    "No se pudieron extraer los valores SSIM o PSNR. Revise los registros en la consola inferior."
                )
            return

        # Modo video renderizado
        if success:
            self.output_actions.show_output(out_path)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Video Comparativo Generado")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(
                f"<div style='font-size: 13px; line-height: 1.4;'>"
                f"<p><b>¡Video comparativo generado con éxito!</b></p>"
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
