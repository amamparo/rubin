import json
from dataclasses import dataclass, field
from pathlib import Path

from rubin.analyzer import AudioAnalysis

STYLES_DIR = Path(__file__).parent.parent.parent / "styles"
USER_STYLES_DIR = Path.home() / ".rubin" / "styles"


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


TRACK_ROLES = ("bass", "lead", "pad", "percussion", "texture")


@dataclass
class AuditionResult:
    style: str
    role: str  # detected or user-specified
    fit_score: float  # 0-100
    dominant_bands: list[str]
    frequency_profile: dict[str, float]  # normalized energy per band (0-1)
    issues: list[Issue]


def load_style(name: str) -> StyleProfile:
    # User styles take precedence over built-ins
    user_path = USER_STYLES_DIR / f"{name}.json"
    if user_path.exists():
        with open(user_path) as f:
            return StyleProfile.from_dict(json.load(f))
    builtin_path = STYLES_DIR / f"{name}.json"
    if builtin_path.exists():
        with open(builtin_path) as f:
            return StyleProfile.from_dict(json.load(f))
    raise FileNotFoundError(f"Style profile not found: {name}")


def list_styles() -> list[str]:
    names: set[str] = set()
    if STYLES_DIR.exists():
        names.update(p.stem for p in STYLES_DIR.glob("*.json"))
    if USER_STYLES_DIR.exists():
        names.update(p.stem for p in USER_STYLES_DIR.glob("*.json"))
    return sorted(names)


def is_user_style(name: str) -> bool:
    return (USER_STYLES_DIR / f"{name}.json").exists()


def save_user_style(profile: StyleProfile) -> Path:
    USER_STYLES_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_STYLES_DIR / f"{profile.name}.json"
    data = _profile_to_dict(profile)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return path


def delete_user_style(name: str) -> None:
    path = USER_STYLES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"User style not found: {name}")
    path.unlink()


def _profile_to_dict(profile: StyleProfile) -> dict:
    data: dict = {"name": profile.name, "description": profile.description}
    if profile.frequency_balance:
        data["frequency_balance"] = {
            band: {"low": r.low, "high": r.high}
            for band, r in profile.frequency_balance.items()
        }
    for key in ("dynamic_range_db", "brightness", "stereo_width", "rms_mean"):
        r = getattr(profile, key)
        if r is not None:
            data[key] = {"low": r.low, "high": r.high}
    return data


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


def audition(
    analysis: AudioAnalysis, profile: StyleProfile, role: str | None = None
) -> AuditionResult:
    """Analyze an isolated track in the context of a style profile."""
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

    # Normalize energy to 0-1 for frequency profile
    total_energy = sum(band_map.values())
    if total_energy > 0:
        freq_profile = {b: v / total_energy for b, v in band_map.items()}
    else:
        freq_profile = {b: 0.0 for b in band_map}

    # Dominant bands: top bands that together account for >= 70% of energy
    sorted_bands = sorted(freq_profile.items(), key=lambda x: x[1], reverse=True)
    dominant: list[str] = []
    cumulative = 0.0
    for band_name, proportion in sorted_bands:
        if proportion > 0:
            dominant.append(band_name)
            cumulative += proportion
            if cumulative >= 0.7:
                break

    # Classify role if not provided
    if role is None:
        role = _classify_role(analysis, freq_profile)

    # Evaluate fit: does this track's energy land in the right place
    # for its role within this style?
    issues: list[Issue] = []
    fit_components: list[float] = []

    # Role-band affinity: which bands should this role emphasize?
    role_bands = _role_band_affinity(role)
    primary_bands = role_bands["primary"]
    avoid_bands = role_bands["avoid"]

    # Score: energy in primary bands should be high
    primary_energy = sum(freq_profile.get(b, 0) for b in primary_bands)
    primary_score = min(100.0, primary_energy * 200)  # 50%+ = perfect
    fit_components.append(primary_score)

    # Penalty: energy in avoid bands
    avoid_energy = sum(freq_profile.get(b, 0) for b in avoid_bands)
    if avoid_energy > 0.15:
        avoid_score = max(0.0, 100.0 - (avoid_energy - 0.15) * 400)
        fit_components.append(avoid_score)
        for b in avoid_bands:
            if freq_profile.get(b, 0) > 0.1:
                issues.append(
                    Issue(
                        category="role_conflict",
                        severity="medium",
                        band=b,
                        message=(
                            f"This {role} element has significant "
                            f"energy in {b} ({freq_profile[b]:.0%}), "
                            f"which may clash with other elements "
                            f"in a {profile.name} mix."
                        ),
                        suggestion=_role_conflict_suggestion(role, b),
                    )
                )

    # Check if dominant bands fall within the style's target ranges
    for band_name in dominant:
        target = profile.frequency_balance.get(band_name)
        if target is None:
            continue
        actual = band_map[band_name]
        if actual > target.high * 1.5:
            issues.append(
                Issue(
                    category="excess_for_style",
                    severity="low",
                    band=band_name,
                    message=(
                        f"{band_name} energy ({actual:.4f}) is high "
                        f"relative to {profile.name} targets "
                        f"[{target.low:.4f}, {target.high:.4f}] "
                        f"— this track may dominate that range."
                    ),
                    suggestion=(
                        f"Consider taming {band_name} on this "
                        f"track to leave room for other elements."
                    ),
                )
            )

    fit_score = round(
        sum(fit_components) / len(fit_components) if fit_components else 100.0, 1
    )

    return AuditionResult(
        style=profile.name,
        role=role,
        fit_score=fit_score,
        dominant_bands=dominant,
        frequency_profile={b: round(v, 4) for b, v in freq_profile.items()},
        issues=issues,
    )


def _classify_role(analysis: AudioAnalysis, freq_profile: dict[str, float]) -> str:
    """Classify an isolated track's role from its spectral profile."""
    low_energy = freq_profile.get("sub_bass", 0) + freq_profile.get("bass", 0)
    mid_energy = freq_profile.get("mid", 0) + freq_profile.get("upper_mid", 0)
    high_energy = freq_profile.get("presence", 0) + freq_profile.get("brilliance", 0)

    # Percussion: high dynamic range + presence/brilliance energy
    if analysis.loudness.dynamic_range_db > 20 and high_energy > 0.25:
        return "percussion"

    # Texture: high spectral flatness (noise-like)
    if analysis.spectral.flatness_mean > 0.3:
        return "texture"

    # Bass: dominant low-frequency energy
    if low_energy > 0.5:
        return "bass"

    # Pad: broad, even distribution + wide stereo
    band_values = list(freq_profile.values())
    if band_values:
        spread = max(band_values) - min(band_values)
        if spread < 0.2 and analysis.stereo.width > 0.1:
            return "pad"

    # Lead: dominant mid/upper-mid energy
    if mid_energy > 0.3:
        return "lead"

    return "lead"  # default fallback


def _role_band_affinity(role: str) -> dict[str, list[str]]:
    """Which bands a role should emphasize vs avoid."""
    affinities = {
        "bass": {
            "primary": ["sub_bass", "bass"],
            "avoid": ["upper_mid", "presence", "brilliance"],
        },
        "lead": {
            "primary": ["mid", "upper_mid", "presence"],
            "avoid": ["sub_bass"],
        },
        "pad": {
            "primary": ["low_mid", "mid"],
            "avoid": [],
        },
        "percussion": {
            "primary": ["presence", "brilliance", "upper_mid"],
            "avoid": ["sub_bass"],
        },
        "texture": {
            "primary": ["mid", "presence", "brilliance"],
            "avoid": [],
        },
    }
    return affinities.get(role, {"primary": ["mid"], "avoid": []})


def _role_conflict_suggestion(role: str, band: str) -> str:
    suggestions = {
        ("bass", "upper_mid"): (
            "Apply a low-pass filter around 2-4 kHz "
            "to keep the bass focused in the low end."
        ),
        ("bass", "presence"): (
            "Roll off above 4 kHz — bass elements " "rarely need presence-range energy."
        ),
        ("bass", "brilliance"): (
            "Filter out high frequencies above 6 kHz "
            "to avoid interference with cymbals/hats."
        ),
        ("lead", "sub_bass"): (
            "High-pass the lead around 80-100 Hz " "to avoid competing with the bass."
        ),
        ("percussion", "sub_bass"): (
            "High-pass percussion above 60 Hz unless " "it's a kick drum."
        ),
    }
    return suggestions.get(
        (role, band),
        f"Consider reducing {band} energy on this {role} element.",
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
