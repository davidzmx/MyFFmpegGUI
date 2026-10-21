#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Widgets reutilizables con soporte de Drag & Drop y componentes visuales.
"""

import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QFileDialog, QLabel, QPlainTextEdit, QProgressBar, QApplication, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer


class FileSelector(QWidget):
    """
    Selector de archivo con botón de examinar y soporte para Arrastrar y Soltar (Drag & Drop).
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

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self._on_text_changed)

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

    def _on_text_changed(self, text: str):
        self.file_selected.emit(text.strip())

    def get_path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, path: str):
        self.edit.setText(path)
        self.file_selected.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
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

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(lambda t: self.folder_selected.emit(t.strip()))

        self.btn_browse = QPushButton("Examinar...", self)
        self.btn_browse.clicked.connect(self._browse)

        layout.addWidget(self.edit)
        layout.addWidget(self.btn_browse)

    def _browse(self):
        start_dir = self.edit.text() if os.path.isdir(self.edit.text()) else ""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta", start_dir)
        if folder:
            self.set_path(folder)

    def get_path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, path: str):
        self.edit.setText(path)
        self.folder_selected.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.set_path(path)
            else:
                # Si arrastra un archivo, tomar su carpeta contenedora
                self.set_path(os.path.dirname(path))
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
        self.lbl_title = QLabel(f"⚡ {title}")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")

        self.btn_copy = QPushButton("📋 Copiar Comando")
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
            QTimer.singleShot(1500, lambda: self.btn_copy.setText("📋 Copiar Comando"))


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
