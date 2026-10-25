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
import scipy.cluster.hierarchy as sch


def compute_acoustic_features(sig: np.ndarray, sr: int = 16000, n_mfcc: int = 13) -> np.ndarray:
    """
    Calcula la huella acústica (timbre vocal) de un fragmento de audio:
    - 13 Coeficientes Cepstrales en Escala Mel (MFCCs sobre cuadros activos de voz)
    - Estimación de Tono Fundamental F0 / Pitch (autocorrelación normalizada en cuadros sonoros)
    - Centroide Espectral (brillo tímbrico de la voz)
    - Varianza energética
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

    # Filtrar cuadros con energía activa para evitar que el silencio o ruido de fondo contamine el timbre
    frame_energies = np.sum(frames ** 2, axis=1)
    max_energy = np.max(frame_energies) if len(frame_energies) > 0 else 0.0
    active_mask = (frame_energies >= (max_energy * 0.08)) if max_energy > 1e-5 else np.ones(len(frames), dtype=bool)
    if not np.any(active_mask):
        active_mask = np.ones(len(frames), dtype=bool)

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
    mfcc_active = mfcc[active_mask]
    if len(mfcc_active) > 0:
        mfcc_mean = np.mean(mfcc_active, axis=0)
        mfcc_std = np.std(mfcc_active, axis=0)
    else:
        mfcc_mean = np.mean(mfcc, axis=0)
        mfcc_std = np.std(mfcc, axis=0)

    # 6. Estimación de Pitch (Frecuencia Fundamental F0 por autocorrelación de cuadros sonoros)
    pitch_val = estimate_fundamental_pitch(sig, sr)

    # 7. Centroide Espectral (brillo de la voz en cuadros activos)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    mag_active = mag_frames[active_mask]
    if len(mag_active) > 0:
        spectral_centroid = np.sum(freqs * np.mean(mag_active, axis=0)) / max(1e-6, np.sum(np.mean(mag_active, axis=0)))
    else:
        spectral_centroid = np.sum(freqs * np.mean(mag_frames, axis=0)) / max(1e-6, np.sum(np.mean(mag_frames, axis=0)))

    # Combinar en vector único de características acústicas (29 dimensiones)
    features = np.concatenate([
        mfcc_mean,
        mfcc_std,
        [pitch_val / 400.0, spectral_centroid / 4000.0, np.log10(max(1e-5, np.var(sig)))]
    ])
    return features.astype(np.float32)


def estimate_fundamental_pitch(sig: np.ndarray, sr: int = 16000) -> float:
    """
    Estima el tono medio F0 (Pitch) evaluando cuadros sonoros mediante autocorrelación normalizada
    en el rango vocal humano (75Hz a 380Hz). Descarta cuadros sordos para evitar valores espurios.
    """
    if len(sig) < int(sr * 0.05):
        return 0.0

    frame_len = int(0.030 * sr)  # 30ms
    frame_step = int(0.015 * sr) # 15ms
    min_lag = int(sr / 380)
    max_lag = int(sr / 75)
    num_frames = max(1, int(np.ceil(float(len(sig) - frame_len) / frame_step)))
    f0_voiced = []

    for i in range(num_frames):
        st = i * frame_step
        en = min(len(sig), st + frame_len)
        frame = sig[st:en]
        if len(frame) < frame_len:
            frame = np.pad(frame, (0, frame_len - len(frame)))
        energy = np.sum(frame ** 2)
        if energy < 1e-4:
            continue
        corr = np.correlate(frame, frame, mode='full')[len(frame) - 1:]
        if corr[0] > 1e-5 and max_lag < len(corr):
            norm_corr = corr / corr[0]
            peak_idx = min_lag + np.argmax(norm_corr[min_lag:max_lag])
            if norm_corr[peak_idx] > 0.28:
                f0_voiced.append(sr / peak_idx)

    if f0_voiced:
        return float(np.median(f0_voiced))

    # Respaldo por correlación de trozo entero
    chunk = sig[:min(len(sig), sr * 2)]
    corr = scipy.signal.correlate(chunk, chunk, mode='full')[len(chunk) - 1:]
    if max_lag < len(corr) and min_lag < max_lag and corr[0] > 1e-5:
        norm_corr = corr / corr[0]
        peak_lag = min_lag + np.argmax(norm_corr[min_lag:max_lag])
        if norm_corr[peak_lag] > 0.25:
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


def subdivide_speech_segments(
    segments: List[Tuple[float, float]],
    chunk_sec: float = 1.2,
    min_chunk_sec: float = 0.5
) -> List[Tuple[float, float]]:
    """
    Subdivide intervalos de habla continuos en ventanas uniformes de longitud óptima (~1.2s)
    para permitir el análisis acústico por fragmentos y evitar que tramos largos
    sean tratados como una única muestra indivisible.
    """
    subdivided = []
    for st, en in segments:
        dur = en - st
        if dur <= chunk_sec + (min_chunk_sec / 2.0):
            if dur >= min_chunk_sec:
                subdivided.append((round(st, 3), round(en, 3)))
            elif subdivided:
                prev_st, _ = subdivided[-1]
                subdivided[-1] = (prev_st, round(en, 3))
            else:
                subdivided.append((round(st, 3), round(en, 3)))
            continue

        curr = st
        while curr < en:
            nxt = curr + chunk_sec
            if en - nxt < min_chunk_sec:
                subdivided.append((round(curr, 3), round(en, 3)))
                break
            else:
                subdivided.append((round(curr, 3), round(nxt, 3)))
                curr = nxt
    return subdivided


def merge_contiguous_segments(
    chunks: List[Tuple[float, float]],
    labels: np.ndarray,
    max_gap: float = 0.35
) -> Dict[int, List[Tuple[float, float]]]:
    """
    Agrupa los fragmentos acústicos etiquetados por interlocutor y fusiona
    aquellos consecutivos o con pausas mínimas (< max_gap) para reconstruir
    las intervenciones naturales continuas de cada persona.
    """
    speaker_segs: Dict[int, List[Tuple[float, float]]] = {}
    for idx, (st, en) in enumerate(chunks):
        lbl = int(labels[idx])
        if lbl not in speaker_segs:
            speaker_segs[lbl] = []
        curr_list = speaker_segs[lbl]
        if curr_list:
            last_st, last_en = curr_list[-1]
            if st - last_en <= max_gap:
                curr_list[-1] = (last_st, round(max(last_en, en), 3))
                continue
        curr_list.append((round(st, 3), round(en, 3)))
    return speaker_segs


def get_silhouette_score(X: np.ndarray, labels: np.ndarray, k: int) -> float:
    """Calcula el coeficiente Silhouette medio para evaluar la separación de los clusters."""
    N = len(X)
    if N <= k or k < 2:
        return -1.0
    sil_scores = []
    for i in range(N):
        same_idx = np.where(labels == labels[i])[0]
        if len(same_idx) <= 1:
            a = 0.0
        else:
            diffs = X[same_idx] - X[i]
            a = float(np.mean(np.sqrt(np.sum(diffs ** 2, axis=1))))

        b = float("inf")
        for c in range(k):
            if c == labels[i]:
                continue
            other_idx = np.where(labels == c)[0]
            if len(other_idx) == 0:
                continue
            diffs = X[other_idx] - X[i]
            mean_dist = float(np.mean(np.sqrt(np.sum(diffs ** 2, axis=1))))
            if mean_dist < b:
                b = mean_dist

        if max(a, b) > 1e-6:
            sil_scores.append((b - a) / max(a, b))
        else:
            sil_scores.append(0.0)
    return float(np.mean(sil_scores)) if sil_scores else 0.0


def perform_speaker_diarization(
    audio_wav_path: str,
    speech_segments: List[Tuple[float, float]],
    num_speakers: Optional[int] = None,
    max_speakers: int = 4
) -> Dict[str, Any]:
    """
    Ejecuta el agrupamiento por timbre vocal en los segmentos de habla detectados.
    Aplica sub-segmentación en ventanas acústicas de 1.2s, ponderación biométrica (F0 Pitch + MFCCs),
    normalización L2 direccional, agrupamiento jerárquico Ward con refinamiento de centroides
    y fusión contigua de intervenciones.
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

    # 2. Sub-segmentar en ventanas acústicas de 1.2s para alta resolución temporal
    eval_chunks = subdivide_speech_segments(speech_segments, chunk_sec=1.2, min_chunk_sec=0.5)

    feature_matrix = []
    valid_chunks = []

    for st, en in eval_chunks:
        start_idx = int(st * sr)
        end_idx = int(en * sr)
        if end_idx > start_idx + int(sr * 0.15) and start_idx < len(audio_data):
            seg_sig = audio_data[start_idx:min(len(audio_data), end_idx)]
            feat = compute_acoustic_features(seg_sig, sr)
            feature_matrix.append(feat)
            valid_chunks.append((st, en))

    if not feature_matrix:
        return result

    features = np.array(feature_matrix, dtype=np.float32)

    # Normalización Z-score de características
    mean = np.mean(features, axis=0)
    std = np.std(features, axis=0)
    std = np.where(std == 0, 1.0, std)
    norm_features = (features - mean) / std

    # Ponderación acústica: potenciar discriminadores biométricos (F0 Pitch y formantes MFCC)
    weights = np.ones(norm_features.shape[1], dtype=np.float32)
    weights[0:6] = 1.6     # MFCCs inferiores (formantes / tracto vocal)
    weights[6:13] = 1.0    # MFCCs superiores
    weights[13:26] = 0.5   # Variabilidad MFCC
    if len(weights) > 26:
        weights[26] = 3.2  # Tono fundamental F0 / Pitch (clave para separar timbres)
    if len(weights) > 27:
        weights[27] = 1.4  # Centroide espectral (brillo de la voz)

    weighted_features = norm_features * weights

    # Normalización L2 por fila para desacoplar fluctuaciones de volumen / intensidad vocal
    row_norms = np.linalg.norm(weighted_features, axis=1, keepdims=True)
    row_norms = np.where(row_norms == 0, 1.0, row_norms)
    l2_features = weighted_features / row_norms
    n_samples = len(valid_chunks)

    # 3. Agrupamiento Jerárquico Aglomerativo (Ward HAC sobre vectores de timbre direccional)
    if n_samples <= 1:
        k = 1
        labels = np.zeros(n_samples, dtype=int)
    elif num_speakers is not None and num_speakers >= 1:
        # Número de interlocutores fijado explícitamente por el usuario
        k = min(num_speakers, n_samples)
        if k <= 1:
            labels = np.zeros(n_samples, dtype=int)
        else:
            Z = sch.linkage(l2_features, method='ward')
            labels = sch.fcluster(Z, t=k, criterion='maxclust') - 1
    else:
        # Autodetección: analizar ratio de dendrograma y calidad de silueta
        max_k_test = min(max_speakers, n_samples)
        if n_samples < 4 or max_k_test < 2:
            k = 1
            labels = np.zeros(n_samples, dtype=int)
        else:
            Z = sch.linkage(l2_features, method='ward')
            ratio_2 = Z[-1, 2] / max(1e-5, Z[-2, 2])

            best_sil = -1.0
            best_k = 1
            for cand_k in range(2, max_k_test + 1):
                c_lbls = sch.fcluster(Z, t=cand_k, criterion='maxclust') - 1
                sil = get_silhouette_score(l2_features, c_lbls, cand_k)
                if sil > best_sil:
                    best_sil = sil
                    best_k = cand_k

            # Si el salto entre los dos últimos clusters es bajo y la silueta es pobre, es un solo hablante
            if ratio_2 < 1.25 and best_sil < 0.40:
                k = 1
                labels = np.zeros(n_samples, dtype=int)
            else:
                k = best_k
                labels = sch.fcluster(Z, t=k, criterion='maxclust') - 1

    # 4. Refinamiento por reasignación de centroides (K-Means Refinement)
    if k >= 2 and n_samples >= k:
        for _ in range(4):
            centroids = []
            for c in range(k):
                c_members = l2_features[labels == c]
                if len(c_members) > 0:
                    c_mean = np.mean(c_members, axis=0)
                    c_norm = np.linalg.norm(c_mean)
                    centroids.append(c_mean / max(1e-5, c_norm))
                else:
                    centroids.append(l2_features[np.random.randint(0, n_samples)])
            centroids = np.array(centroids)
            sims = np.dot(l2_features, centroids.T)
            new_labels = np.argmax(sims, axis=1)
            if np.array_equal(new_labels, labels):
                break
            labels = new_labels

    # 5. Suavizado temporal de etiquetas (eliminar tropiezos aislados de 1 fragmento)
    if len(labels) >= 5 and k >= 2:
        try:
            labels = scipy.signal.medfilt(labels, 3).astype(int)
        except Exception:
            pass

    # 6. Fusionar fragmentos continuos de cada interlocutor
    speaker_dict = merge_contiguous_segments(valid_chunks, labels, max_gap=0.35)

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
