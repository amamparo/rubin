import json
from dataclasses import dataclass, field
from pathlib import Path

from rubin.analyzer import AudioAnalysis

STYLES_DIR = Path(__file__).parent.parent.parent / "styles"


@dataclass
class Range:
    low: float
    high: float

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def deviation(self, value: float) -> float:
        """How far outside the range the value is (0 if inside)."""
        if value < self.low:
            return self.low - value
        if value > self.high:
            return value - self.high
        return 0.0


@dataclass
class StyleProfile:
    name: str
    description: str
    frequency_balance: dict[str, Range] = field(default_factory=dict)
    dynamic_range_db: Range | None = None
    brightness: Range | None = None  # spectral centroid target
    stereo_width: Range | None = None
    rms_mean: Range | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "StyleProfile":
        freq_bal = {}
        for band, r in data.get("frequency_balance", {}).items():
            freq_bal[band] = Range(r["low"], r["high"])

        def _range_or_none(key: str) -> Range | None:
            r = data.get(key)
            return Range(r["low"], r["high"]) if r else None

        return cls(
            name=data["name"],
            description=data["description"],
            frequency_balance=freq_bal,
            dynamic_range_db=_range_or_none("dynamic_range_db"),
            brightness=_range_or_none("brightness"),
            stereo_width=_range_or_none("stereo_width"),
            rms_mean=_range_or_none("rms_mean"),
        )


@dataclass
class Issue:
    category: str  # e.g. "masking", "mud", "harshness", "thin_bass"
    severity: str  # "low", "medium", "high"
    band: str | None  # which frequency band, if applicable
    message: str
    suggestion: str


@dataclass
class EvaluationResult:
    style: str
    cohesion_score: float  # 0-100
    issues: list[Issue]
    band_scores: dict[str, float]  # per-band score 0-100


def load_style(name: str) -> StyleProfile:
    path = STYLES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Style profile not found: {name}")
    with open(path) as f:
        return StyleProfile.from_dict(json.load(f))


def list_styles() -> list[str]:
    if not STYLES_DIR.exists():
        return []
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def evaluate(analysis: AudioAnalysis, profile: StyleProfile) -> EvaluationResult:
    issues: list[Issue] = []
    band_scores: dict[str, float] = {}
    score_components: list[float] = []

    # --- Frequency band evaluation ---
    bands = analysis.frequency_bands
    band_map: dict[str, float] = {
        "sub_bass": bands.sub_bass,
        "bass": bands.bass,
        "low_mid": bands.low_mid,
        "mid": bands.mid,
        "upper_mid": bands.upper_mid,
        "presence": bands.presence,
        "brilliance": bands.brilliance,
    }

    for band_name, actual in band_map.items():
        target = profile.frequency_balance.get(band_name)
        if target is None:
            band_scores[band_name] = 100.0
            continue

        dev = target.deviation(actual)
        span = (target.high - target.low) / 2 if target.high > target.low else 1.0
        # Score: 100 when in range, drops proportionally outside
        score = max(0.0, 100.0 - (dev / span) * 50) if span > 0 else 100.0
        band_scores[band_name] = round(score, 1)
        score_components.append(score)

        if actual > target.high:
            severity = "high" if dev > span * 2 else "medium" if dev > span else "low"
            issue_cat = _categorize_excess(band_name)
            issues.append(
                Issue(
                    category=issue_cat,
                    severity=severity,
                    band=band_name,
                    message=(
                        f"{band_name} energy ({actual:.4f}) exceeds "
                        f"target range [{target.low:.4f}, "
                        f"{target.high:.4f}]"
                    ),
                    suggestion=_suggest_reduction(band_name),
                )
            )
        elif actual < target.low:
            severity = "high" if dev > span * 2 else "medium" if dev > span else "low"
            issues.append(
                Issue(
                    category="thin_" + band_name,
                    severity=severity,
                    band=band_name,
                    message=(
                        f"{band_name} energy ({actual:.4f}) below "
                        f"target range [{target.low:.4f}, "
                        f"{target.high:.4f}]"
                    ),
                    suggestion=_suggest_boost(band_name),
                )
            )

    # --- Dynamic range ---
    if profile.dynamic_range_db:
        dr = analysis.loudness.dynamic_range_db
        target = profile.dynamic_range_db
        if target.contains(dr):
            score_components.append(100.0)
        else:
            dev = target.deviation(dr)
            span = (target.high - target.low) / 2 if target.high > target.low else 1.0
            s = max(0.0, 100.0 - (dev / span) * 50)
            score_components.append(s)
            if dr < target.low:
                issues.append(
                    Issue(
                        category="over_compressed",
                        severity="medium",
                        band=None,
                        message=(
                            f"Dynamic range ({dr:.1f} dB) is below "
                            f"target [{target.low:.1f}, "
                            f"{target.high:.1f}] dB"
                        ),
                        suggestion=(
                            "Reduce compression ratio or raise "
                            "threshold to restore dynamics."
                        ),
                    )
                )
            elif dr > target.high:
                issues.append(
                    Issue(
                        category="under_compressed",
                        severity="low",
                        band=None,
                        message=(
                            f"Dynamic range ({dr:.1f} dB) exceeds "
                            f"target [{target.low:.1f}, "
                            f"{target.high:.1f}] dB"
                        ),
                        suggestion=(
                            "Apply gentle bus compression "
                            "to tighten the dynamic range."
                        ),
                    )
                )

    # --- Brightness (spectral centroid) ---
    if profile.brightness:
        centroid = analysis.spectral.centroid_mean
        target = profile.brightness
        if target.contains(centroid):
            score_components.append(100.0)
        else:
            dev = target.deviation(centroid)
            span = (target.high - target.low) / 2 if target.high > target.low else 1.0
            s = max(0.0, 100.0 - (dev / span) * 50)
            score_components.append(s)
            if centroid > target.high:
                issues.append(
                    Issue(
                        category="harshness",
                        severity="medium",
                        band="upper_mid",
                        message=(
                            f"Spectral centroid ({centroid:.0f} Hz) "
                            "is above target — mix may sound "
                            "harsh or brittle."
                        ),
                        suggestion=(
                            "Roll off highs with a low-pass " "or shelf EQ above 8 kHz."
                        ),
                    )
                )
            else:
                issues.append(
                    Issue(
                        category="dullness",
                        severity="medium",
                        band="presence",
                        message=(
                            f"Spectral centroid ({centroid:.0f} Hz) "
                            "is below target — mix may sound dull."
                        ),
                        suggestion=(
                            "Add a subtle high-shelf boost " "around 8-12 kHz for air."
                        ),
                    )
                )

    # --- Stereo width ---
    if profile.stereo_width:
        width = analysis.stereo.width
        target = profile.stereo_width
        if target.contains(width):
            score_components.append(100.0)
        else:
            dev = target.deviation(width)
            span = (target.high - target.low) / 2 if target.high > target.low else 0.1
            s = max(0.0, 100.0 - (dev / span) * 50)
            score_components.append(s)
            if width > target.high:
                issues.append(
                    Issue(
                        category="too_wide",
                        severity="low",
                        band=None,
                        message=(
                            f"Stereo width ({width:.3f}) exceeds "
                            "target — may lose mono compatibility."
                        ),
                        suggestion=(
                            "Narrow the stereo image on "
                            "low-frequency elements; "
                            "check mono compatibility."
                        ),
                    )
                )
            else:
                issues.append(
                    Issue(
                        category="too_narrow",
                        severity="low",
                        band=None,
                        message=(
                            f"Stereo width ({width:.3f}) is below "
                            "target — mix may sound flat."
                        ),
                        suggestion=(
                            "Use subtle stereo widening on "
                            "pads/reverbs, or pan elements "
                            "further apart."
                        ),
                    )
                )

    # --- Cohesion score ---
    if score_components:
        cohesion_score = round(sum(score_components) / len(score_components), 1)
    else:
        cohesion_score = 100.0

    return EvaluationResult(
        style=profile.name,
        cohesion_score=cohesion_score,
        issues=issues,
        band_scores=band_scores,
    )


def _categorize_excess(band: str) -> str:
    return {
        "sub_bass": "rumble",
        "bass": "mud",
        "low_mid": "mud",
        "mid": "masking",
        "upper_mid": "harshness",
        "presence": "harshness",
        "brilliance": "sibilance",
    }.get(band, "excess")


def _suggest_reduction(band: str) -> str:
    return {
        "sub_bass": "Apply a high-pass filter around 30-40 Hz to tame sub-bass rumble.",
        "bass": "Cut 2-3 dB in the 100-250 Hz range to reduce muddiness.",
        "low_mid": "Dip the 250-500 Hz region to clear boxy buildup.",
        "mid": "Scoop 1-2 dB around 500-2000 Hz to reduce masking between elements.",
        "upper_mid": "Attenuate 2-4 kHz to reduce harshness and listening fatigue.",
        "presence": (
            "Tame 4-6 kHz with a gentle cut " "to soften presence-range aggression."
        ),
        "brilliance": "Roll off above 10 kHz or de-ess vocals to control sibilance.",
    }.get(band, f"Reduce energy in the {band} band.")


def _suggest_boost(band: str) -> str:
    return {
        "sub_bass": "Boost sub-bass with a low shelf or saturator below 60 Hz.",
        "bass": "Add warmth with a gentle boost around 80-150 Hz.",
        "low_mid": "A small lift around 300-400 Hz can add body to thin mixes.",
        "mid": "Boost midrange presence to help vocals and leads cut through.",
        "upper_mid": "A lift around 2-4 kHz adds clarity and articulation.",
        "presence": "Boost 4-6 kHz for more definition and attack.",
        "brilliance": "Add a high shelf boost above 8 kHz for air and sparkle.",
    }.get(band, f"Boost energy in the {band} band.")
