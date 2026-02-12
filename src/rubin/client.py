import socket
import struct
import sys
from abc import ABC, abstractmethod

import numpy as np


class AudioClient(ABC):
    """Captures audio and returns raw PCM buffers."""

    @abstractmethod
    def capture(self, duration: float, sample_rate: int = 44100) -> np.ndarray:
        """Capture audio for `duration` seconds.

        Returns a numpy array of shape (channels, samples) with float32 values
        in [-1.0, 1.0].
        """

    @abstractmethod
    def close(self) -> None:
        """Release any resources."""


class SystemAudioClient(AudioClient):
    """Captures from a system audio device via sounddevice (BlackHole / VB-Audio)."""

    def __init__(self, device: str | int | None = None):
        self._device = device

    def capture(self, duration: float, sample_rate: int = 44100) -> np.ndarray:
        import sounddevice as sd

        frames = int(duration * sample_rate)
        recording = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=2,
            dtype="float32",
            device=self._device,
        )
        sd.wait()
        # sd.rec returns (samples, channels) — transpose to (channels, samples)
        return recording.T

    def close(self) -> None:
        pass


class TcpAudioClient(AudioClient):
    """Receives raw PCM audio over a TCP socket.

    Protocol: the sender writes a 4-byte big-endian uint32 (num_bytes),
    then that many bytes of interleaved float32 stereo PCM.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9878):
        self._host = host
        self._port = port
        self._server_socket: socket.socket | None = None

    def _ensure_listening(self) -> socket.socket:
        if self._server_socket is None:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self._host, self._port))
            self._server_socket.listen(1)
        return self._server_socket

    def capture(self, duration: float, sample_rate: int = 44100) -> np.ndarray:
        srv = self._ensure_listening()
        conn, _ = srv.accept()
        try:
            header = conn.recv(4)
            if len(header) < 4:
                raise IOError("Connection closed before header received")
            (num_bytes,) = struct.unpack(">I", header)
            chunks: list[bytes] = []
            remaining = num_bytes
            while remaining > 0:
                chunk = conn.recv(min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            # Interleaved stereo float32
            samples = np.frombuffer(raw, dtype=np.float32)
            samples = samples.reshape(-1, 2).T
            return samples
        finally:
            conn.close()

    def close(self) -> None:
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None


class StdinAudioClient(AudioClient):
    """Reads raw PCM audio from stdin.

    Expects interleaved stereo float32 piped in, e.g.:
        ffmpeg -i track.wav -f f32le -ac 2 - | rubin --audio stdin
    """

    def capture(self, duration: float, sample_rate: int = 44100) -> np.ndarray:
        num_samples = int(duration * sample_rate)
        num_bytes = num_samples * 2 * 4  # 2 channels, float32
        raw = sys.stdin.buffer.read(num_bytes)
        if not raw:
            raise IOError("No data on stdin")
        samples = np.frombuffer(raw, dtype=np.float32)
        # Pad if we got less than expected
        if len(samples) < num_samples * 2:
            samples = np.pad(samples, (0, num_samples * 2 - len(samples)))
        samples = samples[: num_samples * 2]
        return samples.reshape(-1, 2).T

    def close(self) -> None:
        pass
