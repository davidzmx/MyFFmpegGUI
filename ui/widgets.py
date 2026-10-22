#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Widgets reutilizables con soporte de Drag & Drop y componentes visuales.
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QLabel, QPlainTextEdit, QProgressBar, QApplication, QStyle,
    QSplitter, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer


import config_manager


class DropLineEdit(QLineEdit):
    """
    QLineEdit especializado con soporte robusto para Drag & Drop desde
    exploradores de archivos de Linux (Dolphin, Nautilus, Thunar) y Windows.
    Interpreta URIs, limpia prefijos 'file://', decodifica caracteres %20 y comillas.
    """
    file_dropped = pyqtSignal(str)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        path = ""
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if urls:
                path = urls[0].toLocalFile()
                if not path:
                    path = urls[0].toString()
        elif mime.hasText():
            path = mime.text()

        if path:
            cleaned = config_manager.clean_file_path(path)
            self.setText(cleaned)
            self.file_dropped.emit(cleaned)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FileSelector(QWidget):
    """
    Selector de archivo con botón de examinar y soporte para Arrastrar y Soltar (Drag & Drop).
    Soporta rutas nativas y URIs tipo file:// arrastradas desde Dolphin, Nautilus o Windows Explorer.
    """
    file_selected = pyqtSignal(str)

    def __init__(
        self,
        placeholder: str = "Seleccione o arrastre un archivo aquí...",
        file_filter: str = "Archivos de video (*.mp4 *.mkv *.avi *.mov *.flv *.webm);;Todos los archivos (*.*)",
        is_save_dialog: bool = False,
        default_extension: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.file_filter = file_filter
        self.is_save_dialog = is_save_dialog
        self.default_extension = default_extension
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = DropLineEdit(placeholder, self)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.file_dropped.connect(self._on_dropped)

        self.btn_browse = QPushButton("Examinar...", self)
        self.btn_browse.clicked.connect(self._browse)

        layout.addWidget(self.edit)
        layout.addWidget(self.btn_browse)

    def _browse(self):
        start_dir = os.path.dirname(self.edit.text()) if self.edit.text() else ""
        if self.is_save_dialog:
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar archivo", start_dir, self.file_filter
            )
            if path and self.default_extension and not path.endswith(self.default_extension):
                path += self.default_extension
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar archivo", start_dir, self.file_filter
            )

        if path:
            self.set_path(path)

    def _on_dropped(self, clean_path: str):
        self.set_path(clean_path)

    def _on_text_changed(self, text: str):
        cleaned = config_manager.clean_file_path(text)
        if cleaned != text and (text.startswith("file://") or text.startswith('"') or text.startswith("'")):
            self.edit.blockSignals(True)
            self.edit.setText(cleaned)
            self.edit.blockSignals(False)
        self.file_selected.emit(cleaned)

    def get_path(self) -> str:
        return config_manager.clean_file_path(self.edit.text())

    def set_path(self, path: str):
        cleaned = config_manager.clean_file_path(path)
        self.edit.blockSignals(True)
        self.edit.setText(cleaned)
        self.edit.blockSignals(False)
        self.file_selected.emit(cleaned)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = ""
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if urls:
                path = urls[0].toLocalFile() or urls[0].toString()
        elif mime.hasText():
            path = mime.text()

        if path:
            self.set_path(path)
            event.acceptProposedAction()


class FolderSelector(QWidget):
    """
    Selector de carpetas con soporte de Drag & Drop y botón de examinar.
    """
    folder_selected = pyqtSignal(str)

    def __init__(self, placeholder: str = "Seleccione una carpeta...", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = DropLineEdit(placeholder, self)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.file_dropped.connect(self._on_dropped)

        self.btn_browse = QPushButton("Examinar...", self)
        self.btn_browse.clicked.connect(self._browse)

        layout.addWidget(self.edit)
        layout.addWidget(self.btn_browse)

    def _browse(self):
        start_dir = self.edit.text() if os.path.isdir(self.edit.text()) else ""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", start_dir)
        if folder:
            self.set_path(folder)

    def _on_dropped(self, raw_path: str):
        cleaned = config_manager.clean_file_path(raw_path)
        if os.path.isdir(cleaned):
            self.set_path(cleaned)
        elif os.path.isfile(cleaned):
            self.set_path(os.path.dirname(cleaned))
        else:
            self.set_path(cleaned)

    def _on_text_changed(self, text: str):
        cleaned = config_manager.clean_file_path(text)
        if cleaned != text and (text.startswith("file://") or text.startswith('"') or text.startswith("'")):
            self.edit.blockSignals(True)
            self.edit.setText(cleaned)
            self.edit.blockSignals(False)
        self.folder_selected.emit(cleaned)

    def get_path(self) -> str:
        return config_manager.clean_file_path(self.edit.text())

    def set_path(self, path: str):
        cleaned = config_manager.clean_file_path(path)
        self.edit.blockSignals(True)
        self.edit.setText(cleaned)
        self.edit.blockSignals(False)
        self.folder_selected.emit(cleaned)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = ""
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if urls:
                path = urls[0].toLocalFile() or urls[0].toString()
        elif mime.hasText():
            path = mime.text()

        if path:
            self._on_dropped(path)
            event.acceptProposedAction()


class LogConsole(QWidget):
    """
    Consola estilizada de registros de FFmpeg en tiempo real con botones de copiar y limpiar.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_lbl = QLabel("Terminal de Salida (FFmpeg):")
        header_lbl.setStyleSheet("font-weight: bold; color: #94a3b8;")

        btn_copy = QPushButton("Copiar")
        btn_copy.setFixedHeight(26)
        btn_copy.clicked.connect(self.copy_logs)

        btn_clear = QPushButton("Limpiar")
        btn_clear.setFixedHeight(26)
        btn_clear.clicked.connect(self.clear_logs)

        self.btn_toggle_height = QPushButton("↕ Expandir")
        self.btn_toggle_height.setToolTip("Alternar entre altura compacta y expandida de la terminal")
        self.btn_toggle_height.setFixedHeight(26)
        self.btn_toggle_height.clicked.connect(self._toggle_height)
        self._is_expanded = False

        header_layout.addWidget(header_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_toggle_height)
        header_layout.addWidget(btn_copy)
        header_layout.addWidget(btn_clear)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setObjectName("log_console")
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(1500)
        self.text_edit.setMinimumHeight(45)

        layout.addLayout(header_layout)
        layout.addWidget(self.text_edit)

    def _toggle_height(self):
        self._is_expanded = not self._is_expanded
        if self._is_expanded:
            self.text_edit.setMinimumHeight(240)
            self.btn_toggle_height.setText("↕ Reducir")
        else:
            self.text_edit.setMinimumHeight(45)
            self.text_edit.setMaximumHeight(16777215)
            self.btn_toggle_height.setText("↕ Expandir")

    def append_log(self, text: str):
        self.text_edit.appendPlainText(text)
        # Auto scroll al final
        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_logs(self):
        self.text_edit.clear()

    def copy_logs(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())


class ProgressBarWithStatus(QWidget):
    """
    Barra de progreso acompañada de etiquetas con estado, tiempo transcurrido y velocidad.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.bar = QProgressBar(self)
        self.bar.setValue(0)
        self.bar.setRange(0, 100)

        info_layout = QHBoxLayout()
        self.lbl_time = QLabel("Tiempo: 00:00:00")
        self.lbl_time.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self.lbl_extra = QLabel("En espera...")
        self.lbl_extra.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.lbl_extra.setAlignment(Qt.AlignRight)

        info_layout.addWidget(self.lbl_time)
        info_layout.addWidget(self.lbl_extra)

        layout.addWidget(self.bar)
        layout.addLayout(info_layout)

    def set_progress(self, percent: float, current_time: str, extra: str):
        self.bar.setValue(int(percent))
        if current_time:
            self.lbl_time.setText(f"Tiempo: {current_time}")
        if extra:
            self.lbl_extra.setText(extra)

    def reset(self):
        self.bar.setValue(0)
        self.lbl_time.setText("Tiempo: 00:00:00")
        self.lbl_extra.setText("Listo para iniciar")


class CommandPreviewWidget(QWidget):
    """
    Widget visual que muestra en tiempo real el comando exacto de FFmpeg
    que se va a ejecutar, con botón para copiarlo al portapapeles.
    """
    def __init__(self, title: str = "Comando FFmpeg a ejecutar:", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        self.lbl_title = QLabel(f"▶ {title}")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")

        self.btn_copy = QPushButton("Copiar Comando")
        self.btn_copy.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_copy.setFixedHeight(26)
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #38bdf8;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
                border-color: #1e293b;
            }
        """)
        self.btn_copy.setToolTip("Copiar comando al portapapeles para ejecutarlo en terminal")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)

        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_copy)
        layout.addLayout(header_layout)

        self.text_cmd = QPlainTextEdit(self)
        self.text_cmd.setReadOnly(True)
        self.text_cmd.setFixedHeight(48)
        self.text_cmd.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090d16;
                color: #4ade80;
                border: 1px solid #1e293b;
                border-radius: 4px;
                font-family: 'Consolas', 'DejaVu Sans Mono', 'Courier New', monospace;
                font-size: 11px;
                padding: 4px 6px;
                selection-background-color: #1e3a8a;
            }
        """)
        layout.addWidget(self.text_cmd)
        self._current_cmd_str = ""
        self.set_command("")

    def set_command(self, cmd_or_list):
        if isinstance(cmd_or_list, (list, tuple)):
            import ffmpeg_core
            self._current_cmd_str = ffmpeg_core.format_command_for_display(cmd_or_list)
        elif isinstance(cmd_or_list, str):
            self._current_cmd_str = cmd_or_list.strip()
        else:
            self._current_cmd_str = ""

        if not self._current_cmd_str:
            self.text_cmd.setPlainText("# Seleccione los archivos y parámetros para previsualizar el comando...")
            self.btn_copy.setEnabled(False)
        else:
            self.text_cmd.setPlainText(self._current_cmd_str)
            self.btn_copy.setEnabled(True)

    def get_command(self) -> str:
        return self._current_cmd_str

    def _copy_to_clipboard(self):
        if self._current_cmd_str:
            QApplication.clipboard().setText(self._current_cmd_str)
            self.btn_copy.setText("✓ ¡Copiado!")
            def _reset():
                self.btn_copy.setText("Copiar Comando")
                self.btn_copy.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
            QTimer.singleShot(1500, _reset)


class OutputActionsWidget(QWidget):
    """
    Barra de acciones post-generación:
    Permite abrir directamente el archivo generado o su carpeta contenedora en el explorador.
    """
    def __init__(self, file_label: str = "Abrir Video", parent=None):
        super().__init__(parent)
        self.file_label = file_label
        self.current_path = ""
        self.is_folder_only = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        self.lbl_status = QLabel("Listo:")
        self.lbl_status.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px;")

        self.btn_open_file = QPushButton(file_label)
        self.btn_open_file.setCursor(Qt.PointingHandCursor)
        self.btn_open_file.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_open_file.setStyleSheet("""
            QPushButton {
                background-color: #065f46;
                color: #ecfdf5;
                font-weight: bold;
                border: 1px solid #10b981;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #047857;
                border-color: #34d399;
            }
            QPushButton:pressed {
                background-color: #064e3b;
            }
        """)
        self.btn_open_file.clicked.connect(self._on_open_file)

        self.btn_open_folder = QPushButton("Abrir Carpeta Contenedora")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: bold;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
                color: #ffffff;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0c4a6e;
            }
        """)
        self.btn_open_folder.clicked.connect(self._on_open_folder)

        layout.addWidget(self.lbl_status)
        layout.addWidget(self.btn_open_file)
        layout.addWidget(self.btn_open_folder)
        layout.addStretch()

        self.setVisible(False)

    def show_output(self, path: str, is_folder_only: bool = False, custom_status: str = "Proceso completado exitosamente:"):
        self.current_path = path
        self.is_folder_only = is_folder_only
        self.lbl_status.setText(f"{custom_status}")
        self.btn_open_file.setText(self.file_label)
        self.btn_open_file.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_open_file.setVisible(not is_folder_only and os.path.isfile(path))
        self.btn_open_folder.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        self.btn_open_folder.setVisible(True)
        self.setVisible(True)

    def hide_output(self):
        self.setVisible(False)
        self.current_path = ""

    def _on_open_file(self):
        if self.current_path:
            import config_manager
            config_manager.open_path_in_os(self.current_path, is_directory=False)

    def _on_open_folder(self):
        if self.current_path:
            import config_manager
            config_manager.open_path_in_os(self.current_path, is_directory=True)


class ConsoleOutputPanel(QWidget):
    """
    Panel unificado que integra el 'Comando FFmpeg a ejecutar' y la 'Terminal de Salida (FFmpeg)'.
    Soporta:
    - Ocultar / Mostrar el panel con un solo clic.
    - Cambiar ubicación entre panel inferior (abajo) y panel lateral (derecha).
    - Botones de copiar comando, copiar logs y limpiar terminal.
    """
    toggle_position_requested = pyqtSignal()
    hide_requested = pyqtSignal()

    def __init__(self, title: str = "Comando FFmpeg a ejecutar:", parent=None):
        super().__init__(parent)
        self.position = "bottom"
        self.setObjectName("console_output_panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Barra superior del panel
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(6)

        self.lbl_panel_title = QLabel("🖥️ Comando y Terminal FFmpeg")
        self.lbl_panel_title.setStyleSheet("font-weight: bold; color: #a5b4fc; font-size: 11px;")
        header.addWidget(self.lbl_panel_title)

        header.addStretch()

        self.btn_pos = QPushButton("➡ Panel Lateral")
        self.btn_pos.setToolTip("Alternar entre ubicación Inferior (abajo) y Lateral (derecha)")
        self.btn_pos.setFixedHeight(24)
        self.btn_pos.setCursor(Qt.PointingHandCursor)
        self.btn_pos.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #38bdf8;
                border-color: #38bdf8;
            }
        """)
        self.btn_pos.clicked.connect(self.toggle_position_requested.emit)
        self.btn_toggle_pos = self.btn_pos
        header.addWidget(self.btn_pos)

        self.btn_hide = QPushButton("✖ Ocultar Panel")
        self.btn_hide.setToolTip("Ocultar panel de comando y terminal para ganar espacio")
        self.btn_hide.setFixedHeight(24)
        self.btn_hide.setCursor(Qt.PointingHandCursor)
        self.btn_hide.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #451a1a;
                color: #fca5a5;
                border-color: #ef4444;
            }
        """)
        self.btn_hide.clicked.connect(self.hide_requested.emit)
        header.addWidget(self.btn_hide)

        layout.addLayout(header)

        # 1. Previsualización del comando
        self.cmd_preview = CommandPreviewWidget(title, self)
        layout.addWidget(self.cmd_preview)

        # 2. Terminal de salida (FFmpeg)
        self.log_console = LogConsole(self)
        layout.addWidget(self.log_console, 1)

    def set_position_mode(self, pos: str):
        self.position = pos
        if pos == "side":
            self.btn_pos.setText("⬇ Panel Inferior")
            self.btn_pos.setToolTip("Colocar el comando y la terminal en la parte inferior (abajo)")
        else:
            self.btn_pos.setText("➡ Panel Lateral")
            self.btn_pos.setToolTip("Colocar el comando y la terminal en un panel lateral (derecha)")

    def get_command(self) -> str:
        return self.cmd_preview.get_command()

    def set_command(self, cmd_or_list):
        self.cmd_preview.set_command(cmd_or_list)

    def append_log(self, text: str):
        self.log_console.append_log(text)

    def clear_logs(self):
        self.log_console.clear_logs()

    def copy_logs(self):
        self.log_console.copy_logs()


def setup_tab_console_layout(
    tab_widget: QWidget,
    form_widget: QWidget,
    cmd_title: str = "Comando FFmpeg a ejecutar:",
    initial_bottom_sizes: list = None,
    initial_side_sizes: list = None
):
    """
    Configura de manera uniforme el divisor QSplitter y el panel de comando y consola
    en una pestaña dada.
    """
    # 1. ScrollArea para el formulario de opciones
    scroll_form = QScrollArea(tab_widget)
    scroll_form.setWidgetResizable(True)
    scroll_form.setWidget(form_widget)
    scroll_form.setFrameShape(QScrollArea.NoFrame)
    tab_widget.scroll_form = scroll_form

    # 2. Panel unificado de comando y consola
    console_panel = ConsoleOutputPanel(cmd_title, tab_widget)
    tab_widget.console_panel = console_panel
    tab_widget.cmd_preview = console_panel.cmd_preview
    tab_widget.log_console = console_panel.log_console

    # 3. Divisor QSplitter
    splitter = QSplitter(tab_widget)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(scroll_form)
    splitter.addWidget(console_panel)
    tab_widget.splitter = splitter
    tab_widget.splitter_console = splitter

    # 4. Botón flotante / inferior para mostrar el panel cuando está oculto
    btn_show_console = QPushButton("🖥️ Mostrar Comando FFmpeg y Terminal de Salida", tab_widget)
    btn_show_console.setObjectName("btn_show_console")
    btn_show_console.setCursor(Qt.PointingHandCursor)
    btn_show_console.setFixedHeight(28)
    btn_show_console.setStyleSheet("""
        QPushButton#btn_show_console {
            background-color: #1a1b2b;
            color: #38bdf8;
            border: 1px dashed #3b4261;
            border-radius: 6px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: bold;
        }
        QPushButton#btn_show_console:hover {
            background-color: #23253b;
            color: #7dd3fc;
            border: 1px solid #38bdf8;
        }
    """)
    tab_widget.btn_show_console = btn_show_console

    # Layout raíz de la pestaña
    root_layout = QVBoxLayout(tab_widget)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(4)
    root_layout.addWidget(splitter, 1)
    root_layout.addWidget(btn_show_console)

    def _sync_with_main_window(pos=None, visible=None):
        main_win = tab_widget.window()
        if main_win and hasattr(main_win, "sync_console_panels"):
            main_win.sync_console_panels(pos=pos, visible=visible)

    def _on_hide():
        config_manager.set_console_panel_visible(False)
        tab_widget.apply_console_panel_settings(visible=False)
        _sync_with_main_window(visible=False)

    def _on_show():
        config_manager.set_console_panel_visible(True)
        tab_widget.apply_console_panel_settings(visible=True)
        _sync_with_main_window(visible=True)

    def _on_toggle_pos():
        curr_pos = config_manager.get_console_panel_position()
        new_pos = "side" if curr_pos == "bottom" else "bottom"
        config_manager.set_console_panel_position(new_pos)
        tab_widget.apply_console_panel_settings(pos=new_pos)
        _sync_with_main_window(pos=new_pos)

    console_panel.hide_requested.connect(_on_hide)
    btn_show_console.clicked.connect(_on_show)
    console_panel.toggle_position_requested.connect(_on_toggle_pos)

    def apply_settings(pos: str = None, visible: bool = None):
        if pos is None:
            pos = config_manager.get_console_panel_position()
        if visible is None:
            visible = config_manager.get_console_panel_visible()

        if pos == "side":
            splitter.setOrientation(Qt.Horizontal)
            splitter.setSizes(initial_side_sizes or [620, 500])
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
        else:
            splitter.setOrientation(Qt.Vertical)
            splitter.setSizes(initial_bottom_sizes or [480, 240])
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)

        console_panel.set_position_mode(pos)
        console_panel.setVisible(bool(visible))
        btn_show_console.setVisible(not bool(visible))

    tab_widget.apply_console_panel_settings = apply_settings
    apply_settings()
