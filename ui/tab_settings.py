#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pestaña: Ajustes de FFmpeg, Carpeta Base y Configuración del Menú Contextual Multiplataforma
Permite configurar rutas, preferencias de guardado y personalizar las opciones de clic derecho
(incluyendo atajos rápidos sin abrir la interfaz, reordenación interactiva de opciones y
clic en variables disponibles para no tener que escribirlas manualmente).
"""

import os
import sys
import re
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QMessageBox, QTextEdit, QCheckBox, QRadioButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QFormLayout, QStyle
)
import ffmpeg_core
import config_manager
import context_menu_manager
from ui.widgets import FolderSelector


class CustomActionDialog(QDialog):
    """Diálogo modal para crear un atajo rápido para clic derecho sin GUI con variables interactivas."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Atajo Rápido para Menú Contextual (Sin abrir GUI)")
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl_info = QLabel(
            "<b>Crear Atajo Rápido para Clic Derecho:</b><br>"
            "Este atajo se ejecutará directamente en segundo plano al hacer clic derecho sobre el archivo "
            "sin abrir la interfaz gráfica, mostrando una notificación al finalizar."
        )
        lbl_info.setTextFormat(1)
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        form = QFormLayout()
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("ej. Convertir a MP4 (H.264)")
        form.addRow("Nombre en Menú:", self.edit_name)

        self.edit_cmd = QLineEdit()
        self.edit_cmd.setPlaceholderText('ffmpeg -y -i "{input}" -c:v libx264 -crf 20 "{output_no_ext}_h264.mp4"')
        form.addRow("Comando FFmpeg:", self.edit_cmd)
        layout.addLayout(form)

        # Variables disponibles interactivas (haz clic para insertar sin escribir)
        lbl_vars_title = QLabel("<b>Variables disponibles (haz clic para insertar en el comando):</b>")
        lbl_vars_title.setTextFormat(1)
        lbl_vars_title.setStyleSheet("color: #a5b4fc; font-size: 12px; margin-top: 2px;")
        layout.addWidget(lbl_vars_title)

        vars_info = [
            ("{input}", "Ruta completa del archivo seleccionado"),
            ("{output_no_ext}", "Ruta y nombre sin extensión (ej: /videos/viaje)"),
            ("{output_dir}", "Carpeta contenedora del archivo"),
            ("{file_stem}", "Nombre base del archivo sin extensión (ej: viaje)"),
            ("{filename}", "Nombre de archivo completo con extensión (ej: viaje.mp4)"),
            ("{ext}", "Extensión original con punto (ej: .mp4)"),
        ]

        grid_chips = QHBoxLayout()
        grid_chips.setSpacing(6)
        for var_tag, tooltip_txt in vars_info:
            btn_chip = QPushButton(var_tag)
            btn_chip.setToolTip(f"{var_tag} -> {tooltip_txt} (Haz clic para insertar)")
            btn_chip.setCursor(Qt.PointingHandCursor)
            btn_chip.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #38bdf8;
                    font-family: monospace;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 5px 8px;
                }
                QPushButton:hover {
                    background-color: #334155;
                    color: #7dd3fc;
                    border-color: #38bdf8;
                }
            """)
            btn_chip.clicked.connect(lambda _, t=var_tag: self._insert_variable(t))
            grid_chips.addWidget(btn_chip)
        grid_chips.addStretch()
        layout.addLayout(grid_chips)

        # Plantillas prediseñadas
        lbl_templates = QLabel("<b>O carga una plantilla recomendada de ejemplo con 1 clic:</b>")
        lbl_templates.setTextFormat(1)
        lbl_templates.setStyleSheet("color: #cbd5e1; font-size: 11px; margin-top: 4px;")
        layout.addWidget(lbl_templates)

        h_tpl = QHBoxLayout()
        h_tpl.setSpacing(6)

        btn_tpl_mp3 = QPushButton("MP3 Directo")
        btn_tpl_mp3.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        btn_tpl_mp3.setStyleSheet("background-color: #1e2235; color: #a5b4fc; font-size: 11px; padding: 4px 8px;")
        btn_tpl_mp3.clicked.connect(lambda: self._set_template('Convertir a MP3', 'ffmpeg -y -i "{input}" "{output_no_ext}.mp3"'))

        btn_tpl_h264 = QPushButton("MP4 H.264 Universal")
        btn_tpl_h264.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        btn_tpl_h264.setStyleSheet("background-color: #1e2235; color: #a5b4fc; font-size: 11px; padding: 4px 8px;")
        btn_tpl_h264.clicked.connect(lambda: self._set_template('Convertir a MP4 (H.264)', 'ffmpeg -y -i "{input}" -c:v libx264 -crf 20 -c:a aac "{output_no_ext}_h264.mp4"'))

        btn_tpl_pic = QPushButton("Captura PNG")
        btn_tpl_pic.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        btn_tpl_pic.setStyleSheet("background-color: #1e2235; color: #a5b4fc; font-size: 11px; padding: 4px 8px;")
        btn_tpl_pic.clicked.connect(lambda: self._set_template('Capturar Fotograma en PNG', 'ffmpeg -y -ss 00:00:01 -i "{input}" -vframes 1 "{output_no_ext}_thumb.png"'))

        h_tpl.addWidget(btn_tpl_mp3)
        h_tpl.addWidget(btn_tpl_h264)
        h_tpl.addWidget(btn_tpl_pic)
        h_tpl.addStretch()
        layout.addLayout(h_tpl)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("Guardar Atajo")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancelar")
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _insert_variable(self, var_name: str):
        """Inserta la variable seleccionada en la posición del cursor del campo comando."""
        self.edit_cmd.insert(var_name)
        self.edit_cmd.setFocus()

    def _set_template(self, name: str, cmd: str):
        """Carga una plantilla rápida prediseñada."""
        if not self.edit_name.text().strip():
            self.edit_name.setText(name)
        self.edit_cmd.setText(cmd)
        self.edit_cmd.setFocus()

    def _validate_and_accept(self):
        name = self.edit_name.text().strip()
        cmd = self.edit_cmd.text().strip()
        if not name:
            QMessageBox.warning(self, "Validación", "Por favor introduce un nombre para el atajo.")
            return
        if not cmd:
            QMessageBox.warning(self, "Validación", "Por favor introduce la plantilla de comando FFmpeg.")
            return
        self.accept()

    def get_data(self):
        return self.edit_name.text().strip(), self.edit_cmd.text().strip()


class TabSettings(QWidget):
    config_saved = pyqtSignal()

    def __init__(self, main_window_ref, parent=None):
        super().__init__(parent)
        self.main_window = main_window_ref

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(4, 4, 4, 4)

        # 1. Configuración de Carpeta Base y Preferencias de Guardado
        group_base = QGroupBox("1. Preferencias de Guardado y Carpeta Base")
        layout_base = QVBoxLayout(group_base)

        lbl_pref = QLabel("Comportamiento de guardado predeterminado al convertir audio o video:")
        lbl_pref.setStyleSheet("color: #cbd5e1; font-weight: bold;")
        layout_base.addWidget(lbl_pref)

        h_rad = QHBoxLayout()
        self.radio_pref_same = QRadioButton("Misma carpeta que el original (mismo nombre, nueva extensión)")
        self.radio_pref_base = QRadioButton("Carpeta Base configurada")
        self.radio_pref_same.toggled.connect(self._update_preview_label)
        self.radio_pref_base.toggled.connect(self._update_preview_label)
        h_rad.addWidget(self.radio_pref_same)
        h_rad.addWidget(self.radio_pref_base)
        h_rad.addStretch()
        layout_base.addLayout(h_rad)

        h_base_desc = QHBoxLayout()
        lbl_base_desc = QLabel("Ruta de la Carpeta Base predeterminada:")
        lbl_base_desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        btn_open_base = QPushButton("Abrir en Explorador")
        btn_open_base.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        btn_open_base.setToolTip("Abrir la carpeta base actual en el explorador de archivos del sistema")
        btn_open_base.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #7dd3fc;
            }
        """)
        btn_open_base.setCursor(Qt.PointingHandCursor)
        btn_open_base.clicked.connect(lambda: config_manager.open_path_in_os(self.folder_base.get_path(), is_directory=True))
        h_base_desc.addWidget(lbl_base_desc)
        h_base_desc.addStretch()
        h_base_desc.addWidget(btn_open_base)
        layout_base.addLayout(h_base_desc)

        self.folder_base = FolderSelector("Seleccione la carpeta base de salida...")
        layout_base.addWidget(self.folder_base)

        self.chk_auto_subfolders = QCheckBox(
            "Sugerir automáticamente subcarpeta con el nombre del archivo al usar la Carpeta Base"
        )
        self.chk_auto_subfolders.setStyleSheet("font-weight: bold; color: #a5b4fc;")
        self.chk_auto_subfolders.stateChanged.connect(self._update_preview_label)
        layout_base.addWidget(self.chk_auto_subfolders)

        self.lbl_preview_example = QLabel("")
        self.lbl_preview_example.setObjectName("lbl_meta")
        self.lbl_preview_example.setWordWrap(True)
        layout_base.addWidget(self.lbl_preview_example)

        layout.addWidget(group_base)

        # 2. Configuración del Panel de Salida (Comando y Terminal)
        group_panel = QGroupBox("2. Panel de Salida (Comando FFmpeg y Terminal de Registros)")
        layout_panel = QVBoxLayout(group_panel)

        lbl_panel_desc = QLabel(
            "Configure la ubicación y el comportamiento del panel que agrupa la vista previa del comando FFmpeg y los registros de terminal."
        )
        lbl_panel_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout_panel.addWidget(lbl_panel_desc)

        h_pos = QHBoxLayout()
        h_pos.addWidget(QLabel("Ubicación del panel:"))
        self.radio_panel_bottom = QRadioButton("Inferior (En la parte de abajo - Predeterminado)")
        self.radio_panel_side = QRadioButton("Lateral (A la derecha)")
        h_pos.addWidget(self.radio_panel_bottom)
        h_pos.addWidget(self.radio_panel_side)
        h_pos.addStretch()
        layout_panel.addLayout(h_pos)

        self.chk_panel_visible = QCheckBox("Mostrar panel de comando y terminal al iniciar")
        self.chk_panel_visible.setChecked(False)
        self.chk_panel_visible.setStyleSheet("font-weight: bold; color: #a5b4fc;")
        layout_panel.addWidget(self.chk_panel_visible)

        lbl_panel_tip = QLabel(
            "• También puedes ocultar o alternar la ubicación del panel directamente en cualquier pestaña con los botones integrados."
        )
        lbl_panel_tip.setStyleSheet("color: #64748b; font-size: 11px;")
        layout_panel.addWidget(lbl_panel_tip)

        layout.addWidget(group_panel)

        # 3. Estado del Sistema y Rutas de FFmpeg
        group_paths = QGroupBox("3. Ejecutables de FFmpeg, FFprobe y FFplay")
        layout_paths = QVBoxLayout(group_paths)

        lbl_os = QLabel(f"Sistema Operativo Detectado: <b>{sys.platform.upper()}</b>")
        lbl_os.setStyleSheet("color: #38bdf8;")
        layout_paths.addWidget(lbl_os)

        layout_paths.addWidget(QLabel("Ruta del ejecutable FFmpeg:"))
        h_ffmpeg = QHBoxLayout()
        self.edit_ffmpeg = QLineEdit()
        btn_browse_ffmpeg = QPushButton("Examinar...")
        btn_browse_ffmpeg.clicked.connect(self._browse_ffmpeg)
        h_ffmpeg.addWidget(self.edit_ffmpeg)
        h_ffmpeg.addWidget(btn_browse_ffmpeg)
        layout_paths.addLayout(h_ffmpeg)

        layout_paths.addWidget(QLabel("Ruta del ejecutable FFprobe:"))
        h_ffprobe = QHBoxLayout()
        self.edit_ffprobe = QLineEdit()
        btn_browse_ffprobe = QPushButton("Examinar...")
        btn_browse_ffprobe.clicked.connect(self._browse_ffprobe)
        h_ffprobe.addWidget(self.edit_ffprobe)
        h_ffprobe.addWidget(btn_browse_ffprobe)
        layout_paths.addLayout(h_ffprobe)

        layout_paths.addWidget(QLabel("Ruta del ejecutable FFplay (Opcional - Audio y visor auxiliar):"))
        h_ffplay = QHBoxLayout()
        self.edit_ffplay = QLineEdit()
        btn_browse_ffplay = QPushButton("Examinar...")
        btn_browse_ffplay.clicked.connect(self._browse_ffplay)
        h_ffplay.addWidget(self.edit_ffplay)
        h_ffplay.addWidget(btn_browse_ffplay)
        layout_paths.addLayout(h_ffplay)

        h_actions = QHBoxLayout()
        btn_auto = QPushButton("Autodetectar en Sistema")
        btn_auto.clicked.connect(self._auto_detect)

        btn_save = QPushButton("Guardar Configuración")
        btn_save.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        btn_save.setStyleSheet("background-color: #4338ca; color: white; font-weight: bold;")
        btn_save.clicked.connect(self._save_settings)

        btn_test = QPushButton("Probar y Verificar Versión")
        btn_test.clicked.connect(self._test_version)

        h_actions.addWidget(btn_auto)
        h_actions.addWidget(btn_save)
        h_actions.addWidget(btn_test)
        layout_paths.addLayout(h_actions)

        layout.addWidget(group_paths)

        # 4. Integración, Orden y Atajos en el Menú Contextual (Clic Derecho)
        group_context = QGroupBox("4. Integración, Orden y Atajos en el Menú Contextual (Clic Derecho en Archivos)")
        layout_context = QVBoxLayout(group_context)

        lbl_context_info = QLabel(
            "Personaliza las opciones y el <b>orden</b> en que aparecerán al hacer <b>clic derecho sobre cualquier archivo multimedia</b> "
            "en tu explorador de archivos (Dolphin, Nautilus o Windows Explorer). Puedes <b>reordenar</b> con los botones "
            "Subir / Bajar, activar/desactivar opciones, o añadir tus propios <b>comandos rápidos que se ejecutan sin abrir la interfaz</b>:"
        )
        lbl_context_info.setTextFormat(1)
        lbl_context_info.setWordWrap(True)
        lbl_context_info.setStyleSheet("color: #cbd5e1; font-size: 12px; line-height: 1.4;")
        layout_context.addWidget(lbl_context_info)

        # Layout horizontal para la tabla y los botones de reordenamiento lateral
        h_table_and_order = QHBoxLayout()

        self.table_actions = QTableWidget()
        self.table_actions.setColumnCount(5)
        self.table_actions.setHorizontalHeaderLabels(["Activo", "Nombre en Menú", "Tipo", "Comando / Pestaña", "Orden / Gestión"])
        self.table_actions.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_actions.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_actions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_actions.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_actions.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_actions.setColumnWidth(1, 240)
        self.table_actions.setFixedHeight(230)
        self.table_actions.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_actions.setSelectionMode(QTableWidget.SingleSelection)
        self.table_actions.setStyleSheet(
            "QTableWidget { background-color: #0f1019; color: #f1f5f9; border: 1px solid #2d3348; border-radius: 6px; } "
            "QHeaderView::section { background-color: #1e2235; color: #cbd5e1; font-weight: bold; border: 1px solid #2d3348; padding: 4px; }"
        )
        h_table_and_order.addWidget(self.table_actions)

        # Botones laterales para subir y bajar la fila seleccionada
        v_order = QVBoxLayout()
        v_order.setSpacing(8)

        lbl_reorder = QLabel("<b>Reordenar:</b>")
        lbl_reorder.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_order.addWidget(lbl_reorder)

        self.btn_move_up = QPushButton("Subir")
        self.btn_move_up.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        self.btn_move_up.setToolTip("Mover el elemento seleccionado hacia arriba en el menú de clic derecho")
        self.btn_move_up.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; padding: 8px 12px;")
        self.btn_move_up.clicked.connect(lambda: self._move_selected_action(-1))

        self.btn_move_down = QPushButton("Bajar")
        self.btn_move_down.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.btn_move_down.setToolTip("Mover el elemento seleccionado hacia abajo en el menú de clic derecho")
        self.btn_move_down.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; padding: 8px 12px;")
        self.btn_move_down.clicked.connect(lambda: self._move_selected_action(1))

        v_order.addWidget(self.btn_move_up)
        v_order.addWidget(self.btn_move_down)
        v_order.addStretch()
        h_table_and_order.addLayout(v_order)

        layout_context.addLayout(h_table_and_order)

        # Botones de gestión de atajos
        h_table_btns = QHBoxLayout()
        btn_add_custom = QPushButton("+ Agregar Atajo Rápido Personalizado (Sin GUI)")
        btn_add_custom.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        btn_add_custom.setStyleSheet("background-color: #4338ca; color: white; font-weight: bold;")
        btn_add_custom.clicked.connect(self._add_custom_action)

        btn_reset_defaults = QPushButton("Restablecer Orden y Opciones Predeterminadas")
        btn_reset_defaults.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        btn_reset_defaults.clicked.connect(self._reset_default_actions)

        h_table_btns.addWidget(btn_add_custom)
        h_table_btns.addWidget(btn_reset_defaults)
        h_table_btns.addStretch()
        layout_context.addLayout(h_table_btns)

        # Estado del sistema y botones de instalación
        h_status = QHBoxLayout()
        self.lbl_context_status = QLabel("")
        self.lbl_context_status.setStyleSheet("font-weight: bold; font-size: 13px;")
        h_status.addWidget(self.lbl_context_status)
        h_status.addStretch()
        layout_context.addLayout(h_status)

        h_ctx_btns = QHBoxLayout()
        self.btn_install_context = QPushButton("Aplicar Cambios al Clic Derecho")
        self.btn_install_context.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.btn_install_context.setStyleSheet("background-color: #059669; color: white; font-weight: bold;")
        self.btn_install_context.clicked.connect(self._install_context_menu)

        self.btn_uninstall_context = QPushButton("Desinstalar Menú")
        self.btn_uninstall_context.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_uninstall_context.setStyleSheet("background-color: #334155; color: #f87171;")
        self.btn_uninstall_context.clicked.connect(self._uninstall_context_menu)

        self.btn_export_reg = QPushButton("Exportar Registro Windows (.reg)")
        self.btn_export_reg.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_export_reg.clicked.connect(self._export_windows_reg)

        h_ctx_btns.addWidget(self.btn_install_context)
        h_ctx_btns.addWidget(self.btn_uninstall_context)
        h_ctx_btns.addWidget(self.btn_export_reg)
        layout_context.addLayout(h_ctx_btns)

        layout.addWidget(group_context)

        # 5. Información de Versión
        group_ver = QGroupBox("5. Verificación de Versión y Códecs")
        layout_ver = QVBoxLayout(group_ver)

        self.txt_version = QTextEdit()
        self.txt_version.setReadOnly(True)
        self.txt_version.setFixedHeight(95)
        self.txt_version.setStyleSheet(
            "background-color: #0f1019; color: #a5b4fc; font-family: monospace; font-size: 11px;"
        )
        layout_ver.addWidget(self.txt_version)
        layout.addWidget(group_ver)

        # 6. Guía de portabilidad multiplataforma
        group_guide = QGroupBox("6. Guía de Portabilidad (Windows y Linux)")
        layout_guide = QVBoxLayout(group_guide)

        guide_text = (
            "<b>¿Cómo distribuir la aplicación sin que el usuario tenga que instalar nada?</b><br><br>"
            "<b>1. En Windows:</b><br>"
            "• Colocar <code>ffmpeg.exe</code> y <code>ffprobe.exe</code> en la misma carpeta del programa o en una subcarpeta <code>bin/</code>.<br>"
            "• Para empaquetar en un único <code>.exe</code>:<br>"
            "&nbsp;&nbsp;<code>pyinstaller --noconsole --onefile --name MyFFmpegGUI main.py</code><br><br>"
            "<b>2. En Linux:</b><br>"
            "• Instalar mediante <code>sudo apt install ffmpeg</code> (Debian/Ubuntu) o colocar el binario estático junto a la app."
        )

        lbl_guide = QLabel(guide_text)
        lbl_guide.setTextFormat(1)
        lbl_guide.setWordWrap(True)
        lbl_guide.setStyleSheet("color: #cbd5e1; font-size: 12px; line-height: 1.4;")
        layout_guide.addWidget(lbl_guide)
        layout.addWidget(group_guide)

        scroll.setWidget(container)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(scroll)

        # Cargar valores actuales
        self._load_current_values()

    def _load_current_values(self):
        cfg = config_manager.load_config()
        ffmpeg_p = cfg.get("ffmpeg_path")
        ffprobe_p = cfg.get("ffprobe_path")
        ffplay_p = cfg.get("ffplay_path")
        base_dir = cfg.get("base_output_dir", config_manager.get_default_base_dir())
        auto_sub = cfg.get("auto_suggest_subfolders", True)
        save_pref = cfg.get("default_save_location", "same_folder")

        def_ffmpeg, def_ffprobe = ffmpeg_core.get_default_ffmpeg_paths()
        def_ffplay = ffmpeg_core.get_ffplay_path(ffmpeg_p or def_ffmpeg)

        self.edit_ffmpeg.setText(ffmpeg_p or def_ffmpeg or "")
        self.edit_ffprobe.setText(ffprobe_p or def_ffprobe or "")
        self.edit_ffplay.setText(ffplay_p or def_ffplay or "")
        self.folder_base.set_path(base_dir)
        self.chk_auto_subfolders.setChecked(bool(auto_sub))

        if save_pref == "base_dir":
            self.radio_pref_base.setChecked(True)
        else:
            self.radio_pref_same.setChecked(True)

        panel_pos = cfg.get("console_panel_position", "bottom")
        if panel_pos == "side":
            self.radio_panel_side.setChecked(True)
        else:
            self.radio_panel_bottom.setChecked(True)
        self.chk_panel_visible.setChecked(bool(cfg.get("console_panel_visible", False)))

        self._update_preview_label()
        self._test_version()
        self._populate_actions_table()
        self._update_context_status()

    def _populate_actions_table(self):
        """Llena la tabla de acciones del menú contextual con checkboxes, botones de orden y borrado."""
        actions = config_manager.get_context_actions()
        self.table_actions.setRowCount(len(actions))

        for row, a in enumerate(actions):
            act_id = a.get("id")
            enabled = bool(a.get("enabled", True))

            # 0. Checkbox activo
            chk = QCheckBox()
            chk.setChecked(enabled)
            chk.stateChanged.connect(lambda state, target_id=act_id: self._on_action_toggle(target_id, state))

            chk_container = QWidget()
            h_chk = QHBoxLayout(chk_container)
            h_chk.addWidget(chk)
            h_chk.setAlignment(Qt.AlignCenter)
            h_chk.setContentsMargins(0, 0, 0, 0)
            self.table_actions.setCellWidget(row, 0, chk_container)

            # 1. Nombre con icono nativo
            raw_name = a.get("name", "")
            clean_name = re.sub(r'^[^\w\s\-:()]+', '', raw_name).strip()
            name_item = QTableWidgetItem(clean_name)
            is_quick = a.get("type") == "quick"

            if "audio" in act_id:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
            elif "video" in act_id:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            elif "frames" in act_id:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
            elif "segment" in act_id:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMenuButton))
            elif "compare" in act_id:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
            elif is_quick:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_CommandLink))
            else:
                name_item.setIcon(self.style().standardIcon(QStyle.SP_DesktopIcon))

            self.table_actions.setItem(row, 1, name_item)

            # 2. Tipo
            type_text = "Rápido (Sin GUI)" if is_quick else "Abrir Interfaz"
            type_item = QTableWidgetItem(type_text)
            type_item.setIcon(self.style().standardIcon(QStyle.SP_CommandLink if is_quick else QStyle.SP_TitleBarNormalButton))
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table_actions.setItem(row, 2, type_item)

            # 3. Detalle
            if is_quick:
                detail_text = a.get("command_template", "")
            else:
                detail_text = f"Pestaña: {a.get('tab') or 'Principal'}"
            detail_item = QTableWidgetItem(detail_text)
            detail_item.setFlags(detail_item.flags() & ~Qt.ItemIsEditable)
            self.table_actions.setItem(row, 3, detail_item)

            # 4. Orden y Gestión (▲ Subir, ▼ Bajar, Eliminar)
            cell_container = QWidget()
            h_cell = QHBoxLayout(cell_container)
            h_cell.setContentsMargins(4, 2, 4, 2)
            h_cell.setSpacing(4)
            h_cell.setAlignment(Qt.AlignCenter)

            btn_up = QPushButton()
            btn_up.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
            btn_up.setToolTip("Subir esta opción en el menú de clic derecho")
            btn_up.setFixedSize(28, 22)
            btn_up.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; border-radius: 3px;")
            btn_up.setEnabled(row > 0)
            btn_up.clicked.connect(lambda _, target_id=act_id: self._move_action(target_id, -1))
            h_cell.addWidget(btn_up)

            btn_down = QPushButton()
            btn_down.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
            btn_down.setToolTip("Bajar esta opción en el menú de clic derecho")
            btn_down.setFixedSize(28, 22)
            btn_down.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; border-radius: 3px;")
            btn_down.setEnabled(row < len(actions) - 1)
            btn_down.clicked.connect(lambda _, target_id=act_id: self._move_action(target_id, 1))
            h_cell.addWidget(btn_down)

            if a.get("is_custom"):
                btn_del = QPushButton()
                btn_del.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
                btn_del.setToolTip("Eliminar este atajo personalizado")
                btn_del.setFixedSize(28, 22)
                btn_del.setStyleSheet("color: #f87171; background-color: #1e293b; border-radius: 3px;")
                btn_del.clicked.connect(lambda _, target_id=act_id: self._delete_custom_action(target_id))
                h_cell.addWidget(btn_del)

            self.table_actions.setCellWidget(row, 4, cell_container)

    def _move_action(self, act_id: str, direction: int):
        """Mueve una acción hacia arriba o abajo en el orden del menú."""
        moved = config_manager.move_context_action(act_id, direction)
        if moved:
            self._populate_actions_table()
            actions = config_manager.get_context_actions()
            new_idx = next((i for i, a in enumerate(actions) if a.get("id") == act_id), -1)
            if new_idx >= 0:
                self.table_actions.selectRow(new_idx)
            if context_menu_manager.is_context_menu_installed():
                context_menu_manager.install_context_menu()

    def _move_selected_action(self, direction: int):
        """Mueve la acción de la fila actualmente seleccionada."""
        row = self.table_actions.currentRow()
        actions = config_manager.get_context_actions()
        if 0 <= row < len(actions):
            act_id = actions[row].get("id")
            self._move_action(act_id, direction)

    def _on_action_toggle(self, act_id: str, state: int):
        """Activa o desactiva la acción y actualiza el menú contextual si está instalado."""
        enabled = (state == Qt.Checked)
        config_manager.toggle_context_action(act_id, enabled)
        if context_menu_manager.is_context_menu_installed():
            context_menu_manager.install_context_menu()

    def _add_custom_action(self):
        """Muestra el diálogo para añadir una nueva acción rápida y la registra."""
        dlg = CustomActionDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, cmd = dlg.get_data()
            config_manager.add_custom_quick_action(name, cmd)
            self._populate_actions_table()
            if context_menu_manager.is_context_menu_installed():
                context_menu_manager.install_context_menu()
            QMessageBox.information(
                self, "Atajo Creado",
                f"El atajo '{name}' se ha añadido correctamente a la lista.\n"
                "Al hacer clic derecho en cualquier archivo se ejecutará en segundo plano."
            )

    def _delete_custom_action(self, act_id: str):
        """Elimina una acción personalizada."""
        reply = QMessageBox.question(
            self, "Eliminar Atajo",
            "¿Estás seguro de que deseas eliminar este atajo personalizado?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            config_manager.delete_context_action(act_id)
            self._populate_actions_table()
            if context_menu_manager.is_context_menu_installed():
                context_menu_manager.install_context_menu()

    def _reset_default_actions(self):
        """Restaura los atajos predeterminados y su orden original."""
        reply = QMessageBox.question(
            self, "Restablecer Opciones",
            "¿Deseas restablecer todos los atajos del menú contextual y su orden por defecto?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            config_manager.save_context_actions([dict(a) for a in config_manager.DEFAULT_CONTEXT_ACTIONS])
            self._populate_actions_table()
            if context_menu_manager.is_context_menu_installed():
                context_menu_manager.install_context_menu()

    def _update_preview_label(self):
        base_dir = self.folder_base.get_path() or config_manager.get_default_base_dir()
        if self.radio_pref_same.isChecked():
            preview = "• Preferencia activa: Misma carpeta que el archivo original (ej: /videos/viaje.mp4 -> /videos/viaje.mp3)"
        elif self.chk_auto_subfolders.isChecked():
            preview = f"• Preferencia activa: Carpeta Base con subcarpeta:\n  {base_dir}/viaje/viaje_audio.wav"
        else:
            preview = f"• Preferencia activa: Carpeta Base directa:\n  {base_dir}/viaje_audio.wav"
        self.lbl_preview_example.setText(preview)

    def _browse_ffmpeg(self):
        from PyQt5.QtWidgets import QFileDialog
        is_win = sys.platform.startswith("win")
        filt = "Ejecutable FFmpeg (ffmpeg.exe);;Todos (*.*)" if is_win else "Ejecutable FFmpeg (ffmpeg);;Todos (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar ejecutable FFmpeg", "", filt)
        if path:
            self.edit_ffmpeg.setText(path)
            self._test_version()

    def _browse_ffprobe(self):
        from PyQt5.QtWidgets import QFileDialog
        is_win = sys.platform.startswith("win")
        filt = "Ejecutable FFprobe (ffprobe.exe);;Todos (*.*)" if is_win else "Ejecutable FFprobe (ffprobe);;Todos (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar ejecutable FFprobe", "", filt)
        if path:
            self.edit_ffprobe.setText(path)

    def _browse_ffplay(self):
        from PyQt5.QtWidgets import QFileDialog
        is_win = sys.platform.startswith("win")
        filt = "Ejecutable FFplay (ffplay.exe);;Todos (*.*)" if is_win else "Ejecutable FFplay (ffplay);;Todos (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar ejecutable FFplay", "", filt)
        if path:
            self.edit_ffplay.setText(path)

    def _auto_detect(self):
        def_ffmpeg, def_ffprobe = ffmpeg_core.get_default_ffmpeg_paths()
        def_ffplay = ffmpeg_core.get_ffplay_path(def_ffmpeg)
        self.edit_ffmpeg.setText(def_ffmpeg or "")
        self.edit_ffprobe.setText(def_ffprobe or "")
        self.edit_ffplay.setText(def_ffplay or "")
        self._test_version()
        QMessageBox.information(
            self, "Detección",
            f"FFmpeg: {def_ffmpeg or 'No hallado'}\nFFprobe: {def_ffprobe or 'No hallado'}\nFFplay: {def_ffplay or 'No hallado'}"
        )

    def _save_settings(self):
        base_dir = self.folder_base.get_path().strip() or config_manager.get_default_base_dir()
        config_manager.ensure_dir_exists(base_dir)

        save_loc = "base_dir" if self.radio_pref_base.isChecked() else "same_folder"
        panel_pos = "side" if self.radio_panel_side.isChecked() else "bottom"
        panel_visible = self.chk_panel_visible.isChecked()

        curr_cfg = config_manager.load_config()
        curr_cfg.update({
            "ffmpeg_path": self.edit_ffmpeg.text().strip(),
            "ffprobe_path": self.edit_ffprobe.text().strip(),
            "ffplay_path": self.edit_ffplay.text().strip(),
            "base_output_dir": base_dir,
            "auto_suggest_subfolders": self.chk_auto_subfolders.isChecked(),
            "default_save_location": save_loc,
            "console_panel_position": panel_pos,
            "console_panel_visible": panel_visible,
        })
        config_manager.save_config(curr_cfg)
        self._update_preview_label()
        self.config_saved.emit()
        QMessageBox.information(self, "Guardado", "Configuración, Preferencias y Carpeta Base guardadas exitosamente.")

    def _test_version(self):
        path = self.edit_ffmpeg.text().strip()
        if not path or not os.path.isfile(path):
            self.txt_version.setText("FFmpeg: No configurado o el archivo no existe.")
            return

        ver = ffmpeg_core.get_ffmpeg_version(path)
        ffprobe_p = self.edit_ffprobe.text().strip()
        ffprobe_status = "Detectado" if ffprobe_p and os.path.isfile(ffprobe_p) else "No encontrado"
        ffplay_p = self.edit_ffplay.text().strip() or ffmpeg_core.get_ffplay_path(path)
        ffplay_status = "Detectado" if ffplay_p and os.path.isfile(ffplay_p) else "Opcional / No encontrado"

        self.txt_version.setText(
            f"FFmpeg OK: {ver}\n"
            f"FFprobe estado: {ffprobe_status} ({ffprobe_p or 'No configurado'})\n"
            f"FFplay estado: {ffplay_status} ({ffplay_p or 'No configurado'})"
        )

    def get_paths(self):
        return self.edit_ffmpeg.text().strip(), self.edit_ffprobe.text().strip()

    def _update_context_status(self):
        installed = context_menu_manager.is_context_menu_installed()
        if installed:
            self.lbl_context_status.setText("<span style='color: #10b981; font-size: 14px;'>●</span> <b>Estado:</b> Integrado activamente en el menú contextual de clic derecho.")
            self.lbl_context_status.setStyleSheet("color: #4ade80; font-weight: bold;")
            self.btn_install_context.setText("Aplicar Cambios al Clic Derecho")
            self.btn_install_context.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            self.btn_uninstall_context.setEnabled(True)
        else:
            self.lbl_context_status.setText("<span style='color: #94a3b8; font-size: 14px;'>○</span> <b>Estado:</b> No integrado en el menú contextual del sistema.")
            self.lbl_context_status.setStyleSheet("color: #94a3b8; font-weight: bold;")
            self.btn_install_context.setText("Integrar en Clic Derecho")
            self.btn_install_context.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            self.btn_uninstall_context.setEnabled(False)

    def _install_context_menu(self):
        ok, msg = context_menu_manager.install_context_menu()
        self._update_context_status()
        if ok:
            QMessageBox.information(
                self, "Integración de Menú Contextual",
                f"{msg}\n\n"
                "¡Ahora al hacer clic derecho sobre cualquier archivo multimedia, "
                "aparecerán las opciones en el orden exacto configurado!"
            )
        else:
            QMessageBox.critical(self, "Error al Instalar", f"Error: {msg}")

    def _uninstall_context_menu(self):
        ok, msg = context_menu_manager.uninstall_context_menu()
        self._update_context_status()
        if ok:
            QMessageBox.information(self, "Menú Contextual", msg)
        else:
            QMessageBox.warning(self, "Aviso", msg)

    def _export_windows_reg(self):
        try:
            inst_f, uninst_f = context_menu_manager.export_windows_reg_files()
            QMessageBox.information(
                self,
                "Archivos de Registro para Windows",
                f"Se han generado exitosamente los archivos .reg para Windows con tu orden y opciones actuales:\n\n"
                f"• Instalador: {inst_f}\n"
                f"• Desinstalador: {uninst_f}\n\n"
                "Para activarlo en cualquier equipo con Windows, sólo haga doble clic sobre 'instalar_menu_contextual_windows.reg'. "
                "No requiere permisos de administrador."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al generar archivos de Windows: {e}")
