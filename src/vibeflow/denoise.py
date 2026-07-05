"""Optional noise front-end applied to the mic audio BEFORE speech recognition.

Two cheap, fully-offline stages that make dictation robust to steady background
noise (a fan, AC, traffic hum) — the accuracy gap vs cloud dictation in a noisy
room:

  1. **Band-pass filter** — keep only the human-voice band (~80 Hz–8 kHz),
     dropping out-of-band rumble and hiss. (The "make it sound like a phone
     line" trick; removes noise *outside* the voice band.)
  2. **Spectral noise reduction** — estimate the steady noise profile and
     subtract it across the spectrum, *including inside* the voice band, via
     `noisereduce` (stationary mode — ideal for a constant fan).

Everything is lazy-imported and defensive: if a dependency is missing or the
math fails, we return the ORIGINAL audio untouched — the noise front-end must
never break dictation. Tunables live in config under ``audio.*``.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("vibeflow")


def _bandpass(x, sample_rate: int, low_hz: float, high_hz: float):
    """4th-order Butterworth band-pass (SOS form). Returns x unchanged on a bad band."""
    from scipy.signal import butter, sosfilt

    nyq = 0.5 * float(sample_rate)
    low = max(1e-4, low_hz / nyq)
    high = min(0.999, high_hz / nyq)
    if low >= high:
        return x
    sos = butter(4, [low, high], btype="band", output="sos")
    return sosfilt(sos, x)


def reduce_noise(
    audio,
    sample_rate: int = 16000,
    *,
    bandpass: bool = True,
    spectral: bool = True,
    low_hz: float = 80.0,
    high_hz: float = 8000.0,
):
    """Clean ``audio`` (float32 mono @ ``sample_rate``). Returns the cleaned array,
    or the ORIGINAL on any failure — never raises. Over-cleaning can hurt ASR, so
    both stages are individually toggleable."""
    try:
        import numpy as np

        x = np.asarray(audio, dtype="float32").flatten()
        if x.size == 0:
            return audio

        if bandpass:
            try:
                x = np.asarray(_bandpass(x, sample_rate, low_hz, high_hz), dtype="float32")
            except Exception as exc:  # scipy missing / bad params
                _log.info("denoise: band-pass skipped (%s)", exc)

        if spectral:
            try:
                import noisereduce as nr

                x = np.asarray(
                    nr.reduce_noise(y=x, sr=int(sample_rate), stationary=True),
                    dtype="float32",
                )
            except Exception as exc:  # noisereduce missing / failure
                _log.info("denoise: spectral reduction skipped (%s)", exc)

        return x
    except Exception as exc:
        _log.info("denoise: disabled this pass (%s)", exc)
        return audio
