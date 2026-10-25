#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diarization Core Module
Motor acústico y de diarización de interlocutores basado en VAD, MFCC y agrupamiento tímbrico.
No requiere dependencias pesadas ni cuentas externas; opera mediante Scipy/NumPy y FFmpeg.
"""

import os
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import scipy.signal
import scipy.fft
import scipy.io.wavfile as wavfile
import scipy.cluster.vq as vq


def compute_acoustic_features(sig: np.ndarray, sr: int = 16000, n_mfcc: int = 13) -> np.ndarray:
    """
    Calcula la huella acústica (timbre vocal) de un fragmento de audio:
    - 13 Coeficientes Cepstrales en Escala Mel (MFCCs: media y desviación típica = 26 dimensiones)
    - Estimación de Tono Fundamental F0 / Pitch (media y estabilidad)
    - Centroide Espectral (brillo de la voz)
    """
    if len(sig) < int(sr * 0.08):
        return np.zeros(n_mfcc * 2 + 3, dtype=np.float32)

    # 1. Pre-énfasis para equilibrar el espectro de frecuencias altas
    emphasized = np.append(sig[0], sig[1:] - 0.97 * sig[:-1])

    # 2. Ventaneo (ventanas de 25ms con solapamiento de 10ms)
    frame_len = int(0.025 * sr)
    frame_step = int(0.010 * sr)
    num_frames = max(1, int(np.ceil(float(np.abs(len(emphasized) - frame_len)) / frame_step)))
    pad_len = num_frames * frame_step + frame_len
    pad_sig = np.append(emphasized, np.zeros(max(0, pad_len - len(emphasized))))

    indices = np.tile(np.arange(0, frame_len), (num_frames, 1)) + np.tile(
        np.arange(0, num_frames * frame_step, frame_step), (frame_len, 1)
    ).T
    frames = pad_sig[indices.astype(np.int32, copy=False)]
    frames = frames * np.hamming(frame_len)

    # 3. FFT y Espectro de Potencia
    nfft = 512
    mag_frames = np.absolute(np.fft.rfft(frames, nfft))
    pow_frames = (1.0 / nfft) * (mag_frames ** 2)

    # 4. Banco de Filtros Mel (26 filtros distribuidos de 0 a sr/2)
    low_freq_mel = 0
    high_freq_mel = 2595.0 * np.log10(1.0 + (sr / 2.0) / 700.0)
    nfilt = 26
    mel_points = np.linspace(low_freq_mel, high_freq_mel, nfilt + 2)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bins = np.floor((nfft + 1) * hz_points / sr).astype(int)

    fbank = np.zeros((nfilt, int(np.floor(nfft / 2 + 1))))
    for m in range(1, nfilt + 1):
        f_m_minus = bins[m - 1]
        f_m = bins[m]
        f_m_plus = bins[m + 1]
        for k in range(f_m_minus, f_m):
            fbank[m - 1, k] = (k - bins[m - 1]) / max(1, (bins[m] - bins[m - 1]))
        for k in range(f_m, f_m_plus):
            fbank[m - 1, k] = (bins[m + 1] - k) / max(1, (bins[m + 1] - bins[m]))

    filter_banks = np.dot(pow_frames, fbank.T)
    filter_banks = np.where(filter_banks <= 0, np.finfo(float).eps, filter_banks)
    filter_banks = 20.0 * np.log10(filter_banks)

    # 5. Transformada Discreta del Coseno (DCT) para extraer MFCCs
    mfcc = scipy.fft.dct(filter_banks, type=2, axis=1, norm='ortho')[:, 1 : (n_mfcc + 1)]
    mfcc_mean = np.mean(mfcc, axis=0)
    mfcc_std = np.std(mfcc, axis=0)

    # 6. Estimación de Pitch (Frecuencia Fundamental F0 por autocorrelación)
    pitch_val = estimate_fundamental_pitch(sig, sr)

    # 7. Centroide Espectral
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    spectral_centroid = np.sum(freqs * np.mean(mag_frames, axis=0)) / max(1e-6, np.sum(np.mean(mag_frames, axis=0)))

    # Combinar en vector único de características acústicas
    features = np.concatenate([
        mfcc_mean,
        mfcc_std,
        [pitch_val / 400.0, spectral_centroid / 4000.0, np.log10(max(1e-5, np.var(sig)))]
    ])
    return features.astype(np.float32)


def estimate_fundamental_pitch(sig: np.ndarray, sr: int = 16000) -> float:
    """
    Estima el tono medio F0 (Pitch) de la voz mediante autocorrelación en el rango humano (75Hz a 380Hz).
    """
    if len(sig) < int(sr * 0.05):
        return 0.0
    min_lag = int(sr / 380)
    max_lag = int(sr / 75)
    chunk = sig[:min(len(sig), sr * 2)]  # Tomar máximo 2 segundos para rapidez
    corr = scipy.signal.correlate(chunk, chunk, mode='full')[len(chunk) - 1:]
    if max_lag > len(corr):
        max_lag = len(corr) - 1
    if min_lag >= max_lag:
        return 0.0
    peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
    if peak_lag > 0:
        return float(sr / peak_lag)
    return 0.0


def select_best_sample_segments(
    segments: List[Tuple[float, float]],
    target_duration: float = 30.0
) -> List[Tuple[float, float]]:
    """
    Selecciona de forma inteligente los mejores segmentos continuos de habla
    de un interlocutor hasta alcanzar la duración objetivo solicitada (ej. 15s, 30s o 60s).
    Prioriza segmentos estables (> 1.2 seg) sin fragmentaciones bruscas.
    """
    if not segments:
        return []

    # Ordenar segmentos por longitud descendente para preferir frases completas
    sorted_segs = sorted(segments, key=lambda s: (s[1] - s[0]), reverse=True)

    accumulated = 0.0
    chosen = []

    for seg in sorted_segs:
        dur = seg[1] - seg[0]
        if dur >= 0.8:
            chosen.append(seg)
            accumulated += dur
            if accumulated >= target_duration:
                break

    # Si aún no alcanza, agregar fragmentos más breves
    if accumulated < target_duration:
        for seg in segments:
            if seg not in chosen:
                chosen.append(seg)
                accumulated += (seg[1] - seg[0])
                if accumulated >= target_duration:
                    break

    # Reordenar cronológicamente
    chosen.sort(key=lambda s: s[0])
    return chosen


def perform_speaker_diarization(
    audio_wav_path: str,
    speech_segments: List[Tuple[float, float]],
    num_speakers: Optional[int] = None,
    max_speakers: int = 4
) -> Dict[str, Any]:
    """
    Ejecuta el agrupamiento por timbre vocal en los segmentos de habla detectados.
    Devuelve los interlocutores encontrados, sus estadísticas y sus muestras optimizadas.
    """
    result = {
        "total_speech_duration": 0.0,
        "num_speakers": 0,
        "speakers": []
    }

    if not os.path.isfile(audio_wav_path) or not speech_segments:
        return result

    # 1. Leer archivo WAV de análisis
    sr, raw_data = wavfile.read(audio_wav_path)
    if raw_data.ndim > 1:
        raw_data = raw_data.mean(axis=1)

    if raw_data.dtype == np.int16:
        audio_data = raw_data.astype(np.float32) / 32768.0
    elif raw_data.dtype == np.int32:
        audio_data = raw_data.astype(np.float32) / 2147483648.0
    else:
        audio_data = raw_data.astype(np.float32)

    total_speech_dur = sum((en - st) for st, en in speech_segments)
    result["total_speech_duration"] = round(total_speech_dur, 2)

    # 2. Extraer características acústicas de cada segmento
    feature_matrix = []
    valid_segments = []

    for st, en in speech_segments:
        start_idx = int(st * sr)
        end_idx = int(en * sr)
        if end_idx > start_idx + int(sr * 0.15) and start_idx < len(audio_data):
            seg_sig = audio_data[start_idx:min(len(audio_data), end_idx)]
            feat = compute_acoustic_features(seg_sig, sr)
            feature_matrix.append(feat)
            valid_segments.append((st, en))

    if not feature_matrix:
        return result

    features = np.array(feature_matrix, dtype=np.float32)

    # Normalización Z-score de características
    mean = np.mean(features, axis=0)
    std = np.std(features, axis=0)
    std = np.where(std == 0, 1.0, std)
    norm_features = (features - mean) / std

    n_samples = len(valid_segments)

    # 3. Determinar número de interlocutores
    if num_speakers is not None and num_speakers >= 1:
        k = min(num_speakers, n_samples)
    else:
        # Autodetección: evaluar distorsión k-means entre 1 y min(max_speakers, n_samples)
        best_k = 1
        best_score = float("inf")
        max_k_test = min(max_speakers, n_samples)

        if max_k_test >= 2 and n_samples >= 3:
            for cand_k in range(2, max_k_test + 1):
                try:
                    centroids, labels = vq.kmeans2(norm_features, cand_k, minit='points', iter=15)
                    # Calcular inercia intra-cluster
                    diffs = norm_features - centroids[labels]
                    distortion = np.mean(np.sum(diffs ** 2, axis=1))
                    # Penalización de complejidad (criterio BIC simplificado)
                    score = distortion + (cand_k * 0.45)
                    if score < best_score:
                        best_score = score
                        best_k = cand_k
                except Exception:
                    pass
        k = best_k

    # 4. Agrupamiento final
    if k <= 1 or n_samples < 2:
        labels = np.zeros(n_samples, dtype=int)
        k = 1
    else:
        try:
            _, labels = vq.kmeans2(norm_features, k, minit='points', iter=25)
        except Exception:
            labels = np.zeros(n_samples, dtype=int)
            k = 1

    # 5. Agrupar segmentos por interlocutor
    speaker_dict = {i: [] for i in range(k)}
    for idx, (st, en) in enumerate(valid_segments):
        lbl = int(labels[idx])
        speaker_dict[lbl].append((st, en))

    # Ordenar interlocutores por tiempo total de habla (el que más habla será Hablante 1)
    sorted_speakers = sorted(
        speaker_dict.items(),
        key=lambda item: sum((s[1] - s[0]) for s in item[1]),
        reverse=True
    )

    speakers_list = []
    for spk_idx, (orig_id, segs) in enumerate(sorted_speakers, 1):
        if not segs:
            continue
        tot_dur = sum((s[1] - s[0]) for s in segs)
        sample_15 = select_best_sample_segments(segs, 15.0)
        sample_30 = select_best_sample_segments(segs, 30.0)
        sample_60 = select_best_sample_segments(segs, 60.0)

        speakers_list.append({
            "id": spk_idx,
            "name": f"Hablante {spk_idx}",
            "segment_count": len(segs),
            "total_duration": round(tot_dur, 2),
            "total_duration_fmt": format_seconds_to_time(tot_dur),
            "segments": segs,
            "sample_15": sample_15,
            "sample_30": sample_30,
            "sample_60": sample_60
        })

    result["num_speakers"] = len(speakers_list)
    result["speakers"] = speakers_list
    return result


def format_seconds_to_time(seconds: float) -> str:
    """Convierte segundos a formato MM:SS o HH:MM:SS."""
    if seconds < 0:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
