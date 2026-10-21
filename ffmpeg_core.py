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


def build_create_video_command(
    ffmpeg_path: str,
    input_pattern: str,
    output_file: str,
    fps: float = 30.0,
    codec_preset: str = "h264_lossless",  # "h264_lossless", "h264_visually_lossless", "prores", "vp9_lossless"
    audio_file: Optional[str] = None
) -> List[str]:
    """
    Construye el comando para ensamblar un video a partir de fotogramas secuenciales.
    """
    cmd = [ffmpeg_path, "-y", "-framerate", str(fps), "-i", input_pattern]

    if audio_file and os.path.isfile(audio_file):
        cmd.extend(["-i", audio_file])

    if codec_preset == "h264_lossless":
        # H.264 CRF 0 es matemáticamente sin pérdida
        # yuv420p permite reproducirlo en reproductores habituales sin distorsión visible
        cmd.extend(["-c:v", "libx264", "-crf", "0", "-preset", "slow", "-pix_fmt", "yuv420p"])
    elif codec_preset == "h264_visually_lossless":
        # CRF 17 es imperceptiblemente idéntico a la fuente original y altamente compatible
        cmd.extend(["-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p"])
    elif codec_preset == "prores":
        # Apple ProRes 422 HQ (estándar de edición profesional sin pérdida perceptual)
        cmd.extend(["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"])
    elif codec_preset == "vp9_lossless":
        # WebM / VP9 Lossless
        cmd.extend(["-c:v", "libvpx-vp9", "-lossless", "1", "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"])

    if audio_file and os.path.isfile(audio_file):
        cmd.extend(["-c:a", "copy", "-shortest"])

    cmd.append(output_file)
    return cmd


def build_segment_command(
    ffmpeg_path: str,
    input_file: str,
    output_pattern: str,
    segment_duration_sec: int = 15,
    mode: str = "copy"  # "copy" (sin recodificar, ultra rápido) o "exact" (fuerza keyframes para corte exacto con CRF 17)
) -> List[str]:
    """
    Construye el comando para dividir un video en segmentos de duración configurable.
    - 'copy': Modo directo sin pérdida de calidad (-c copy) cortando en keyframes.
    - 'exact': Fuerza keyframe en cada múltiplo de segmento para longitud exacta sin pérdida visual.
    """
    cmd = [ffmpeg_path, "-y", "-i", input_file]

    if mode == "copy":
        # Copia directa sin pérdida de video ni audio
        cmd.extend([
            "-c", "copy",
            "-map", "0",
            "-f", "segment",
            "-segment_time", str(segment_duration_sec),
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
            "-reset_timestamps", "1"
        ])

    cmd.append(output_pattern)
    return cmd


def build_concat_command(
    ffmpeg_path: str,
    list_file_path: str = None,
    output_file: str = "",
    mode: str = "copy",  # "copy" (demuxer concat sin recodificar) o "reencode" (si provienen de formatos distintos)
    concat_list_file: str = None
) -> List[str]:
    """
    Construye el comando para unir segmentos.
    - 'copy': Modo demuxer concat sin pérdida y sin recodificación.
    """
    actual_list = list_file_path or concat_list_file or ""
    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", actual_list
    ]

    if mode == "copy":
        cmd.extend(["-c", "copy"])
    else:
        # Re-encodificación de alta fidelidad si los códecs fueran heterogéneos
        cmd.extend([
            "-c:v", "libx264", "-crf", "17", "-preset", "fast",
            "-c:a", "aac", "-b:a", "256k"
        ])

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
