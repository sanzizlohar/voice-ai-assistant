"""WAV I/O and PCM helpers on the standard library (wave/struct/array).

Audio flows through the pipeline as ``array('h')`` of signed 16-bit mono
samples at 16 kHz unless stated otherwise.
"""
from __future__ import annotations

import array
import io
import math
import struct
import wave

TARGET_SR = 16_000


def rms(samples: array.array) -> float:
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += s * s
    return math.sqrt(acc / len(samples)) / 32768.0


def to_float(samples: array.array) -> list[float]:
    return [s / 32768.0 for s in samples]


def from_float(vals) -> array.array:
    out = array.array("h")
    for v in vals:
        out.append(int(max(-1.0, min(1.0, v)) * 32767))
    return out


def write_wav(path_or_buf, samples: array.array, sr: int = TARGET_SR) -> None:
    """Write 16-bit mono PCM to a path or a binary file object."""
    close = False
    if isinstance(path_or_buf, (str, bytes)) or hasattr(path_or_buf, "__fspath__"):
        fh = open(path_or_buf, "wb")
        close = True
    else:
        fh = path_or_buf
    try:
        with wave.Wave_write(fh) as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(samples.tobytes())
    finally:
        if close:
            fh.close()


def read_wav(path_or_buf) -> tuple[array.array, int]:
    """Read any 8/16/24/32-bit or float WAV into 16-bit mono samples.

    Accepts a filesystem path (str/os.PathLike), raw WAV bytes, or an
    open binary file object."""
    close = False
    if isinstance(path_or_buf, bytes):
        fh = io.BytesIO(path_or_buf)
    elif isinstance(path_or_buf, str) or hasattr(path_or_buf, "__fspath__"):
        fh = open(path_or_buf, "rb")
        close = True
    else:
        fh = path_or_buf
    try:
        with wave.Wave_read(fh) as w:
            sr = w.getframerate()
            width = w.getsampwidth()
            channels = w.getnchannels()
            raw = w.readframes(w.getnframes())
    finally:
        if close:
            fh.close()

    if width == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        if sys_byteorder_big():
            samples.byteswap()
    elif width == 1:
        samples = array.array("h", (((b - 128) << 8) for b in raw))
    elif width == 4:
        n = len(raw) // 4
        floats = struct.unpack(f"<{n}f", raw[: n * 4])
        samples = array.array(
            "h", (int(max(-1.0, min(1.0, v)) * 32767) for v in floats))
    else:  # width == 3, 24-bit
        samples = array.array("h")
        for i in range(0, len(raw) - 2, 3):
            v = int.from_bytes(raw[i:i + 3], "little", signed=True)
            samples.append(v >> 8)

    if channels > 1:  # average downmix
        samples = array.array(
            "h", (sum(samples[i:i + channels]) // channels
                  for i in range(0, len(samples) - channels + 1, channels)))
    return samples, sr


def sys_byteorder_big() -> bool:
    return struct.pack("h", 1) != b"\x01\x00"


def resample(samples: array.array, sr_in: int,
             sr_out: int = TARGET_SR) -> array.array:
    if sr_in == sr_out or not samples:
        return samples
    ratio = sr_in / sr_out
    n_out = int(len(samples) / ratio)
    out = array.array("h")
    for i in range(n_out):
        pos = i * ratio
        i0 = int(pos)
        frac = pos - i0
        a = samples[i0]
        b = samples[min(i0 + 1, len(samples) - 1)]
        out.append(int(a + (b - a) * frac))
    return out


def mix_noise(samples: array.array, snr_db: float,
              rng) -> array.array:
    """Additive white noise at ``snr_db`` below the signal RMS."""
    sig = rms(samples)
    if sig <= 0:
        return samples
    noise_amp = sig * (10 ** (-snr_db / 20.0)) * 32768.0
    out = array.array("h")
    for s in samples:
        v = s + rng.gauss(0.0, noise_amp)
        out.append(int(max(-32768, min(32767, v))))
    return out
