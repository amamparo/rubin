import numpy as np

from rubin.analyzer import analyze


def _make_sine(freq: float, duration: float = 1.0, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(duration * sr), endpoint=False)
    sine = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([sine, sine])


def test_analyze_returns_all_fields():
    audio = _make_sine(440)
    result = analyze(audio, 44100)

    assert result.sample_rate == 44100
    assert abs(result.duration - 1.0) < 0.01
    assert result.num_channels == 2

    assert result.spectral.centroid_mean > 0
    assert result.spectral.bandwidth_mean > 0
    assert len(result.timbre.mfcc_means) == 13
    assert len(result.timbre.chroma_means) == 12
    assert result.loudness.rms_mean > 0
    assert result.frequency_bands.mid >= 0
    assert 0 <= result.stereo.width <= 1


def test_analyze_stereo_width_mono():
    """Identical L/R should have near-zero stereo width."""
    audio = _make_sine(440)
    result = analyze(audio, 44100)
    assert result.stereo.width < 0.01
    assert result.stereo.correlation > 0.99


def test_analyze_stereo_width_wide():
    """Different L/R content should have wider stereo."""
    t = np.linspace(0, 1.0, 44100, endpoint=False)
    left = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    right = (0.5 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
    audio = np.stack([left, right])
    result = analyze(audio, 44100)
    assert result.stereo.width > 0.01


def test_analyze_mono_input():
    """Mono (1D) input should be handled gracefully."""
    t = np.linspace(0, 1.0, 44100, endpoint=False)
    mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    result = analyze(mono, 44100)
    assert result.num_channels == 2  # duplicated to stereo
    assert result.duration > 0


def test_low_frequency_has_bass_energy():
    audio = _make_sine(100, duration=1.0)
    result = analyze(audio, 44100)
    assert result.frequency_bands.bass > result.frequency_bands.brilliance
