from dataclasses import dataclass

import librosa
import numpy as np


@dataclass
class SpectralFeatures:
    centroid_mean: float
    centroid_std: float
    bandwidth_mean: float
    rolloff_mean: float
    flatness_mean: float


@dataclass
class TimbreFeatures:
    mfcc_means: list[float]
    chroma_means: list[float]


@dataclass
class LoudnessFeatures:
    rms_mean: float
    rms_max: float
    rms_min: float
    dynamic_range_db: float


@dataclass
class FrequencyBandEnergy:
    sub_bass: float  # 20-60 Hz
    bass: float  # 60-250 Hz
    low_mid: float  # 250-500 Hz
    mid: float  # 500-2000 Hz
    upper_mid: float  # 2000-4000 Hz
    presence: float  # 4000-6000 Hz
    brilliance: float  # 6000-20000 Hz


@dataclass
class StereoFeatures:
    width: float  # 0 = mono, 1 = full stereo
    balance: float  # -1 = left, 0 = center, 1 = right
    correlation: float  # 1 = identical, 0 = uncorrelated, -1 = inverted


@dataclass
class AudioAnalysis:
    spectral: SpectralFeatures
    timbre: TimbreFeatures
    loudness: LoudnessFeatures
    frequency_bands: FrequencyBandEnergy
    stereo: StereoFeatures
    sample_rate: int
    duration: float
    num_channels: int


def _band_energy(S: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> float:
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        return 0.0
    return float(np.mean(S[mask]))


def analyze(audio: np.ndarray, sample_rate: int = 44100) -> AudioAnalysis:
    """Analyze a stereo audio buffer.

    Args:
        audio: shape (channels, samples), float32 in [-1, 1]
        sample_rate: sample rate in Hz
    """
    if audio.ndim == 1:
        audio = np.stack([audio, audio])
    num_channels, num_samples = audio.shape
    duration = num_samples / sample_rate

    # Mix to mono for spectral/timbral analysis
    mono = np.mean(audio, axis=0)

    # --- Spectral ---
    centroid = librosa.feature.spectral_centroid(y=mono, sr=sample_rate)[0]
    bandwidth = librosa.feature.spectral_bandwidth(y=mono, sr=sample_rate)[0]
    rolloff = librosa.feature.spectral_rolloff(y=mono, sr=sample_rate)[0]
    flatness = librosa.feature.spectral_flatness(y=mono)[0]

    spectral = SpectralFeatures(
        centroid_mean=float(np.mean(centroid)),
        centroid_std=float(np.std(centroid)),
        bandwidth_mean=float(np.mean(bandwidth)),
        rolloff_mean=float(np.mean(rolloff)),
        flatness_mean=float(np.mean(flatness)),
    )

    # --- Timbre ---
    mfccs = librosa.feature.mfcc(y=mono, sr=sample_rate, n_mfcc=13)
    chroma = librosa.feature.chroma_stft(y=mono, sr=sample_rate)

    timbre = TimbreFeatures(
        mfcc_means=[float(m) for m in np.mean(mfccs, axis=1)],
        chroma_means=[float(c) for c in np.mean(chroma, axis=1)],
    )

    # --- Loudness ---
    rms = librosa.feature.rms(y=mono)[0]
    rms_min = float(np.min(rms))
    rms_max = float(np.max(rms))
    rms_mean = float(np.mean(rms))
    # Dynamic range in dB (avoid log of zero)
    if rms_min > 0 and rms_max > 0:
        dynamic_range_db = float(20 * np.log10(rms_max / rms_min))
    else:
        dynamic_range_db = 0.0

    loudness = LoudnessFeatures(
        rms_mean=rms_mean,
        rms_max=rms_max,
        rms_min=rms_min,
        dynamic_range_db=dynamic_range_db,
    )

    # --- Frequency band energy ---
    S = np.abs(librosa.stft(mono))
    freqs = librosa.fft_frequencies(sr=sample_rate)

    frequency_bands = FrequencyBandEnergy(
        sub_bass=_band_energy(S, freqs, 20, 60),
        bass=_band_energy(S, freqs, 60, 250),
        low_mid=_band_energy(S, freqs, 250, 500),
        mid=_band_energy(S, freqs, 500, 2000),
        upper_mid=_band_energy(S, freqs, 2000, 4000),
        presence=_band_energy(S, freqs, 4000, 6000),
        brilliance=_band_energy(S, freqs, 6000, 20000),
    )

    # --- Stereo ---
    left, right = audio[0], audio[1]
    mid_signal = (left + right) / 2
    side_signal = (left - right) / 2
    mid_energy = float(np.mean(mid_signal**2))
    side_energy = float(np.mean(side_signal**2))
    total_energy = mid_energy + side_energy
    width = side_energy / total_energy if total_energy > 0 else 0.0

    left_energy = float(np.mean(left**2))
    right_energy = float(np.mean(right**2))
    total_lr = left_energy + right_energy
    balance = (right_energy - left_energy) / total_lr if total_lr > 0 else 0.0

    if len(left) > 0:
        correlation = float(
            np.corrcoef(left, right)[0, 1]
            if np.std(left) > 0 and np.std(right) > 0
            else 1.0
        )
    else:
        correlation = 1.0

    stereo = StereoFeatures(width=width, balance=balance, correlation=correlation)

    return AudioAnalysis(
        spectral=spectral,
        timbre=timbre,
        loudness=loudness,
        frequency_bands=frequency_bands,
        stereo=stereo,
        sample_rate=sample_rate,
        duration=duration,
        num_channels=num_channels,
    )
