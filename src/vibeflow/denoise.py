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


def _is_noisy(x, sample_rate: int) -> bool:
    """Rough check for GENUINE background noise. Clean speech has near-silent gaps
    between words (a low noise floor); steady noise (a fan/AC) lifts that floor. We
    only want spectral subtraction when it's actually noisy — on clean audio it
    strips speech detail and wrecks accuracy (the "WinAPK/Nox/Kali" garbage)."""
    try:
        import numpy as np

        n = max(1, int(0.025 * sample_rate))  # 25 ms frames
        usable = (len(x) // n) * n
        if usable < n * 8:
            return False
        frames = x[:usable].reshape(-1, n).astype("float64")
        rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
        floor = float(np.percentile(rms, 20))    # quiet frames ≈ background
        speech = float(np.percentile(rms, 95))   # loud frames ≈ speech
        if speech < 1e-4:
            return False
        # Quiet parts NOT much quieter than speech ⇒ there's a noise floor ⇒ noisy.
        return (floor / speech) > 0.15
    except Exception:
        return False


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
    or the ORIGINAL on any failure — never raises.

    Spectral subtraction is applied ONLY when the audio is genuinely noisy (see
    :func:`_is_noisy`) and gently (``prop_decrease=0.75``), because over-cleaning
    clean audio destroys accuracy. The band-pass (removing sub-80 Hz rumble and
    >8 kHz hiss) is safe on speech, so it always runs."""
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

        if spectral and _is_noisy(x, int(sample_rate)):
            try:
                import noisereduce as nr

                x = np.asarray(
                    nr.reduce_noise(
                        y=x, sr=int(sample_rate), stationary=True, prop_decrease=0.75
                    ),
                    dtype="float32",
                )
            except Exception as exc:  # noisereduce missing / failure
                _log.info("denoise: spectral reduction skipped (%s)", exc)
        elif spectral:
            _log.info("denoise: audio is clean — spectral reduction skipped")

        return x
    except Exception as exc:
        _log.info("denoise: disabled this pass (%s)", exc)
        return audio
