import json
from dataclasses import asdict

from injector import Injector, Module, provider, singleton
from mcp.server.fastmcp import FastMCP

from rubin.analyzer import analyze
from rubin.client import AudioClient, SystemAudioClient
from rubin.evaluator import evaluate, list_styles, load_style


class AudioModule(Module):
    @singleton
    @provider
    def provide_audio_client(self) -> AudioClient:
        return SystemAudioClient()


# Snapshot storage: name -> (AudioAnalysis dict, style evaluated against)
_snapshots: dict[str, dict] = {}


def create_server(injector: Injector | None = None) -> FastMCP:
    if injector is None:
        injector = Injector([AudioModule])

    server = FastMCP("rubin")

    def _client() -> AudioClient:
        return injector.get(AudioClient)

    # ------------------------------------------------------------------
    # Tool: evaluate_mix
    # ------------------------------------------------------------------
    @server.tool()
    async def evaluate_mix(
        style: str, duration: float = 5.0, sample_rate: int = 44100
    ) -> str:
        """Capture audio and evaluate the mix against a style profile.

        Args:
            style: Name of the style profile (e.g. "ambient", "synthpop").
            duration: Seconds of audio to capture.
            sample_rate: Sample rate for capture.

        Returns JSON with cohesion_score (0-100), issues, and per-band scores.
        """
        profile = load_style(style)
        audio = _client().capture(duration, sample_rate)
        analysis = analyze(audio, sample_rate)
        result = evaluate(analysis, profile)
        return json.dumps(asdict(result), indent=2)

    # ------------------------------------------------------------------
    # Tool: capture_snapshot
    # ------------------------------------------------------------------
    @server.tool()
    async def capture_snapshot(
        name: str, duration: float = 5.0, sample_rate: int = 44100
    ) -> str:
        """Capture audio and save the analysis as a named snapshot for later comparison.

        Args:
            name: Identifier for this snapshot (e.g. "before_eq", "final_mix").
            duration: Seconds of audio to capture.
            sample_rate: Sample rate for capture.

        Returns the full analysis as JSON.
        """
        audio = _client().capture(duration, sample_rate)
        analysis = analyze(audio, sample_rate)
        analysis_dict = asdict(analysis)
        _snapshots[name] = analysis_dict
        return json.dumps(analysis_dict, indent=2)

    # ------------------------------------------------------------------
    # Tool: compare_snapshots
    # ------------------------------------------------------------------
    @server.tool()
    async def compare_snapshots(name_a: str, name_b: str) -> str:
        """Compare two previously captured snapshots.

        Args:
            name_a: First snapshot name.
            name_b: Second snapshot name.

        Returns JSON with per-metric deltas between the two snapshots.
        """
        if name_a not in _snapshots:
            return json.dumps({"error": f"Snapshot '{name_a}' not found"})
        if name_b not in _snapshots:
            return json.dumps({"error": f"Snapshot '{name_b}' not found"})

        a = _snapshots[name_a]
        b = _snapshots[name_b]

        def _delta(path: list[str], da: dict, db: dict) -> dict:
            result = {}
            for key in da:
                va, vb = da[key], db.get(key)
                if isinstance(va, dict) and isinstance(vb, dict):
                    result[key] = _delta(path + [key], va, vb)
                elif isinstance(va, list) and isinstance(vb, list):
                    result[key] = {
                        "a": va,
                        "b": vb,
                        "delta": [
                            round(float(bv) - float(av), 6) for av, bv in zip(va, vb)
                        ],
                    }
                elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    result[key] = {
                        "a": va,
                        "b": vb,
                        "delta": round(float(vb) - float(va), 6),
                    }
                else:
                    result[key] = {"a": va, "b": vb}
            return result

        comparison = _delta([], a, b)
        return json.dumps(comparison, indent=2)

    # ------------------------------------------------------------------
    # Tool: get_spectral_data
    # ------------------------------------------------------------------
    @server.tool()
    async def get_spectral_data(duration: float = 5.0, sample_rate: int = 44100) -> str:
        """Capture audio and return raw spectral analysis data.

        Args:
            duration: Seconds of audio to capture.
            sample_rate: Sample rate for capture.

        Returns the full analysis as JSON (spectral, timbral,
        loudness, frequency bands, stereo).
        """
        audio = _client().capture(duration, sample_rate)
        analysis = analyze(audio, sample_rate)
        return json.dumps(asdict(analysis), indent=2)

    # ------------------------------------------------------------------
    # Tool: suggest_adjustments
    # ------------------------------------------------------------------
    @server.tool()
    async def suggest_adjustments(
        style: str, duration: float = 5.0, sample_rate: int = 44100
    ) -> str:
        """Capture audio, evaluate against a style, and return
        only the actionable suggestions.

        Args:
            style: Name of the style profile.
            duration: Seconds of audio to capture.
            sample_rate: Sample rate for capture.

        Returns JSON list of suggestions sorted by severity.
        """
        profile = load_style(style)
        audio = _client().capture(duration, sample_rate)
        analysis = analyze(audio, sample_rate)
        result = evaluate(analysis, profile)

        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_issues = sorted(
            result.issues, key=lambda i: severity_order.get(i.severity, 3)
        )
        suggestions = [
            {
                "severity": issue.severity,
                "category": issue.category,
                "band": issue.band,
                "problem": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in sorted_issues
        ]

        return json.dumps(
            {
                "style": style,
                "cohesion_score": result.cohesion_score,
                "suggestions": suggestions,
            },
            indent=2,
        )

    # ------------------------------------------------------------------
    # Tool: list_style_profiles
    # ------------------------------------------------------------------
    @server.tool()
    async def list_style_profiles() -> str:
        """List all available style profiles.

        Returns JSON list of style names.
        """
        return json.dumps(list_styles())

    # ------------------------------------------------------------------
    # Tool: list_snapshots
    # ------------------------------------------------------------------
    @server.tool()
    async def list_snapshots() -> str:
        """List all saved snapshots.

        Returns JSON list of snapshot names.
        """
        return json.dumps(list(sorted(_snapshots.keys())))

    return server


mcp = create_server()
