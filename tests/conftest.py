import numpy as np
import pytest
from injector import Injector, Module, provider, singleton

from rubin.client import AudioClient
from rubin.server import create_server


class FakeAudioClient(AudioClient):
    """In-memory fake that returns a configurable audio buffer."""

    def __init__(self):
        self._audio: np.ndarray | None = None
        self.captures: list[tuple[float, int]] = []

    def set_audio(self, audio: np.ndarray) -> None:
        self._audio = audio

    def capture(self, duration: float, sample_rate: int = 44100) -> np.ndarray:
        self.captures.append((duration, sample_rate))
        if self._audio is not None:
            return self._audio
        # Default: generate a simple sine wave (stereo)
        t = np.linspace(0, duration, int(duration * sample_rate), endpoint=False)
        sine = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return np.stack([sine, sine])

    def close(self) -> None:
        pass


class FakeAudioModule(Module):
    def __init__(self, fake_client: FakeAudioClient):
        self._fake_client = fake_client

    @singleton
    @provider
    def provide_audio_client(self) -> AudioClient:
        return self._fake_client


@pytest.fixture
def fake_client():
    return FakeAudioClient()


@pytest.fixture
def mcp_server(fake_client):
    injector = Injector([FakeAudioModule(fake_client)])
    return create_server(injector)
