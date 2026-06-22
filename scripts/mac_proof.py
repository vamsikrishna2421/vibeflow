"""M0 — console proof for the macOS port.

Records a few seconds from the microphone and prints what ``transcriber`` hears.
This proves the two cross-platform "engine" pieces work natively on the Mac —
``sounddevice`` capture (needs Microphone permission) and ``faster-whisper``
inference (CPU/int8 on Apple Silicon) — before any GUI / menu-bar code exists.

Run from the repo root inside the venv::

    python scripts/mac_proof.py            # records 3 seconds
    python scripts/mac_proof.py --seconds 5 --model small

Nothing here is Mac-specific: it imports the same ``vibeflow.audio`` /
``vibeflow.transcriber`` the Windows app uses. The first run downloads the
speech model (~150 MB) into ~/.config/VibeFlow/models and needs internet once.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running straight from a checkout (mirrors the test suite's
# ``pythonpath = ["src"]``) without needing an editable install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vibeflow import config as config_mod  # noqa: E402
from vibeflow.audio import AudioError, Recorder  # noqa: E402
from vibeflow.transcriber import Transcriber, TranscriptionError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VibeFlow macOS mic/engine proof")
    parser.add_argument(
        "--seconds", type=float, default=3.0, help="how long to record (default 3)"
    )
    parser.add_argument(
        "--model", default="base", help="whisper size: tiny|base|small (default base)"
    )
    parser.add_argument(
        "--device", default="default", help="input device name/substring/index"
    )
    parser.add_argument(
        "--list-devices", action="store_true", help="list input devices and exit"
    )
    args = parser.parse_args(argv)

    if args.list_devices:
        from vibeflow.audio import list_input_devices

        print("Input devices:")
        for line in list_input_devices():
            print("  " + line)
        return 0

    recorder = Recorder(sample_rate=16000, input_device=args.device)
    transcriber = Transcriber(
        size=args.model,
        language="en",
        models_dir=str(config_mod.models_dir()),
    )

    # Load the model first so the recording window isn't spent downloading.
    print(f"Loading '{args.model}' model (first run downloads it)…", flush=True)
    try:
        transcriber.load()
    except TranscriptionError as exc:
        print(f"\nERROR loading the speech engine: {exc}", file=sys.stderr)
        return 2
    print(f"Model ready on {transcriber._resolved[0]}/{transcriber._resolved[1]}.")

    print(f"\nRecording {args.seconds:g}s — speak now…", flush=True)
    try:
        recorder.start()
    except AudioError as exc:
        print(f"\nERROR opening the microphone: {exc}", file=sys.stderr)
        print(
            "On macOS, grant Microphone access in "
            "System Settings → Privacy & Security → Microphone.",
            file=sys.stderr,
        )
        return 2

    try:
        time.sleep(max(0.1, args.seconds))
    finally:
        audio = recorder.stop()

    seconds = recorder.duration(audio)
    print(f"Captured {seconds:.2f}s of audio. Transcribing…", flush=True)
    if seconds < 0.2:
        print(
            "\n(No audio captured — check the mic permission / input device with "
            "`--list-devices`.)"
        )
        return 1

    try:
        text = transcriber.transcribe(audio)
    except TranscriptionError as exc:
        print(f"\nERROR transcribing: {exc}", file=sys.stderr)
        return 2

    text = (text or "").strip()
    print("\n" + "=" * 60)
    print("Transcript:")
    print(text if text else "(no speech detected)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
