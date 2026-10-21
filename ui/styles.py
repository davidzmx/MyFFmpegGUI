#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Estilos visuales modernos (Dark Theme) para MyFFmpegGUI
Inspirado en interfaces modernas y elegantes.
"""

import os
import sys
from pathlib import Path
from PyQt5.QtGui import QPalette, QColor, QIcon


def _get_asset_path(filename: str) -> str:
    """Devuelve la ruta absoluta normalizada (con forward slashes para QSS) a un archivo de assets."""
    search_dirs = []
    if getattr(sys, "_MEIPASS", None):
        search_dirs.append(Path(sys._MEIPASS) / "assets")
        search_dirs.append(Path(sys._MEIPASS))
    search_dirs.append(Path(__file__).resolve().parent.parent / "assets")
    search_dirs.append(Path.cwd() / "assets")

    for d in search_dirs:
        cand = d / filename
        if cand.is_file():
            return cand.as_posix()
    def_path = (Path(__file__).resolve().parent.parent / "assets" / filename).resolve()
    return def_path.as_posix()


ARROW_DOWN_URL = _get_asset_path("arrow_down.svg")
ARROW_DOWN_HOVER_URL = _get_asset_path("arrow_down_hover.svg")
ARROW_UP_URL = _get_asset_path("arrow_up.svg")
ARROW_UP_HOVER_URL = _get_asset_path("arrow_up_hover.svg")

DARK_THEME_RAW_QSS = """
/* Ventana principal, diálogos y explorador de archivos */
QMainWindow, QDialog, QFileDialog {
    background-color: #13141f;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Ubuntu', 'Inter', -apple-system, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e2e8f0;
    font-size: 13px;
}

/* Tabs / Pestañas */
QTabWidget::pane {
    border: 1px solid #2d314d;
    background-color: #1a1b2b;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #13141f;
    color: #94a3b8;
    padding: 7px 11px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid transparent;
    margin-right: 2px;
    font-weight: 600;
    font-size: 12px;
}

QTabBar::tab:hover {
    background-color: #23253b;
    color: #f8fafc;
}

QTabBar::tab:selected {
    background-color: #1a1b2b;
    color: #818cf8;
    border: 1px solid #2d314d;
    border-bottom: 2px solid #6366f1;
}

/* Grupos y contenedores (QGroupBox) */
QGroupBox {
    border: 1px solid #2d314d;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    padding-left: 12px;
    padding-right: 12px;
    padding-bottom: 12px;
    background-color: #1f2136;
    font-weight: bold;
    color: #cbd5e1;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    background-color: #282a45;
    border-radius: 4px;
    color: #a5b4fc;
}

/* Inputs de texto, comboboxes y selectores numéricos con altura mínima garantizada */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #151624;
    border: 1px solid #3b3f63;
    border-radius: 6px;
    min-height: 32px;
    padding: 4px 8px;
    color: #f8fafc;
    font-size: 12px;
    selection-background-color: #6366f1;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #818cf8;
    background-color: #181a2e;
}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: #0f1019;
    color: #64748b;
    border-color: #23253a;
}

/* Listas desplegables (QComboBox) */
QComboBox {
    padding-left: 8px;
    padding-right: 28px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #2d314d;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #1a1b2b;
}

QComboBox::drop-down:hover {
    background-color: #242740;
}

QComboBox::down-arrow {
    image: url(__ARROW_DOWN_URL__);
    width: 12px;
    height: 12px;
}

QComboBox::down-arrow:hover {
    image: url(__ARROW_DOWN_HOVER_URL__);
}

QComboBox QAbstractItemView {
    background-color: #1a1b2b;
    border: 1px solid #3b3f63;
    selection-background-color: #4f46e5;
    color: #f1f5f9;
    padding: 2px;
    border-radius: 6px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 4px 8px;
}

/* Selectores numéricos (QSpinBox y QDoubleSpinBox) */
QSpinBox, QDoubleSpinBox {
    padding-right: 26px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #2d314d;
    border-bottom: 1px solid #2d314d;
    border-top-right-radius: 5px;
    background-color: #1a1b2b;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #2e3252;
}

QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {
    background-color: #151624;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(__ARROW_UP_URL__);
    width: 10px;
    height: 10px;
}

QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {
    image: url(__ARROW_UP_HOVER_URL__);
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: padding;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #2d314d;
    border-bottom-right-radius: 5px;
    background-color: #1a1b2b;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #2e3252;
}

QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: #151624;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(__ARROW_DOWN_URL__);
    width: 10px;
    height: 10px;
}

QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {
    image: url(__ARROW_DOWN_HOVER_URL__);
}

/* Botones */
QPushButton {
    background-color: #2e3252;
    color: #f8fafc;
    border: 1px solid #3e4470;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #3d436e;
    border-color: #6366f1;
}

QPushButton:pressed {
    background-color: #252844;
}

QPushButton:disabled {
    background-color: #1c1d2e;
    color: #64748b;
    border-color: #23253b;
}

/* Botón de acción principal (Verde esmeralda / Ejecutar) */
QPushButton#btn_run {
    background-color: #059669;
    color: #ffffff;
    border: 1px solid #10b981;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 20px;
}

QPushButton#btn_run:hover {
    background-color: #10b981;
    border-color: #34d399;
}

QPushButton#btn_run:pressed {
    background-color: #047857;
}

/* Botón de cancelar (Rojo / Peligro) */
QPushButton#btn_cancel {
    background-color: #dc2626;
    color: #ffffff;
    border: 1px solid #ef4444;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 20px;
}

QPushButton#btn_cancel:hover {
    background-color: #ef4444;
}

QPushButton#btn_cancel:pressed {
    background-color: #b91c1c;
}

/* Barra de progreso */
QProgressBar {
    border: 1px solid #2d314d;
    background-color: #131420;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #4f46e5, stop:1 #06b6d4);
    border-radius: 5px;
}

/* Vistas de listas, tablas, árboles y explorador de archivos (QFileDialog) */
QTreeView, QListView, QTableView, QAbstractItemView, QListWidget {
    background-color: #151624;
    alternate-background-color: #191b2c;
    color: #f1f5f9;
    border: 1px solid #2d314d;
    border-radius: 6px;
    padding: 2px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
    outline: none;
    font-size: 12px;
}

QTreeView::item, QListView::item, QTableView::item, QListWidget::item {
    padding: 4px 6px;
    color: #f1f5f9;
    border-radius: 4px;
}

QTreeView::item:hover, QListView::item:hover, QTableView::item:hover, QListWidget::item:hover {
    background-color: #242740;
    color: #ffffff;
}

QTreeView::item:selected, QListView::item:selected, QTableView::item:selected, QListWidget::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
}

/* Cabeceras de columnas en explorador de archivos (Name, Size, Type, Date Modified) */
QHeaderView {
    background-color: #1a1b2b;
    border: none;
}

QHeaderView::section {
    background-color: #1f2136;
    color: #a5b4fc;
    padding: 5px 8px;
    border: 1px solid #2d314d;
    font-weight: 600;
    font-size: 11px;
}

QHeaderView::section:hover {
    background-color: #282a48;
    color: #ffffff;
}

/* Barra de herramientas y botones auxiliares de QFileDialog (<, >, ^, Nueva carpeta, Vistas) */
QToolButton {
    background-color: #2b3052;
    color: #f8fafc;
    border: 1px solid #454d80;
    border-radius: 6px;
    padding: 5px 7px;
    margin: 1px;
    font-weight: bold;
    min-width: 24px;
    min-height: 24px;
}

QToolButton:hover {
    background-color: #3b4372;
    border-color: #6366f1;
}

QToolButton:pressed {
    background-color: #1e223b;
}

QToolButton:checked {
    background-color: #4f46e5;
    border-color: #818cf8;
}

/* Botones de acción dentro de diálogos y QFileDialog (Open, Choose, Cancel) */
QDialog QPushButton, QFileDialog QPushButton {
    background-color: #2b3052;
    color: #f8fafc;
    border: 1px solid #454d80;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
    min-height: 28px;
}

QDialog QPushButton:hover, QFileDialog QPushButton:hover {
    background-color: #3b4372;
    border-color: #6366f1;
}

QDialog QPushButton:pressed, QFileDialog QPushButton:pressed {
    background-color: #1e223b;
}

/* Panel lateral de accesos directos (Places / Lugares) en diálogo de archivos */
QFileDialog QTreeView, QFileDialog QListView {
    background-color: #151624;
    color: #f1f5f9;
}

QFileDialog QWidget#sidebar, QFileDialog QListView[viewMode="0"] {
    background-color: #13141f;
    color: #cbd5e1;
    border-right: 1px solid #2d314d;
}

QSplitter::handle:vertical {
    height: 8px;
    background-color: #272a42;
    border-top: 1px solid #3b3f63;
    border-bottom: 1px solid #1a1c2d;
    border-radius: 3px;
    margin: 2px 4px;
}

QSplitter::handle:vertical:hover {
    background-color: #4f46e5;
    border-color: #818cf8;
}

QSplitter::handle:vertical:pressed {
    background-color: #6366f1;
}

QSplitter::handle:horizontal {
    width: 6px;
    background-color: #272a42;
    border-left: 1px solid #3b3f63;
    border-right: 1px solid #1a1c2d;
}

QSplitter::handle:horizontal:hover {
    background-color: #4f46e5;
}

/* Consola de Registros / Logs (QPlainTextEdit) */
QPlainTextEdit#log_console {
    background-color: #0d0e17;
    border: 1px solid #25283f;
    border-radius: 6px;
    color: #38bdf8;
    font-family: 'Fira Code', 'Cascadia Code', 'Consolas', 'DejaVu Sans Mono', monospace;
    font-size: 11px;
    padding: 8px;
}

/* Barras de desplazamiento (QScrollBar) */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollBar:vertical {
    border: none;
    background-color: #131420;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #333857;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4f46e5;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background-color: #131420;
    height: 10px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal {
    background-color: #333857;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #4f46e5;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Radio Buttons y CheckBoxes */
QRadioButton, QCheckBox {
    color: #e2e8f0;
    font-size: 13px;
    spacing: 7px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid #475569;
    background-color: #151624;
}

QRadioButton::indicator:checked {
    border: 2px solid #818cf8;
    background-color: #4f46e5;
}

QRadioButton::indicator:hover {
    border-color: #818cf8;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #151624;
}

QCheckBox::indicator:checked {
    border: 1px solid #818cf8;
    background-color: #4f46e5;
}

QCheckBox::indicator:hover {
    border-color: #818cf8;
}

/* Etiquetas de información */
QLabel#lbl_meta {
    color: #94a3b8;
    font-size: 12px;
}

QLabel#lbl_title {
    color: #f8fafc;
    font-size: 16px;
    font-weight: bold;
}

QLabel#badge_lossless {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1px solid #059669;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}
"""

DARK_THEME_QSS = (
    DARK_THEME_RAW_QSS
    .replace("__ARROW_DOWN_URL__", ARROW_DOWN_URL)
    .replace("__ARROW_DOWN_HOVER_URL__", ARROW_DOWN_HOVER_URL)
    .replace("__ARROW_UP_URL__", ARROW_UP_URL)
    .replace("__ARROW_UP_HOVER_URL__", ARROW_UP_HOVER_URL)
)


def get_dark_palette() -> QPalette:
    """
    Genera una paleta oscura completa para los componentes del sistema y diálogos de Qt
    (como QFileDialog), garantizando que las listas y árboles tengan fondo oscuro y texto claro.
    """
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#13141f"))
    palette.setColor(QPalette.WindowText, QColor("#e2e8f0"))
    palette.setColor(QPalette.Base, QColor("#151624"))
    palette.setColor(QPalette.AlternateBase, QColor("#1a1b2b"))
    palette.setColor(QPalette.ToolTipBase, QColor("#1a1b2b"))
    palette.setColor(QPalette.ToolTipText, QColor("#e2e8f0"))
    palette.setColor(QPalette.Text, QColor("#f1f5f9"))
    palette.setColor(QPalette.Button, QColor("#2e3252"))
    palette.setColor(QPalette.ButtonText, QColor("#f8fafc"))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Link, QColor("#38bdf8"))
    palette.setColor(QPalette.Highlight, QColor("#4f46e5"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    # Colores deshabilitados
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#64748b"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#64748b"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#64748b"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#2d314d"))
    return palette


def configure_dark_icon_theme() -> str:
    """
    Configura automáticamente un tema de iconos oscuro (como breeze-dark, Papirus-Dark,
    Yaru-dark, etc.) para que los iconos de carpetas, flechas de navegación y botones
    tengan el contraste adecuado (blanco/claro) sobre el fondo oscuro de la interfaz y diálogos.
    """
    try:
        current = QIcon.themeName()
        if current and "dark" in current.lower():
            return current

        candidates = [
            f"{current}-dark" if current else "",
            f"{current}-Dark" if current else "",
            "breeze-dark",
            "Papirus-Dark",
            "Yaru-dark",
            "Adwaita-dark",
            "elementary-dark",
            "breeze"
        ]
        candidates = [c for c in candidates if c]

        search_paths = QIcon.themeSearchPaths()
        for cand in candidates:
            for p in search_paths:
                theme_index = os.path.join(p, cand, "index.theme")
                if os.path.isfile(theme_index):
                    QIcon.setThemeName(cand)
                    return cand
    except Exception:
        pass
    return ""
