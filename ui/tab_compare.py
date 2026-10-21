#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Comparar Videos (Comparador visual interactivo y sincronizado)
Permite abrir o arrastrar dos videos (Referencia y Comprimido/Convertido) para:
1. Inspección técnica de metadatos (Resolución, FPS, Códecs, Bitrate, Reducción de Tamaño).
2. Reproducción paralela interactiva con visor integrado en 1 sola ventana o en reproductores externos.
"""

import os
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QMessageBox, QCheckBox, QStyle, QDialog, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, QSize

from ui.widgets import FileSelector
import ffmpeg_core
import config_manager
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
    1. Reproductor integrado en 1 sola ventana con cortina interactiva y controles.
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
            "• Alterna al instante entre Pantalla Dividida y Lado a Lado, con barra de búsqueda, volumen y pistas de audio."
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
        self.info_a = None
        self.info_b = None
        self._live_procs = []
        self._dual_procs = []

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. Videos a Comparar (Video A y Video B)
        group_inputs = QGroupBox("1. Videos a Comparar (Seleccione o arrastre ambos archivos)")
        layout_inputs = QVBoxLayout(group_inputs)
        layout_inputs.setSpacing(10)

        # Contenedor lado a lado para Video A y Video B
        h_videos = QHBoxLayout()
        h_videos.setSpacing(14)

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
            "padding: 8px 12px; color: #cbd5e1; font-size: 12px;"
        )
        self.lbl_diff_summary = self.banner_diff
        layout_inputs.addWidget(self.banner_diff)

        layout.addWidget(group_inputs)

        # 2. Panel del Comparador Visual Interactivo
        group_play = QGroupBox("2. Comparador Visual en Tiempo Real")
        layout_play = QVBoxLayout(group_play)
        layout_play.setSpacing(14)

        lbl_desc = QLabel(
            "<div style='font-size: 12px; color: #cbd5e1; line-height: 1.6;'>"
            "<p>Compara ambos videos directamente en pantalla de forma interactiva y sincronizada:</p>"
            "<ul style='margin-left: 10px; color: #94a3b8;'>"
            "<li><b>Pantalla Dividida interactiva:</b> Arrastra la cortina con el mouse sobre el video para contrastar detalles píxel a píxel.</li>"
            "<li><b>Modo Lado a Lado:</b> Visualiza ambos videos enteros uno junto al otro para comparar colores y encuadre general.</li>"
            "<li><b>Controles completos:</b> Pausa/Play sincronizado, barra de búsqueda, volumen independiente, cambio de pista de audio y pantalla completa.</li>"
            "</ul>"
            "</div>"
        )
        lbl_desc.setTextFormat(Qt.RichText)
        lbl_desc.setWordWrap(True)
        layout_play.addWidget(lbl_desc)

        # Botón principal
        h_btn = QHBoxLayout()
        self.btn_play_both = QPushButton("  Reproducir Ambos en Paralelo (Comparar)", self)
        self.btn_play_both.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_play_both.setIconSize(QSize(20, 20))
        self.btn_play_both.setFixedHeight(46)
        self.btn_play_both.setCursor(Qt.PointingHandCursor)
        self.btn_play_both.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; font-size: 13px; "
            "border-radius: 6px; padding: 6px 18px;"
        )
        self.btn_play_both.setToolTip("Reproduce ambos videos en paralelo (Visor sincronizado en 1 ventana o en 2 ventanas). Clic derecho para cambiar modo.")
        self.btn_play_both.clicked.connect(self._play_both)
        self.btn_play_both.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_play_both.customContextMenuRequested.connect(self._show_play_context_menu)
        h_btn.addWidget(self.btn_play_both)
        layout_play.addLayout(h_btn)

        layout.addWidget(group_play)
        layout.addStretch(1)

        # Alias descriptivo para compatibilidad
        self.btn_gen_compare = None

    def update_base_dir_display(self):
        """Mantiene compatibilidad con MainWindow si cambia la carpeta base."""
        pass

    def _on_file_a_selected(self, path: str):
        path = config_manager.clean_file_path(path)
        if not path or not os.path.isfile(path):
            self.lbl_meta_a.setText("Sin archivo cargado")
            self.info_a = None
            self._update_summary()
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
        self._update_summary()

    def _on_file_b_selected(self, path: str):
        path = config_manager.clean_file_path(path)
        if not path or not os.path.isfile(path):
            self.lbl_meta_b.setText("Sin archivo cargado")
            self.info_b = None
            self._update_summary()
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
        self._update_summary()

    def _update_summary(self):
        if not self.info_a or not self.info_b:
            self.banner_diff.setText("Cargue ambos videos para analizar las diferencias técnicas de compresión.")
            self.banner_diff.setStyleSheet(
                "background-color: #1e2235; border: 1px solid #334155; border-radius: 6px; "
                "padding: 8px 12px; color: #cbd5e1; font-size: 12px;"
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
        player._set_mode("split")
        player.exec_()

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
