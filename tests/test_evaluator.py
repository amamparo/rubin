import numpy as np

from rubin.analyzer import analyze
from rubin.evaluator import Range, StyleProfile, evaluate, list_styles, load_style


def _make_sine(freq: float, duration: float = 1.0, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(duration * sr), endpoint=False)
    sine = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([sine, sine])


def test_list_styles():
    styles = list_styles()
    assert "ambient" in styles
    assert "synthpop" in styles
    assert "lo-fi" in styles
    assert "techno" in styles
    assert "orchestral" in styles


def test_load_style():
    profile = load_style("ambient")
    assert profile.name == "ambient"
    assert "bass" in profile.frequency_balance
    assert profile.dynamic_range_db is not None


def test_evaluate_returns_result():
    audio = _make_sine(440)
    analysis = analyze(audio, 44100)
    profile = load_style("ambient")
    result = evaluate(analysis, profile)

    assert result.style == "ambient"
    assert 0 <= result.cohesion_score <= 100
    assert isinstance(result.issues, list)
    assert isinstance(result.band_scores, dict)


def test_evaluate_perfect_score_when_in_range():
    """A profile with very wide ranges should give a high score."""
    profile = StyleProfile(
        name="test",
        description="test",
        frequency_balance={
            "sub_bass": Range(0, 100),
            "bass": Range(0, 100),
            "low_mid": Range(0, 100),
            "mid": Range(0, 100),
            "upper_mid": Range(0, 100),
            "presence": Range(0, 100),
            "brilliance": Range(0, 100),
        },
        dynamic_range_db=Range(0, 100),
        brightness=Range(0, 20000),
        stereo_width=Range(0, 1),
    )
    audio = _make_sine(440)
    analysis = analyze(audio, 44100)
    result = evaluate(analysis, profile)
    assert result.cohesion_score == 100.0
    assert len(result.issues) == 0


def test_evaluate_flags_issues():
    """A very tight profile should flag issues for a broadband signal."""
    profile = StyleProfile(
        name="tight",
        description="tight test profile",
        frequency_balance={
            "mid": Range(999.0, 999.1),
        },
    )
    audio = _make_sine(440)
    analysis = analyze(audio, 44100)
    result = evaluate(analysis, profile)
    # Should have at least one issue since the sine won't match such a tight range
    assert len(result.issues) > 0 or result.band_scores.get("mid", 100) < 100
