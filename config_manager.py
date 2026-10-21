#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Config Manager
Gestión centralizada de configuración persistente (config.json)
Manejo de Carpeta Base y Sugerencia de Carpetas automáticas.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Tuple, Optional


def get_app_dir() -> Path:
    """Devuelve la carpeta base de la aplicación (compatible con ejecutables portables congelados)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_config_file_path() -> Path:
    """Devuelve la ruta absoluta al archivo config.json."""
    return get_app_dir() / "config.json"


CONFIG_FILE = get_config_file_path()


def get_app_icon_path() -> Optional[str]:
    """Devuelve la ruta absoluta al archivo de icono de la aplicación (ico o png)."""
    search_dirs = []
    if getattr(sys, "_MEIPASS", None):
        search_dirs.append(Path(sys._MEIPASS) / "assets")
        search_dirs.append(Path(sys._MEIPASS))
    app_dir = get_app_dir()
    search_dirs.append(app_dir / "assets")
    search_dirs.append(app_dir)
    search_dirs.append(Path(__file__).resolve().parent / "assets")

    # En Windows preferir .ico (multiresolución para barra de título y barra de tareas), en Linux .png
    preferred_names = ["icon.ico", "icon.png"] if sys.platform == "win32" else ["icon.png", "icon.ico"]
    for d in search_dirs:
        for name in preferred_names:
            candidate = d / name
            if candidate.is_file():
                return str(candidate)
    return None


def open_path_in_os(target_path: str, is_directory: bool = False) -> bool:
    """
    Abre un archivo o carpeta en el explorador de archivos o reproductor predeterminado del SO.
    Compatible con Windows (os.startfile), Linux (xdg-open) y macOS (open).
    """
    if not target_path:
        return False

    path = os.path.abspath(target_path)
    if is_directory:
        if os.path.isfile(path):
            path = os.path.dirname(path)
        os.makedirs(path, exist_ok=True)
    else:
        if not os.path.exists(path):
            parent = os.path.dirname(path)
            if os.path.isdir(parent):
                path = parent
                is_directory = True
            else:
                return False

    # 1. Intentar mediante la API nativa de Qt si está disponible
    try:
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        url = QUrl.fromLocalFile(path)
        if QDesktopServices.openUrl(url):
            return True
    except Exception:
        pass

    # 2. Fallback a llamadas directas del SO
    try:
        if sys.platform == "win32":
            os.startfile(path)
            return True
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return True
        else:
            subprocess.Popen(["xdg-open", path])
            return True
    except Exception as e:
        print(f"Error al abrir en SO ({path}): {e}")
        return False


def make_clickable_folder_label(label, get_folder_fn):
    """
    Configura un QLabel que muestra una ruta de carpeta para que, al hacer clic
    sobre el texto o el enlace, se abra automáticamente en el explorador de archivos.
    """
    try:
        from PyQt5.QtCore import Qt
        label.setCursor(Qt.PointingHandCursor)
        label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(lambda path: open_path_in_os(path, is_directory=True))
        label.setToolTip("📁 Haz clic aquí para abrir esta carpeta en el explorador de archivos")

        def on_mouse_press(event):
            folder = get_folder_fn()
            if folder:
                open_path_in_os(folder, is_directory=True)

        label.mousePressEvent = on_mouse_press
    except Exception:
        pass


def get_default_base_dir() -> str:
    """Devuelve una carpeta base por defecto según el sistema operativo."""
    home = Path.home()
    # Buscar carpetas típicas en español/inglés
    candidates = [
        home / "Vídeos" / "MyFFmpeg_Output",
        home / "Videos" / "MyFFmpeg_Output",
        home / "Documentos" / "MyFFmpeg_Output",
        home / "Documents" / "MyFFmpeg_Output",
        home / "MyFFmpeg_Output"
    ]
    for c in candidates:
        if c.parent.is_dir():
            return str(c)
    return str(home / "MyFFmpeg_Output")


DEFAULT_CONTEXT_ACTIONS = [
    {
        "id": "quick_mp3",
        "name": "⚡ Rápido: Convertir a MP3",
        "type": "quick",
        "command_template": 'ffmpeg -y -i "{input}" "{output_no_ext}.mp3"',
        "enabled": True,
        "is_custom": False,
        "icon": "audio-x-generic"
    },
    {
        "id": "quick_wav",
        "name": "⚡ Rápido: Convertir a WAV",
        "type": "quick",
        "command_template": 'ffmpeg -y -i "{input}" "{output_no_ext}.wav"',
        "enabled": True,
        "is_custom": False,
        "icon": "audio-x-generic"
    },
    {
        "id": "quick_audio_copy",
        "name": "⚡ Rápido: Extraer Audio Original (Stream Copy)",
        "type": "quick",
        "command_template": 'ffmpeg -y -i "{input}" -vn -c:a copy "{output_no_ext}_audio.m4a"',
        "enabled": False,
        "is_custom": False,
        "icon": "audio-x-generic"
    },
    {
        "id": "gui_audio",
        "name": "🎵 Abrir en Conversor de Audio (MP3 / WAV)",
        "type": "gui",
        "tab": "audio",
        "command_template": "",
        "enabled": True,
        "is_custom": False,
        "icon": "audio-x-generic"
    },
    {
        "id": "gui_video",
        "name": "🎬 Abrir en Conversor de Video",
        "type": "gui",
        "tab": "video",
        "command_template": "",
        "enabled": True,
        "is_custom": False,
        "icon": "video-x-generic"
    },
    {
        "id": "gui_frames",
        "name": "🎞️ Abrir en Extractor de Fotogramas",
        "type": "gui",
        "tab": "frames",
        "command_template": "",
        "enabled": True,
        "is_custom": False,
        "icon": "image-x-generic"
    },
    {
        "id": "gui_segment",
        "name": "✂️ Abrir en Segmentar Video",
        "type": "gui",
        "tab": "segment",
        "command_template": "",
        "enabled": True,
        "is_custom": False,
        "icon": "edit-cut"
    },
    {
        "id": "gui_main",
        "name": "📂 Abrir en MyFFmpeg GUI",
        "type": "gui",
        "tab": None,
        "command_template": "",
        "enabled": True,
        "is_custom": False,
        "icon": "applications-multimedia"
    }
]


def load_config() -> dict:
    default_cfg = {
        "ffmpeg_path": "",
        "ffprobe_path": "",
        "base_output_dir": get_default_base_dir(),
        "auto_suggest_subfolders": True,
        "default_save_location": "same_folder",  # "same_folder" o "base_dir"
        "context_menu_actions": [dict(a) for a in DEFAULT_CONTEXT_ACTIONS]
    }
    cfg_path = get_config_file_path()
    if cfg_path.is_file():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
                # Asegurar que existan las acciones por defecto si faltan
                if "context_menu_actions" not in data:
                    default_cfg["context_menu_actions"] = [dict(a) for a in DEFAULT_CONTEXT_ACTIONS]
        except Exception:
            pass
    return default_cfg


def save_config(cfg: dict):
    try:
        cfg_path = get_config_file_path()
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        pass


def get_context_actions() -> list:
    """Devuelve la lista de acciones configuradas para el menú contextual."""
    cfg = load_config()
    actions = cfg.get("context_menu_actions")
    if not actions:
        actions = [dict(a) for a in DEFAULT_CONTEXT_ACTIONS]
        cfg["context_menu_actions"] = actions
        save_config(cfg)
    return actions


def save_context_actions(actions: list):
    """Guarda la lista de acciones del menú contextual."""
    cfg = load_config()
    cfg["context_menu_actions"] = actions
    save_config(cfg)


def add_custom_quick_action(name: str, command_template: str) -> dict:
    """Añade una nueva acción rápida personalizada al menú contextual."""
    import time
    action_id = f"custom_{int(time.time())}"
    new_action = {
        "id": action_id,
        "name": name.strip(),
        "type": "quick",
        "command_template": command_template.strip(),
        "enabled": True,
        "is_custom": True,
        "icon": "system-run"
    }
    actions = get_context_actions()
    actions.append(new_action)
    save_context_actions(actions)
    return new_action


def delete_context_action(action_id: str) -> bool:
    """Elimina una acción personalizada por su ID."""
    actions = get_context_actions()
    initial_len = len(actions)
    actions = [a for a in actions if a.get("id") != action_id]
    if len(actions) < initial_len:
        save_context_actions(actions)
        return True
    return False


def toggle_context_action(action_id: str, enabled: bool) -> bool:
    """Activa o desactiva una acción por su ID."""
    actions = get_context_actions()
    found = False
    for a in actions:
        if a.get("id") == action_id:
            a["enabled"] = enabled
            found = True
            break
    if found:
        save_context_actions(actions)
    return found


def move_context_action(action_id: str, direction: int) -> bool:
    """Mueve una acción hacia arriba (direction=-1) o hacia abajo (direction=1)."""
    actions = get_context_actions()
    idx = next((i for i, a in enumerate(actions) if a.get("id") == action_id), -1)
    if idx == -1:
        return False
    new_idx = idx + direction
    if 0 <= new_idx < len(actions):
        actions[idx], actions[new_idx] = actions[new_idx], actions[idx]
        save_context_actions(actions)
        return True
    return False


def get_base_output_dir() -> str:
    cfg = load_config()
    b_dir = cfg.get("base_output_dir")
    if not b_dir:
        b_dir = get_default_base_dir()
    return b_dir


def is_auto_suggest_subfolders() -> bool:
    cfg = load_config()
    return bool(cfg.get("auto_suggest_subfolders", True))


def get_default_save_location() -> str:
    cfg = load_config()
    return cfg.get("default_save_location", "same_folder")


def ensure_dir_exists(directory: str):
    """Crea la carpeta si no existe."""
    if directory:
        os.makedirs(directory, exist_ok=True)


def suggest_output_path(
    input_file_or_folder: str,
    suffix: str = "",
    extension: str = "",
    is_destination_folder: bool = False,
    override_base_dir: Optional[str] = None,
    override_auto_subfolders: Optional[bool] = None,
    same_folder_as_input: bool = False
) -> str:
    """
    Calcula la ruta sugerida de salida:
    1. Si same_folder_as_input=True: Guarda en la misma carpeta que el original con mismo nombre y nueva extensión.
    2. Si same_folder_as_input=False: Usa la carpeta base configurada (o la indicada).
    3. Si auto_suggest_subfolders está activo, crea/sugiere una subcarpeta con el nombre del archivo.
    """
    if not input_file_or_folder:
        return ""

    input_path = Path(input_file_or_folder)
    file_stem = input_path.stem if input_path.is_file() or not is_destination_folder else input_path.name
    if not file_stem:
        file_stem = "archivo"

    # Caso 1: Guardar en la misma carpeta que el archivo original
    if same_folder_as_input and input_path.parent.is_dir():
        target_dir = input_path.parent
        if is_destination_folder:
            return str(target_dir / f"{file_stem}{suffix}")

        if extension and not extension.startswith("."):
            extension = f".{extension}"

        # Si coincide con la misma extensión y no hay sufijo, evitar sobreescribir el original
        if input_path.suffix.lower() == extension.lower() and not suffix:
            filename = f"{file_stem}_convertido{extension}"
        else:
            filename = f"{file_stem}{suffix}{extension}"

        return str(target_dir / filename)

    # Caso 2: Guardar en la Carpeta Base configurada
    base_dir = override_base_dir if override_base_dir else get_base_output_dir()
    use_subfolder = override_auto_subfolders if override_auto_subfolders is not None else is_auto_suggest_subfolders()

    base_p = Path(base_dir)

    if use_subfolder:
        target_dir = base_p / file_stem
    else:
        target_dir = base_p

    # Si lo que se pide como salida es una carpeta (ej. fotogramas o segmentos)
    if is_destination_folder:
        if not use_subfolder and suffix:
            target_dir = target_dir / f"{file_stem}{suffix}"
        return str(target_dir)

    # Si es un archivo de salida
    if extension and not extension.startswith("."):
        extension = f".{extension}"

    filename = f"{file_stem}{suffix}{extension}"
    return str(target_dir / filename)
