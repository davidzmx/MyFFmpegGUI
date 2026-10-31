#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFmpeg Core Module
Manejo multiplataforma (Windows/Linux/macOS) de ejecutables, metadatos y generación de comandos FFmpeg.
"""

import os
import sys
import shutil
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple


def get_app_dir() -> Path:
    """Devuelve la carpeta base de la aplicación (compatible con ejecutables portables congelados)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_default_ffmpeg_paths() -> Tuple[Optional[str], Optional[str]]:
    """
    Busca ejecutables ffmpeg y ffprobe de forma multiplataforma:
    1. Variable de entorno personal FFMPEG_PATH / FFPROBE_PATH
    2. En el directorio actual o carpeta de la aplicación (incluyendo .exe en Windows)
    3. En el PATH del sistema operativo (shutil.which)
    """
    app_dir = get_app_dir()

    is_windows = sys.platform.startswith("win")
    ffmpeg_exe_name = "ffmpeg.exe" if is_windows else "ffmpeg"
    ffprobe_exe_name = "ffprobe.exe" if is_windows else "ffprobe"

    # 1. Custom env var
    ffmpeg_path = os.environ.get("FFMPEG_PATH")
    ffprobe_path = os.environ.get("FFPROBE_PATH")

    # 2. Local directory (e.g. portable bundle on Windows/Linux)
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        candidate = app_dir / ffmpeg_exe_name
        if candidate.is_file():
            ffmpeg_path = str(candidate)
        else:
            candidate_bin = app_dir / "bin" / ffmpeg_exe_name
            if candidate_bin.is_file():
                ffmpeg_path = str(candidate_bin)

    if not ffprobe_path or not os.path.isfile(ffprobe_path):
        candidate = app_dir / ffprobe_exe_name
        if candidate.is_file():
            ffprobe_path = str(candidate)
        else:
            candidate_bin = app_dir / "bin" / ffprobe_exe_name
            if candidate_bin.is_file():
                ffprobe_path = str(candidate_bin)

    # 3. System PATH
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        ffmpeg_path = shutil.which("ffmpeg")

    if not ffprobe_path or not os.path.isfile(ffprobe_path):
        ffprobe_path = shutil.which("ffprobe")

    return ffmpeg_path, ffprobe_path


def get_ffplay_path(ffmpeg_path: str = None) -> Optional[str]:
    """
    Localiza el ejecutable ffplay correspondiente al ffmpeg configurado, en config o en PATH.
    """
    try:
        import config_manager
        cfg_p = config_manager.load_config().get("ffplay_path")
        if cfg_p and os.path.isfile(cfg_p):
            return cfg_p
    except Exception:
        pass

    if ffmpeg_path:
        parent_dir = Path(ffmpeg_path).resolve().parent
        for candidate in ("ffplay.exe", "ffplay"):
            target = parent_dir / candidate
            if target.is_file():
                return str(target)

    for cmd in ("ffplay", "ffplay.exe"):
        found = shutil.which(cmd)
        if found and os.path.isfile(found):
            return found

    return None


def get_ffmpeg_version(ffmpeg_path: str) -> str:
    """Obtiene la versión instalada de FFmpeg."""
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        return "No encontrado"
    try:
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        res = subprocess.run(
            [ffmpeg_path, "-version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            check=True
        )
        first_line = res.stdout.splitlines()[0] if res.stdout else "Desconocida"
        return first_line
    except Exception as e:
        return f"Error al verificar: {e}"


def format_command_for_display(cmd: List[str]) -> str:
    """
    Convierte una lista de argumentos de comando en una cadena ejecutable en terminal (Windows/Linux).
    Asegura que los argumentos con espacios estén debidamente entrecomillados.
    """
    if not cmd:
        return ""
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(cmd)
    else:
        import shlex
        return shlex.join(cmd)



def get_media_info(filepath: str, ffprobe_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene información detallada del archivo multimedia usando ffprobe en formato JSON.
    Devuelve duración, resolución, códec de video, códec de audio, fps, etc.
    """
    if not ffprobe_path:
        _, ffprobe_path = get_default_ffmpeg_paths()

    info: Dict[str, Any] = {
        "duration": 0.0,
        "duration_str": "00:00:00",
        "format_name": "",
        "size_bytes": 0,
        "video_streams": [],
        "audio_streams": [],
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "video_codec": "",
        "audio_codec": "",
        "raw": {}
    }

    if not ffprobe_path or not os.path.isfile(ffprobe_path) or not os.path.isfile(filepath):
        return info

    try:
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            filepath
        ]
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            check=True
        )
        data = json.loads(res.stdout)
        info["raw"] = data

        format_info = data.get("format", {})
        dur = float(format_info.get("duration", 0.0))
        info["duration"] = dur
        info["size_bytes"] = int(format_info.get("size", 0))
        info["format_name"] = format_info.get("format_name", "")

        # Formato de tiempo HH:MM:SS
        hours = int(dur // 3600)
        minutes = int((dur % 3600) // 60)
        seconds = int(dur % 60)
        info["duration_str"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        streams = data.get("streams", [])
        for st in streams:
            codec_type = st.get("codec_type")
            if codec_type == "video":
                info["video_streams"].append(st)
                if not info["video_codec"]:
                    info["video_codec"] = st.get("codec_name", "")
                    info["width"] = int(st.get("width", 0))
                    info["height"] = int(st.get("height", 0))
                    r_frame_rate = st.get("r_frame_rate", "0/1")
                    if "/" in r_frame_rate:
                        num, den = r_frame_rate.split("/")
                        if float(den) > 0:
                            info["fps"] = round(float(num) / float(den), 2)
                    dar = st.get("display_aspect_ratio", "")
                    if dar and ":" in dar:
                        try:
                            dnum, dden = dar.split(":")
                            if float(dden) > 0 and float(dnum) > 0:
                                info["dar"] = float(dnum) / float(dden)
                        except Exception:
                            pass
            elif codec_type == "audio":
                info["audio_streams"].append(st)
                if not info["audio_codec"]:
                    info["audio_codec"] = st.get("codec_name", "")

    except Exception:
        pass

    return info


def build_audio_convert_command(
    ffmpeg_path: str,
    input_file: str,
    output_file: str,
    mode: str = "mp3_320k",  # "mp3_320k", "mp3_256k", "mp3_192k", "mp3_vbr0", "copy", "flac", "wav_16", "wav_24", "wav_32", "wav"
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    keep_metadata: bool = True
) -> List[str]:
    """
    Construye el comando para extraer/convertir audio manteniendo la máxima calidad posible (MP3, WAV, FLAC, etc.).
    """
    cmd = [ffmpeg_path, "-y", "-i", input_file, "-vn"]

    if mode == "copy":
        # Sin pérdida absoluta: copia el stream de audio original sin recodificar
        cmd.extend(["-c:a", "copy"])
    elif mode == "flac":
        # Sin pérdida PCM comprimida FLAC
        cmd.extend(["-c:a", "flac"])
    elif mode in ("wav_16", "wav"):
        # WAV PCM lineal 16-bit (Calidad CD)
        cmd.extend(["-c:a", "pcm_s16le"])
    elif mode == "wav_24":
        # WAV PCM lineal 24-bit (Alta Definición de Estudio)
        cmd.extend(["-c:a", "pcm_s24le"])
    elif mode == "wav_32":
        # WAV PCM Float 32-bit (Máxima precisión matemática)
        cmd.extend(["-c:a", "pcm_f32le"])
    elif mode == "mp3_vbr0":
        # Calidad máxima perceptual en MP3 usando LAME VBR 0
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "0"])
    elif mode == "mp3_256k":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "256k"])
    elif mode == "mp3_192k":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
    else:  # Por defecto "mp3_320k"
        # Máxima tasa de bits de MP3 CBR
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])

    if sample_rate and sample_rate > 0:
        cmd.extend(["-ar", str(sample_rate)])

    if channels and channels > 0:
        cmd.extend(["-ac", str(channels)])

    if keep_metadata:
        cmd.extend(["-map_metadata", "0"])

    cmd.append(output_file)
    return cmd


def format_volume_filter(val: float) -> str:
    """Formatea un multiplicador numérico de volumen para el filtro 'volume' de FFmpeg (ej. 1.0, 0.35, 1.5)."""
    v = max(0.0, float(val))
    if abs(v - round(v)) < 0.001:
        return f"{v:.1f}"
    return f"{v:.2f}".rstrip('0')


def format_seconds_to_time_str(sec: float) -> str:
    """Formatea segundos en formato HH:MM:SS.cs para visualización de tiempos precisos."""
    total_sec = max(0.0, float(sec))
    hours = int(total_sec // 3600)
    minutes = int((total_sec % 3600) // 60)
    seconds = int(total_sec % 60)
    centiseconds = int(round((total_sec - int(total_sec)) * 100))
    if centiseconds >= 100:
        centiseconds = 0
        seconds += 1
        if seconds >= 60:
            seconds = 0
            minutes += 1
            if minutes >= 60:
                minutes = 0
                hours += 1
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def build_add_audio_to_video_command(
    ffmpeg_path: str,
    video_file: str,
    audio_file: str,
    output_file: str,
    audio_mode: str = "replace",  # "replace", "mix", "add_track"
    audio_codec: str = "aac",     # "aac", "copy", "mp3", "flac"
    shortest: bool = True,
    has_original_audio: bool = True,
    volume_orig: float = 1.0,
    volume_added: float = 1.0,
    audio_delay_sec: float = 0.0,
    audio_start_offset_sec: float = 0.0
) -> List[str]:
    """
    Construye el comando FFmpeg para incorporar, reemplazar o mezclar audio en un video.
    El video se procesa con Stream Copy (-c:v copy) 100% sin pérdida de calidad ni tiempo.
    - 'replace': Reemplaza el audio existente o añade audio al video si era mudo.
    - 'mix': Mezcla el audio original del video con la nueva pista de audio, con control independiente de volumen.
    - 'add_track': Conserva el audio original y añade la nueva pista como pista secundaria.
    - shortest: Corta el audio si es más largo que el video para evitar fotogramas congelados.
    - volume_orig: Multiplicador de volumen del audio original (1.0 = 100%).
    - volume_added: Multiplicador de volumen del audio agregado (1.0 = 100%).
    - audio_delay_sec: Segundo del video en el que empieza a sonar el audio (adelay).
    - audio_start_offset_sec: Segundo del archivo de audio desde el que se empieza a reproducir (-ss).
    """
    cmd = [
        ffmpeg_path, "-y",
        "-i", video_file
    ]

    # Punto de inicio en el archivo de audio (salta la intro / adelanto)
    if audio_start_offset_sec and audio_start_offset_sec > 0.001:
        cmd.extend(["-ss", f"{audio_start_offset_sec:.3f}"])

    cmd.extend(["-i", audio_file])

    # Video stream siempre en copia directa (sin pérdida y ultrarrápido)
    cmd.extend(["-c:v", "copy"])

    has_filter = False
    delay_ms = int(round(audio_delay_sec * 1000)) if (audio_delay_sec and audio_delay_sec > 0.001) else 0

    if audio_mode == "mix" and has_original_audio:
        has_filter = True
        vo_str = format_volume_filter(volume_orig)
        va_str = format_volume_filter(volume_added)
        if delay_ms > 0:
            filter_str = (
                f"[0:a]volume={vo_str}[a0];"
                f"[1:a]adelay={delay_ms}:all=1,volume={va_str}[a1];"
                f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        else:
            filter_str = (
                f"[0:a]volume={vo_str}[a0];"
                f"[1:a]volume={va_str}[a1];"
                f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "0:v:0",
            "-map", "[aout]"
        ])
    elif audio_mode == "add_track":
        if delay_ms > 0:
            has_filter = True
            cmd.extend([
                "-filter_complex", f"[1:a]adelay={delay_ms}:all=1[a1]",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-map", "[a1]"
            ])
        else:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "0:a?",
                "-map", "1:a:0"
            ])
    else:
        # "replace" (o "mix" si el video original no contenía audio)
        if delay_ms > 0:
            has_filter = True
            cmd.extend([
                "-filter_complex", f"[1:a]adelay={delay_ms}:all=1[aout]",
                "-map", "0:v:0",
                "-map", "[aout]"
            ])
        else:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0"
            ])

    # Determinar parámetros de codificación de audio
    if audio_codec == "mp3":
        a_codec_args = ["-c:a", "libmp3lame", "-b:a", "320k"]
    elif audio_codec == "flac":
        a_codec_args = ["-c:a", "flac"]
    elif audio_codec == "copy" and not has_filter:
        a_codec_args = ["-c:a", "copy"]
    else:
        # Predeterminado o forzado por filtro (adelay o amix): AAC 256k
        a_codec_args = ["-c:a", "aac", "-b:a", "256k"]

    cmd.extend(a_codec_args)

    if shortest:
        cmd.append("-shortest")

    cmd.append(output_file)
    return cmd



def build_convert_video_command(
    ffmpeg_path: str,
    input_file: str,
    output_file: str,
    mode: str = "copy",  # "copy", "h264_lossless", "h264_visually_lossless", "h264_standard", "h265", "prores", "vp9", "gif"
    resolution: Optional[str] = None,  # "original" o "1920x1080", etc.
    fps: Optional[float] = None,
    audio_mode: str = "copy",  # "copy", "aac", "mp3", "flac", "none"
    map_all_streams: bool = True
) -> List[str]:
    """
    Construye el comando para convertir entre formatos de video (MP4, MKV, MOV, AVI, WebM, TS, GIF, etc.).
    - mode='copy': Cambio de contenedor ultra rápido 100% sin pérdida de calidad.
    - mode='h264_lossless': CRF 0 sin pérdida de video.
    - mode='h264_visually_lossless': CRF 17 compatible y de altísima fidelidad.
    - mode='gif': Genera GIF de alta calidad usando paleta optimizada (palettegen).
    """
    cmd = [ffmpeg_path, "-y", "-i", input_file]

    # Caso especial: GIF de alta calidad con paleta optimizada
    if mode == "gif":
        vf_filters = []
        if fps and fps > 0:
            vf_filters.append(f"fps={fps}")
        else:
            vf_filters.append("fps=15")

        if resolution and resolution != "original":
            vf_filters.append(f"scale={resolution.replace('x', ':')}:flags=lanczos")
        else:
            vf_filters.append("scale=iw:ih:flags=lanczos")

        filter_str = ",".join(vf_filters)
        cmd.extend([
            "-vf", f"{filter_str},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            output_file
        ])
        return cmd

    # Mapear todos los streams (subtítulos, múltiples pistas de audio) si se solicita
    if map_all_streams and mode != "copy":
        cmd.extend(["-map", "0"])
    elif map_all_streams and mode == "copy":
        cmd.extend(["-map", "0"])

    # Filtros de video (escalado o fps) si no es copia directa
    vf_list = []
    if resolution and resolution != "original":
        vf_list.append(f"scale={resolution.replace('x', ':')}")
    if fps and fps > 0:
        vf_list.append(f"fps={fps}")

    vf_arg = ",".join(vf_list) if vf_list else None

    # Configuración de Video
    if mode == "copy":
        cmd.extend(["-c:v", "copy"])
    elif mode == "h264_lossless":
        cmd.extend(["-c:v", "libx264", "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    elif mode == "h264_visually_lossless":
        cmd.extend(["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    elif mode == "h264_standard":
        cmd.extend(["-c:v", "libx264", "-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    elif mode == "h265":
        cmd.extend(["-c:v", "libx265", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    elif mode == "prores":
        cmd.extend(["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    elif mode == "vp9":
        cmd.extend(["-c:v", "libvpx-vp9", "-crf", "20", "-b:v", "0", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"])
        if vf_arg:
            cmd.extend(["-vf", vf_arg])

    # Configuración de Audio
    is_webm = output_file.lower().endswith(".webm")
    if audio_mode == "none":
        cmd.append("-an")
    elif is_webm:
        # WebM solo admite Opus o Vorbis
        if audio_mode == "flac":
            cmd.extend(["-c:a", "libvorbis"])
        else:
            cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
    elif audio_mode == "copy" or mode == "copy":
        cmd.extend(["-c:a", "copy"])
    elif audio_mode == "opus":
        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
    elif audio_mode == "aac":
        cmd.extend(["-c:a", "aac", "-b:a", "256k"])
    elif audio_mode == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
    elif audio_mode == "flac":
        cmd.extend(["-c:a", "flac"])
    else:
        cmd.extend(["-c:a", "copy"])

    # Subtítulos si se copian streams
    if mode == "copy":
        cmd.extend(["-c:s", "copy"])

    cmd.append(output_file)
    return cmd



def build_extract_frames_command(
    ffmpeg_path: str,
    input_file: str,
    output_pattern: str,
    fmt: str = "png",  # "png" (lossless), "jpg", "webp", "tiff" (lossless)
    fps_mode: str = "all",  # "all", "1fps", "custom_fps", "keyframes"
    custom_fps: float = 1.0,
    start_time: Optional[str] = None,
    duration: Optional[str] = None
) -> List[str]:
    """
    Construye el comando para extraer fotogramas sin pérdida de resolución ni calidad.
    """
    cmd = [ffmpeg_path, "-y"]

    if start_time:
        cmd.extend(["-ss", start_time])
    if duration:
        cmd.extend(["-t", duration])

    cmd.extend(["-i", input_file])

    # Filtros de fotogramas
    if fps_mode == "keyframes":
        # Extraer solo fotogramas I (Keyframes)
        cmd.extend(["-vf", "select='eq(pict_type\\,PICT_TYPE_I)'", "-vsync", "vfr"])
    elif fps_mode == "1fps":
        cmd.extend(["-vf", "fps=1"])
    elif fps_mode == "custom_fps" and custom_fps > 0:
        cmd.extend(["-vf", f"fps={custom_fps}"])
    else:
        # Extraer todos los fotogramas nativos sin duplicar ni descartar
        cmd.extend(["-fps_mode", "passthrough"])

    # Códec de imagen para fidelidad máxima
    if fmt == "png":
        # PNG es intrínsecamente sin pérdida
        cmd.extend(["-c:v", "png"])
    elif fmt == "tiff":
        cmd.extend(["-c:v", "tiff"])
    elif fmt == "webp":
        cmd.extend(["-c:v", "libwebp", "-lossless", "1"])
    elif fmt == "jpg":
        # Calidad máxima JPG (q:v 1)
        cmd.extend(["-q:v", "1"])

    cmd.append(output_pattern)
    return cmd


def build_cut_video_segment_command(
    ffmpeg_path: str,
    input_file: str,
    output_file: str,
    start_sec: float,
    end_sec: float,
    mode: str = "exact"  # "exact" o "copy"
) -> List[str]:
    """
    Construye el comando para extraer un intervalo de tiempo específico [start_sec, end_sec] de un video.
    - 'exact': Corte con recodificación exacta al milisegundo (-ss ... -to ... -c:v libx264 -crf 17 -c:a aac).
    - 'copy': Copia directa de streams (-c copy -map 0) sin recodificar.
    """
    cmd = [ffmpeg_path, "-y"]

    if mode == "copy":
        # Copia de streams buscando keyframes cercanos
        cmd.extend([
            "-ss", f"{start_sec:.3f}",
            "-to", f"{end_sec:.3f}",
            "-i", input_file,
            "-c", "copy",
            "-map", "0",
            output_file
        ])
    else:
        # Corte exacto con máxima fidelidad visual y de audio
        cmd.extend([
            "-ss", f"{start_sec:.3f}",
            "-to", f"{end_sec:.3f}",
            "-i", input_file,
            "-c:v", "libx264",
            "-crf", "17",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0",
            output_file
        ])

    return cmd


def find_sequence_start_number(folder: str, pattern: str) -> Optional[int]:
    """
    Detecta el número inicial de una secuencia de imágenes (ej. frame_%06d.png)
    en una carpeta, especialmente útil si se han eliminado fotogramas iniciales.
    """
    if not folder or not os.path.isdir(folder) or not pattern:
        return None
    try:
        parts = re.split(r"(%0?\d*d)", pattern)
        if len(parts) == 3:
            prefix = re.escape(parts[0])
            suffix = re.escape(parts[2])
            regex = re.compile(rf"^{prefix}(\d+){suffix}$", re.IGNORECASE)
        else:
            regex_pattern = re.sub(r"%0?\d*d", r"(\d+)", pattern)
            regex = re.compile(rf"^{regex_pattern}$", re.IGNORECASE)

        min_num = None
        for filename in os.listdir(folder):
            m = regex.match(filename)
            if m:
                val = int(m.group(1))
                if min_num is None or val < min_num:
                    min_num = val
        return min_num
    except Exception:
        return None


def build_create_video_command(
    ffmpeg_path: str,
    input_pattern: str,
    output_file: str,
    fps: float = 30.0,
    codec_preset: str = "h264_lossless",  # "h264_lossless", "h264_visually_lossless", "prores", "vp9_lossless"
    audio_file: Optional[str] = None,
    start_number: Optional[int] = None
) -> List[str]:
    """
    Construye el comando para ensamblar un video a partir de fotogramas secuenciales.
    """
    cmd = [ffmpeg_path, "-y", "-framerate", str(fps)]
    if start_number is not None and start_number >= 0:
        cmd.extend(["-start_number", str(start_number)])
    cmd.extend(["-i", input_pattern])

    if audio_file and os.path.isfile(audio_file):
        cmd.extend(["-i", audio_file])

    gop_size = max(1, int(round(fps * 2)))  # Keyframe cada 2 segundos para edición y segmentación óptima

    if codec_preset == "h264_lossless":
        # H.264 CRF 0 es matemáticamente sin pérdida
        # yuv420p permite reproducirlo en reproductores habituales sin distorsión visible
        cmd.extend(["-c:v", "libx264", "-crf", "0", "-preset", "slow", "-g", str(gop_size), "-pix_fmt", "yuv420p"])
    elif codec_preset == "h264_visually_lossless":
        # CRF 17 es imperceptiblemente idéntico a la fuente original y altamente compatible
        cmd.extend(["-c:v", "libx264", "-crf", "17", "-preset", "slow", "-g", str(gop_size), "-pix_fmt", "yuv420p"])
    elif codec_preset == "prores":
        # Apple ProRes 422 HQ (estándar de edición profesional sin pérdida perceptual)
        cmd.extend(["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"])
    elif codec_preset == "vp9_lossless":
        # WebM / VP9 Lossless
        cmd.extend(["-c:v", "libvpx-vp9", "-lossless", "1", "-g", str(gop_size), "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-g", str(gop_size), "-pix_fmt", "yuv420p"])

    if audio_file and os.path.isfile(audio_file):
        cmd.extend(["-c:a", "copy", "-shortest"])

    cmd.append(output_file)
    return cmd


def build_segment_command(
    ffmpeg_path: str,
    input_file: str,
    output_pattern: str,
    segment_duration_sec: int = 15,
    mode: str = "exact"  # Por defecto: "exact" (corte exacto al segundo con CRF 17) o "copy" (copia directa)
) -> List[str]:
    """
    Construye el comando para dividir un video en segmentos de duración configurable.
    - 'exact': Fuerza keyframe en cada múltiplo de segmento para longitud exacta sin pérdida visual (predeterminado).
    - 'copy': Modo directo sin pérdida de calidad (-c copy) cortando en keyframes.
    """
    cmd = [ffmpeg_path, "-y", "-i", input_file]

    if mode == "copy":
        # Copia directa sin pérdida de video ni audio
        cmd.extend([
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", str(segment_duration_sec),
            "-segment_time_delta", "0.5",
            "-reset_timestamps", "1"
        ])
    else:
        # Modo corte exacto: fuerza I-frames en cada intervalo manteniendo CRF 17 (calidad visual sin pérdida)
        force_kf = f"expr:gte(t,n_forced*{segment_duration_sec})"
        cmd.extend([
            "-c:v", "libx264",
            "-crf", "17",
            "-preset", "fast",
            "-force_key_frames", force_kf,
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0",
            "-f", "segment",
            "-segment_time", str(segment_duration_sec),
            "-segment_time_delta", "0.1",
            "-reset_timestamps", "1"
        ])

    cmd.append(output_pattern)
    return cmd


def build_concat_command(
    ffmpeg_path: str,
    list_file_path: str = None,
    output_file: str = "",
    mode: str = "copy",  # "copy" (demuxer concat sin recodificar) o "reencode" (si provienen de formatos distintos)
    concat_list_file: str = None,
    audio_file: Optional[str] = None,
    audio_mode: str = "replace",  # "replace", "mix", "add_track"
    shortest: bool = True,
    anti_stutter: bool = False,
    stutter_mode: str = "auto",  # "auto" o "manual"
    drop_start_frames: int = 1,
    file_paths: Optional[List[str]] = None,
    volume_orig: float = 1.0,
    volume_added: float = 1.0
) -> List[str]:
    """
    Construye el comando para unir segmentos con soporte opcional para:
    - 'copy': Modo demuxer concat sin pérdida y sin recodificación.
    - 'reencode': Recodificación con libx264 CRF 17.
    - anti_stutter: Elimina micro-stutter / solapamiento entre segmentos (requiere recodificación):
        * 'auto': Utiliza mpdecimate para detectar y descartar fotogramas idénticos/congelados en las uniones.
        * 'manual': Descarta exactamente N fotogramas iniciales de cada segmento posterior mediante filter_complex.
    - audio_file: Archivo de audio externo (MP3, WAV, AAC, etc.) a incorporar al archivo unificado.
    - audio_mode:
        * 'replace': Reemplaza el audio existente o añade audio al video unificado.
        * 'mix': Mezcla el audio existente de los videos con el audio externo (con soporte para volumen individual).
        * 'add_track': Conserva el audio original y añade el nuevo audio como segunda pista.
    - shortest: Corta el audio si es más largo que el video unido para evitar fotograma congelado.
    - volume_orig: Multiplicador de volumen del audio original de los videos (1.0 = 100%).
    - volume_added: Multiplicador de volumen del audio agregado (1.0 = 100%).
    """
    actual_list = list_file_path or concat_list_file or ""
    has_audio = bool(audio_file and str(audio_file).strip())
    audio_target = str(audio_file).strip() if has_audio else None

    vo_str = format_volume_filter(volume_orig)
    va_str = format_volume_filter(volume_added)

    # Si se activa anti_stutter, se requiere recodificación obligatoriamente
    if anti_stutter:
        mode = "reencode"

        # Intentar extraer file_paths desde actual_list si no se suministró en modo manual
        if stutter_mode == "manual":
            if (not file_paths or len(file_paths) < 2) and actual_list and os.path.isfile(actual_list):
                try:
                    extracted = []
                    with open(actual_list, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("file "):
                                p = line[5:].strip().strip("'\"")
                                extracted.append(p)
                    if len(extracted) >= 2:
                        file_paths = extracted
                except Exception:
                    pass

        # Modo MANUAL: omitir N fotogramas al inicio de cada segmento posterior (>= 1)
        if stutter_mode == "manual" and file_paths and len(file_paths) >= 2:
            k = len(file_paths)
            n_drop = max(1, int(drop_start_frames))

            cmd = [ffmpeg_path, "-y"]
            for f in file_paths:
                cmd.extend(["-i", str(f)])
            if has_audio:
                cmd.extend(["-i", audio_target])
                ext_audio_idx = k

            # Filtros de video
            v_parts = ["[0:v]setpts=PTS-STARTPTS[v0]"]
            for i in range(1, k):
                v_parts.append(f"[{i}:v]select=gte(n\\,{n_drop}),setpts=PTS-STARTPTS[v{i}]")
            v_cat = "".join(f"[v{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0[vout]"

            if not has_audio:
                a_parts = ["[0:a]asetpts=PTS-STARTPTS[a0]"]
                for i in range(1, k):
                    a_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
                a_cat = "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[aout]"
                fc = ";".join(v_parts + a_parts + [v_cat, a_cat])
                cmd.extend([
                    "-filter_complex", fc,
                    "-map", "[vout]",
                    "-map", "[aout]"
                ])
            else:
                if audio_mode == "replace":
                    fc = ";".join(v_parts + [v_cat])
                    cmd.extend([
                        "-filter_complex", fc,
                        "-map", "[vout]",
                        "-map", f"{ext_audio_idx}:a:0"
                    ])
                elif audio_mode == "mix":
                    a_parts = ["[0:a]asetpts=PTS-STARTPTS[a0]"]
                    for i in range(1, k):
                        a_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
                    a_cat = "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[acat]"
                    mix_part = f"[acat]volume={vo_str}[a0v];[{ext_audio_idx}:a]volume={va_str}[a1v];[a0v][a1v]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                    fc = ";".join(v_parts + a_parts + [v_cat, a_cat, mix_part])
                    cmd.extend([
                        "-filter_complex", fc,
                        "-map", "[vout]",
                        "-map", "[aout]"
                    ])
                else:  # add_track
                    a_parts = ["[0:a]asetpts=PTS-STARTPTS[a0]"]
                    for i in range(1, k):
                        a_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
                    a_cat = "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[orig_a]"
                    fc = ";".join(v_parts + a_parts + [v_cat, a_cat])
                    cmd.extend([
                        "-filter_complex", fc,
                        "-map", "[vout]",
                        "-map", "[orig_a]",
                        "-map", f"{ext_audio_idx}:a:0"
                    ])

            cmd.extend([
                "-fps_mode", "passthrough",
                "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                "-c:a", "aac", "-b:a", "256k"
            ])
            if has_audio and shortest:
                cmd.append("-shortest")
            cmd.append(output_file)
            return cmd

        # Modo AUTOMÁTICO (mpdecimate con concat demuxer)
        cmd = [
            ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", actual_list
        ]
        if has_audio:
            cmd.extend(["-i", audio_target])

        if not has_audio:
            cmd.extend([
                "-vf", "mpdecimate,setpts=N/FRAME_RATE/TB",
                "-af", "aresample=async=1000",
                "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                "-c:a", "aac", "-b:a", "256k"
            ])
        else:
            if audio_mode == "mix":
                cmd.extend([
                    "-filter_complex", f"[0:v]mpdecimate,setpts=N/FRAME_RATE/TB[vout];[0:a]aresample=async=1000,volume={vo_str}[a0];[1:a]volume={va_str}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "[vout]",
                    "-map", "[aout]",
                    "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "256k"
                ])
            elif audio_mode == "add_track":
                cmd.extend([
                    "-filter_complex", "[0:v]mpdecimate,setpts=N/FRAME_RATE/TB[vout];[0:a]aresample=async=1000[a0]",
                    "-map", "[vout]",
                    "-map", "[a0]",
                    "-map", "1:a:0",
                    "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "256k"
                ])
            else:  # replace
                cmd.extend([
                    "-vf", "mpdecimate,setpts=N/FRAME_RATE/TB",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "256k"
                ])

            if shortest:
                cmd.append("-shortest")

        cmd.append(output_file)
        return cmd

    # Comportamiento estándar sin anti_stutter
    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", actual_list
    ]

    if has_audio:
        cmd.extend(["-i", audio_target])

    if not has_audio:
        if mode == "copy":
            cmd.extend(["-c", "copy"])
        else:
            # Re-encodificación de alta fidelidad si los códecs fueran heterogéneos
            cmd.extend([
                "-c:v", "libx264", "-crf", "17", "-preset", "fast",
                "-c:a", "aac", "-b:a", "256k"
            ])
    else:
        # Modo con audio incorporado
        if mode == "copy":
            v_codec = ["-c:v", "copy"]
        else:
            v_codec = ["-c:v", "libx264", "-crf", "17", "-preset", "fast"]

        if audio_mode == "mix":
            # Mezclar audio original de los segmentos con la nueva pista de audio
            cmd.extend([
                "-filter_complex", f"[0:a]volume={vo_str}[a0];[1:a]volume={va_str}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v:0",
                "-map", "[aout]"
            ])
            cmd.extend(v_codec)
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])
        elif audio_mode == "add_track":
            # Añadir como pista secundaria de audio
            cmd.extend([
                "-map", "0:v:0",
                "-map", "0:a?",
                "-map", "1:a:0"
            ])
            cmd.extend(v_codec)
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])
        else:
            # "replace": Reemplaza audio de los segmentos o añade audio al video unificado
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0"
            ])
            cmd.extend(v_codec)
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])

        if shortest:
            cmd.append("-shortest")

    cmd.append(output_file)
    return cmd


def create_concat_list_file(file_paths: List[str], target_txt_path: str) -> str:
    """
    Genera el archivo de lista requerido por el concat demuxer de FFmpeg.
    Maneja rutas con barras normales / compatibles con Windows y Linux.
    """
    with open(target_txt_path, "w", encoding="utf-8") as f:
        for p in file_paths:
            # Escapar comillas simples y usar formato compatible
            clean_path = str(Path(p).resolve()).replace("\\", "/")
            clean_path = clean_path.replace("'", "'\\''")
            f.write(f"file '{clean_path}'\n")
    return target_txt_path


def build_compare_video_command(
    ffmpeg_path: str,
    video_a: str,
    video_b: str,
    output_file: str,
    mode: str = "split_screen",  # "split_screen", "side_by_side", "diff"
    target_width: int = 1280,
    target_height: int = 720
) -> List[str]:
    """
    Construye el comando FFmpeg para generar un video de comparación visual entre dos videos.
    - 'split_screen': Mitad izquierda video A, mitad derecha video B con línea divisoria central.
    - 'side_by_side': Dos videos en paralelo lado a lado con etiquetas de identificación.
    - 'diff': Mapa de diferencias (los píxeles idénticos se muestran en negro; los modificados en color).
    """
    cmd = [
        ffmpeg_path, "-y",
        "-i", video_a,
        "-i", video_b
    ]

    w = target_width if target_width % 2 == 0 else target_width + 1
    h = target_height if target_height % 2 == 0 else target_height + 1
    w_half = w // 2

    if mode == "side_by_side":
        # Ambos videos lado a lado (cada uno escalado a w_half x h)
        filter_str = (
            f"[0:v]scale={w_half}:{h},drawtext=text='ORIGINAL (A)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[left]; "
            f"[1:v]scale={w_half}:{h},drawtext=text='COMPARADO (B)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[right]; "
            f"[left][right]hstack[vout]"
        )
    elif mode == "diff":
        # Mapa de diferencias
        filter_str = (
            f"[0:v]scale={w}:{h}[v0s]; "
            f"[1:v]scale={w}:{h}[v1s]; "
            f"[v0s][v1s]blend=all_mode=difference[diff]; "
            f"[diff]drawtext=text='MAPA DE DIFERENCIAS (Negro = Idéntico | Color = Pérdida o Cambio)':x=15:y=15:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6[vout]"
        )
    else:
        # "split_screen" (predeterminado)
        filter_str = (
            f"[1:v]scale={w}:{h}[v1s]; "
            f"[0:v]scale={w}:{h},crop={w_half}:{h}:0:0,drawtext=text='ORIGINAL (Izq)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[left]; "
            f"[v1s]crop={w_half}:{h}:{w_half}:0,drawtext=text='COMPARADO (Der)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[right]; "
            f"[left][right]hstack[split]; "
            f"[split]drawbox=x={w_half - 1}:y=0:w=2:h={h}:color=yellow@0.9:t=fill[vout]"
        )

    cmd.extend([
        "-filter_complex", filter_str,
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "17",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_file
    ])
    return cmd


def build_compare_live_stream_command(
    ffmpeg_path: str,
    video_a: str,
    video_b: str,
    mode: str = "split_screen",
    target_width: int = 1280,
    target_height: int = 720
) -> List[str]:
    """
    Construye el comando FFmpeg para emitir en directo (pipe NUT) la comparación
    entre dos videos con decodificación inmediata sin escribir en disco.
    """
    w = target_width if target_width % 2 == 0 else target_width + 1
    h = target_height if target_height % 2 == 0 else target_height + 1
    w_half = w // 2

    if mode == "side_by_side":
        filter_str = (
            f"[0:v]scale={w_half}:{h},drawtext=text='ORIGINAL (A)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[left]; "
            f"[1:v]scale={w_half}:{h},drawtext=text='COMPARADO (B)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[right]; "
            f"[left][right]hstack[vout]"
        )
    elif mode == "diff":
        filter_str = (
            f"[0:v]scale={w}:{h}[v0s]; "
            f"[1:v]scale={w}:{h}[v1s]; "
            f"[v0s][v1s]blend=all_mode=difference[diff]; "
            f"[diff]drawtext=text='MAPA DE DIFERENCIAS (Negro = Idéntico | Color = Pérdida o Cambio)':x=15:y=15:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6[vout]"
        )
    else:
        # split_screen
        filter_str = (
            f"[1:v]scale={w}:{h}[v1s]; "
            f"[0:v]scale={w}:{h},crop={w_half}:{h}:0:0,drawtext=text='ORIGINAL (Izq)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[left]; "
            f"[v1s]crop={w_half}:{h}:{w_half}:0,drawtext=text='COMPARADO (Der)':x=15:y=15:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6[right]; "
            f"[left][right]hstack[split]; "
            f"[split]drawbox=x={w_half - 1}:y=0:w=2:h={h}:color=yellow@0.9:t=fill[vout]"
        )

    return [
        ffmpeg_path, "-y",
        "-i", video_a,
        "-i", video_b,
        "-filter_complex", filter_str,
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:v", "rawvideo",
        "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le",
        "-f", "nut",
        "-"
    ]


def build_ffplay_live_stream_command(
    ffplay_path: str,
    window_title: str = "Comparación Sincronizada en Tiempo Real"
) -> List[str]:
    """Construye el comando ffplay para leer desde stdin (-) el flujo de comparación en vivo."""
    return [
        ffplay_path,
        "-window_title", window_title,
        "-autoexit",
        "-"
    ]


def build_ffplay_dual_window_commands(
    ffplay_path: str,
    video_a: str,
    video_b: str,
    screen_width: int = 1920,
    screen_height: int = 1080,
    screen_x: int = 0,
    screen_y: int = 0
) -> Tuple[List[str], List[str]]:
    """
    Construye dos comandos de ffplay posicionados geométricamente uno al lado del otro
    (mitad izquierda y mitad derecha de la pantalla).
    """
    usable_w = screen_width
    usable_h = screen_height
    win_w = max(320, min(int(usable_w / 2) - 30, 960))
    win_h = max(240, min(int(win_w * 9 / 16), usable_h - 100))

    y_pos = screen_y + max(40, int((usable_h - win_h) / 2))
    x_pos_a = screen_x + 15
    x_pos_b = screen_x + int(usable_w / 2) + 10

    name_a = Path(video_a).name
    name_b = Path(video_b).name

    cmd_a = [
        ffplay_path,
        "-window_title", f"Original (A): {name_a}",
        "-x", str(win_w),
        "-y", str(win_h),
        "-left", str(x_pos_a),
        "-top", str(y_pos),
        "-autoexit",
        video_a
    ]

    cmd_b = [
        ffplay_path,
        "-window_title", f"Comparado (B): {name_b}",
        "-x", str(win_w),
        "-y", str(win_h),
        "-left", str(x_pos_b),
        "-top", str(y_pos),
        "-autoexit",
        video_b
    ]

    return cmd_a, cmd_b


def build_compare_metrics_command(
    ffmpeg_path: str,
    video_a: str,
    video_b: str,
    target_width: int = 1280,
    target_height: int = 720
) -> List[str]:
    """
    Construye el comando FFmpeg para calcular métricas objetivas de calidad (SSIM y PSNR)
    entre el video original (referencia A) y el video procesado (B).
    """
    w = target_width if target_width % 2 == 0 else target_width + 1
    h = target_height if target_height % 2 == 0 else target_height + 1

    filter_graph = (
        f"[0:v]scale={w}:{h},split=2[v0_s][v0_p];"
        f"[1:v]scale={w}:{h},split=2[v1_s][v1_p];"
        f"[v0_s][v1_s]ssim[sout];"
        f"[v0_p][v1_p]psnr[pout]"
    )

    return [
        ffmpeg_path, "-y",
        "-i", video_b,
        "-i", video_a,
        "-filter_complex", filter_graph,
        "-map", "[sout]", "-f", "null", "-",
        "-map", "[pout]", "-f", "null", "-"
    ]


def parse_comparison_metrics(stderr_text) -> Dict[str, Any]:
    """
    Analiza la salida de FFmpeg para extraer los valores de SSIM y PSNR.
    Devuelve puntuaciones cuantitativas y veredicto cualitativo con código de color.
    """
    if isinstance(stderr_text, (list, tuple)):
        stderr_text = "\n".join(str(l) for l in stderr_text)
    elif not isinstance(stderr_text, str):
        stderr_text = str(stderr_text or "")

    res = {
        "ssim": None,
        "psnr": None,
        "ssim_str": "N/D",
        "psnr_str": "N/D",
        "rating": "No se pudieron calcular métricas",
        "rating_color": "#94a3b8",
        "detail": ""
    }

    # SSIM All:0.984210
    ssim_match = re.search(r'SSIM\s+.*?All:([0-9.]+|inf)', stderr_text, re.IGNORECASE)
    if ssim_match:
        try:
            raw = ssim_match.group(1).lower()
            if raw == "inf":
                res["ssim"] = 1.0
                res["ssim_str"] = "1.0000 (Exacto)"
            else:
                val = float(raw)
                res["ssim"] = val
                res["ssim_str"] = f"{val:.4f}"
        except Exception:
            pass

    # PSNR average:42.510000
    psnr_match = re.search(r'PSNR\s+.*?average:([0-9.]+|inf)', stderr_text, re.IGNORECASE)
    if psnr_match:
        try:
            raw = psnr_match.group(1).lower()
            if raw == "inf":
                res["psnr"] = 999.0
                res["psnr_str"] = "∞ dB (Sin pérdida)"
            else:
                val = float(raw)
                res["psnr"] = val
                res["psnr_str"] = f"{val:.2f} dB"
        except Exception:
            pass

    ssim_val = res["ssim"]
    psnr_val = res["psnr"]

    if ssim_val is not None:
        if ssim_val >= 0.98 or (psnr_val and psnr_val >= 42.0):
            res["rating"] = "Excelente (Fidelidad visual indistinguible del original)"
            res["rating_color"] = "#10b981"
            res["detail"] = "La compresión conserva prácticamente el 100% de la textura y detalle del video original."
        elif ssim_val >= 0.95 or (psnr_val and psnr_val >= 37.0):
            res["rating"] = "Muy Buena (Fidelidad visual alta)"
            res["rating_color"] = "#38bdf8"
            res["detail"] = "Diferencias casi imperceptibles a distancia de reproducción normal."
        elif ssim_val >= 0.90 or (psnr_val and psnr_val >= 32.0):
            res["rating"] = "Aceptable / Buena (Pérdida moderada)"
            res["rating_color"] = "#f59e0b"
            res["detail"] = "Pérdida perceptible en escenas de movimiento rápido o gradientes sutiles."
        else:
            res["rating"] = "Pérdida Notoria de Calidad"
            res["rating_color"] = "#ef4444"
            res["detail"] = "Artefactos de compresión o reducción evidente de resolución y nitidez."
    elif psnr_val is not None:
        if psnr_val >= 40.0:
            res["rating"] = "Excelente Fidelidad (PSNR > 40 dB)"
            res["rating_color"] = "#10b981"
        elif psnr_val >= 32.0:
            res["rating"] = "Buena Fidelidad (PSNR > 32 dB)"
            res["rating_color"] = "#38bdf8"
        else:
            res["rating"] = "Calidad Reducida"
            res["rating_color"] = "#ef4444"

    return res


def build_voice_isolation_command(
    ffmpeg_path: str,
    input_file: str,
    output_file: str,
    profile: str = "moderate",  # "light", "moderate", "aggressive", "studio"
    normalize_speech: bool = True,
    remove_silence: bool = False,
    audio_format: str = "wav_16",  # "wav_16", "wav_24", "mp3_320k", "flac"
    sample_rate: int = 0,
    channels: int = 0
) -> List[str]:
    """
    Construye el comando FFmpeg para aislar y limpiar voces de un video o audio
    utilizando filtros de banda vocal, reducción de ruido espectral y normalización de habla.
    """
    cmd = [ffmpeg_path, "-y", "-i", input_file, "-vn"]

    # Construir cadena de filtros de audio
    filters = []

    # Paso de banda vocal para eliminar retumbes graves (<80Hz) y siseos agudos (>11-12kHz)
    if profile == "light":
        filters.append("highpass=f=80,lowpass=f=12000")
        filters.append("afftdn=nf=-20:tn=1")
    elif profile == "aggressive":
        filters.append("highpass=f=95,lowpass=f=10000")
        filters.append("afftdn=nf=-34:tn=1")
    elif profile == "studio":
        filters.append("highpass=f=80,lowpass=f=12000")
        filters.append("afftdn=nf=-22:tn=1")
        filters.append("speechnorm=e=4:r=0.0001:l=1")
    else:  # "moderate"
        filters.append("highpass=f=85,lowpass=f=11000")
        filters.append("afftdn=nf=-26:tn=1")

    # Normalización de voz si no está ya en el perfil
    if normalize_speech and profile != "studio":
        filters.append("speechnorm=e=4:r=0.0001:l=1")

    # Eliminación opcional de pausas y silencios
    if remove_silence:
        filters.append("silenceremove=start_periods=1:start_duration=0.3:start_threshold=-38dB:stop_periods=-1:stop_duration=0.5:stop_threshold=-38dB")

    if filters:
        cmd.extend(["-af", ",".join(filters)])

    # Frecuencia de muestreo
    if sample_rate > 0:
        cmd.extend(["-ar", str(sample_rate)])

    # Canales de audio
    if channels == 1:
        cmd.extend(["-ac", "1"])
    elif channels == 2:
        cmd.extend(["-ac", "2"])

    # Parámetros de codificador de salida
    if audio_format == "wav_16":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif audio_format == "wav_24":
        cmd.extend(["-c:a", "pcm_s24le"])
    elif audio_format == "mp3_320k":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
    elif audio_format == "flac":
        cmd.extend(["-c:a", "flac"])
    else:
        cmd.extend(["-c:a", "pcm_s16le"])

    cmd.append(output_file)
    return cmd


def build_extract_mono_wav_command(
    ffmpeg_path: str,
    input_file: str,
    output_wav: str,
    sample_rate: int = 16000
) -> List[str]:
    """
    Extrae una pista de audio PCM mono a 16 kHz optimizada para análisis acústico y diarización.
    """
    return [
        ffmpeg_path, "-y",
        "-i", input_file,
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        output_wav
    ]


def build_silence_detect_command(
    ffmpeg_path: str,
    input_file: str,
    noise_db: float = -30.0,
    min_duration: float = 0.4
) -> List[str]:
    """
    Construye el comando para detectar marcas de silencio y voz en el audio mediante silencedetect.
    """
    filter_str = f"silencedetect=noise={noise_db}dB:d={min_duration}"
    return [
        ffmpeg_path, "-y",
        "-i", input_file,
        "-vn",
        "-af", filter_str,
        "-f", "null", "-"
    ]


def parse_silence_detect_output(
    stderr_text: str,
    total_duration: float = 0.0,
    min_speech_sec: float = 0.35,
    pad_start_sec: float = 0.0,
    pad_end_sec: float = 0.0
) -> List[Tuple[float, float]]:
    """
    Analiza la salida de silencedetect e invierte los silencios para obtener
    los intervalos exactos de habla humana [(inicio, fin), ...].
    """
    if isinstance(stderr_text, (list, tuple)):
        stderr_text = "\n".join(str(l) for l in stderr_text)
    elif not isinstance(stderr_text, str):
        stderr_text = str(stderr_text or "")

    silence_starts = []
    silence_ends = []

    for line in stderr_text.splitlines():
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m:
                try:
                    silence_starts.append(float(m.group(1)))
                except Exception:
                    pass
        elif "silence_end:" in line:
            m = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m:
                try:
                    silence_ends.append(float(m.group(1)))
                except Exception:
                    pass

    # Si se pasó total_duration = 0, intentar deducirla del log
    if total_duration <= 0.0:
        dur_match = re.search(r"Duration:\s*(\d{2}:\d{2}:\d{2}\.\d+)", stderr_text)
        if dur_match:
            try:
                parts = dur_match.group(1).split(":")
                total_duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except Exception:
                pass

    if total_duration <= 0.0 and silence_ends:
        total_duration = max(silence_ends) + 1.0

    # Parear silencios
    silence_intervals = []
    num_starts = len(silence_starts)
    num_ends = len(silence_ends)
    max_pairs = min(num_starts, num_ends)

    for i in range(max_pairs):
        s = silence_starts[i]
        e = silence_ends[i]
        if e > s:
            silence_intervals.append((s, e))

    # Si quedó un silence_start huérfano al final del audio
    if num_starts > num_ends and total_duration > silence_starts[-1]:
        silence_intervals.append((silence_starts[-1], total_duration))

    # Invertir los silencios para obtener los tramos de voz
    speech_segments = []
    current_time = 0.0

    for s_start, s_end in silence_intervals:
        if s_start > current_time:
            seg_len = s_start - current_time
            if seg_len >= min_speech_sec:
                seg_st = max(0.0, current_time - pad_start_sec)
                seg_en = s_start + pad_end_sec
                if s_end > s_start:
                    seg_en = min(seg_en, s_start + (s_end - s_start) * 0.75, s_end)
                if total_duration > 0.0:
                    seg_en = min(total_duration, seg_en)
                speech_segments.append((round(seg_st, 3), round(seg_en, 3)))
        current_time = max(current_time, s_end)

    if total_duration > current_time:
        rem_len = total_duration - current_time
        if rem_len >= min_speech_sec:
            seg_st = max(0.0, current_time - pad_start_sec)
            speech_segments.append((round(seg_st, 3), round(total_duration, 3)))

    return speech_segments


def build_stitch_segments_command(
    ffmpeg_path: str,
    input_file: str,
    segments: List[Tuple[float, float]],
    output_file: str,
    apply_cleanup: bool = True,
    audio_format: str = "wav_16"
) -> List[str]:
    """
    Construye un comando FFmpeg para unir una lista de intervalos de tiempo [(inicio, fin), ...]
    en una única pista de audio continua y sin pérdidas, aplicando opcionalmente limpieza vocal.
    """
    if not segments:
        raise ValueError("Se requiere al menos un segmento de tiempo para ensamblar.")

    cmd = [ffmpeg_path, "-y", "-i", input_file, "-vn"]

    # Caso 1: Un solo segmento continuo
    if len(segments) == 1:
        st, en = segments[0]
        cmd.extend(["-ss", f"{st:.3f}", "-to", f"{en:.3f}"])
        if apply_cleanup:
            cmd.extend(["-af", "highpass=f=80,lowpass=f=12000,afftdn=nr=12:nf=-45:tn=1,speechnorm=e=4:r=0.0001:l=1"])
    else:
        # Caso 2: Múltiples segmentos unidos mediante atrim y concat
        v_parts = []
        for i, (st, en) in enumerate(segments):
            v_parts.append(f"[0:a]atrim=start={st:.3f}:end={en:.3f},asetpts=PTS-STARTPTS[a{i}]")

        n_inputs = len(segments)
        cat_inputs = "".join(f"[a{i}]" for i in range(n_inputs))

        if apply_cleanup:
            concat_filter = (
                ";".join(v_parts) +
                f";{cat_inputs}concat=n={n_inputs}:v=0:a=1[araw];"
                "[araw]highpass=f=80,lowpass=f=12000,afftdn=nr=12:nf=-45:tn=1,speechnorm=e=4:r=0.0001:l=1[aout]"
            )
        else:
            concat_filter = ";".join(v_parts) + f";{cat_inputs}concat=n={n_inputs}:v=0:a=1[aout]"

        cmd.extend(["-filter_complex", concat_filter, "-map", "[aout]"])

    if audio_format == "wav_16":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif audio_format == "wav_24":
        cmd.extend(["-c:a", "pcm_s24le"])
    elif audio_format == "mp3_320k":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
    elif audio_format == "flac":
        cmd.extend(["-c:a", "flac"])
    else:
        cmd.extend(["-c:a", "pcm_s16le"])

    cmd.append(output_file)
    return cmd
