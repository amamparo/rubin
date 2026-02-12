import json
from unittest.mock import patch

import numpy as np

from rubin.analyzer import analyze
from rubin.evaluator import (
    Range,
    StyleProfile,
    audition,
    delete_user_style,
    evaluate,
    is_user_style,
    list_styles,
    load_style,
    save_user_style,
)


def _make_sine(freq: float, duration: float = 1.0, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(duration * sr), endpoint=False)
    sine = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([sine, sine])


def test_list_styles():
    styles = list_styles()
    expected = [
        "ambient",
        "downtempo",
        "drum-and-bass",
        "edm",
        "folk",
        "hip-hop",
        "house",
        "industrial",
        "jazz",
        "lo-fi",
        "orchestral",
        "rnb",
        "rock",
        "synthpop",
        "techno",
        "vaporwave",
    ]
    for name in expected:
        assert name in styles


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


def test_save_and_load_user_style(tmp_path):
    """User styles are saved to and loaded from the user styles dir."""
    profile = StyleProfile(
        name="custom",
        description="A test custom style",
        frequency_balance={"bass": Range(0.01, 0.1)},
        dynamic_range_db=Range(6, 18),
    )
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        save_user_style(profile)
        loaded = load_style("custom")
        assert loaded.name == "custom"
        assert loaded.description == "A test custom style"
        assert "bass" in loaded.frequency_balance
        assert loaded.dynamic_range_db is not None


def test_user_style_overrides_builtin(tmp_path):
    """A user style with the same name as a built-in takes precedence."""
    profile = StyleProfile(
        name="ambient",
        description="My custom ambient",
        frequency_balance={"bass": Range(0.5, 0.9)},
    )
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        save_user_style(profile)
        loaded = load_style("ambient")
        assert loaded.description == "My custom ambient"


def test_list_styles_includes_user(tmp_path):
    """User styles appear in the combined list."""
    profile = StyleProfile(
        name="my-custom",
        description="Custom",
        frequency_balance={},
    )
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        save_user_style(profile)
        styles = list_styles()
        assert "my-custom" in styles
        assert "ambient" in styles  # built-ins still present


def test_is_user_style(tmp_path):
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        assert not is_user_style("ambient")
        save_user_style(
            StyleProfile(name="test-user", description="test", frequency_balance={})
        )
        assert is_user_style("test-user")


def test_delete_user_style(tmp_path):
    profile = StyleProfile(
        name="deleteme",
        description="To be deleted",
        frequency_balance={},
    )
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        save_user_style(profile)
        assert is_user_style("deleteme")
        delete_user_style("deleteme")
        assert not is_user_style("deleteme")


def test_profile_roundtrip(tmp_path):
    """All fields survive save/load roundtrip."""
    profile = StyleProfile(
        name="roundtrip",
        description="Full roundtrip test",
        frequency_balance={
            "sub_bass": Range(0.001, 0.05),
            "bass": Range(0.01, 0.1),
        },
        dynamic_range_db=Range(6, 18),
        brightness=Range(2000, 5000),
        stereo_width=Range(0.1, 0.4),
        rms_mean=Range(0.05, 0.25),
    )
    with patch("rubin.evaluator.USER_STYLES_DIR", tmp_path):
        save_user_style(profile)
        loaded = load_style("roundtrip")
        assert loaded.name == profile.name
        assert loaded.brightness.low == 2000
        assert loaded.brightness.high == 5000
        assert loaded.rms_mean.low == 0.05
        path = tmp_path / "roundtrip.json"
        data = json.loads(path.read_text())
        assert data["name"] == "roundtrip"
        assert "frequency_balance" in data


def test_audition_low_freq_classifies_as_bass():
    """A low-frequency sine should be classified as a bass element."""
    audio = _make_sine(80)
    analysis = analyze(audio, 44100)
    profile = load_style("techno")
    result = audition(analysis, profile)
    assert result.role == "bass"
    assert result.style == "techno"
    assert 0 <= result.fit_score <= 100
    assert len(result.dominant_bands) > 0
    assert len(result.frequency_profile) == 7


def test_audition_mid_freq_classifies_as_lead():
    """A mid-frequency sine should be classified as a lead element."""
    audio = _make_sine(2000)
    analysis = analyze(audio, 44100)
    profile = load_style("synthpop")
    result = audition(analysis, profile)
    assert result.role == "lead"


def test_audition_explicit_role_override():
    """User-specified role should override auto-detection."""
    audio = _make_sine(80)
    analysis = analyze(audio, 44100)
    profile = load_style("ambient")
    result = audition(analysis, profile, role="pad")
    assert result.role == "pad"


def test_audition_frequency_profile_sums_to_one():
    """Frequency profile values should sum to approximately 1."""
    audio = _make_sine(440)
    analysis = analyze(audio, 44100)
    profile = load_style("ambient")
    result = audition(analysis, profile)
    total = sum(result.frequency_profile.values())
    assert abs(total - 1.0) < 0.01
