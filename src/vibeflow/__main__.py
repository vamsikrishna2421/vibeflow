"""Command-line entry point for VibeFlow.

Usage examples
--------------
    python -m vibeflow                 # start the tray app
    python -m vibeflow --doctor        # check the setup (great first step)
    python -m vibeflow --list-devices  # show microphones
    python -m vibeflow --print-config  # show effective settings
    python -m vibeflow --model small --mode push_to_talk
"""

from __future__ import annotations

import argparse
import sys

from . import __app_name__, __version__, config as config_mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vibeflow",
        description=f"{__app_name__} — offline voice-to-text dictation.",
    )
    p.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    p.add_argument("--config", metavar="PATH", help="Use a specific config file.")
    p.add_argument("--model", metavar="SIZE", help="Override model size (e.g. small).")
    p.add_argument(
        "--mode",
        choices=["toggle", "push_to_talk"],
        help="Override the trigger mode for this run.",
    )
    p.add_argument("--language", metavar="LANG", help="Override language (e.g. en, auto).")
    p.add_argument(
        "--doctor",
        action="store_true",
        help="Run a setup self-test and exit (no model download).",
    )
    p.add_argument(
        "--download-model",
        action="store_true",
        help="Download/prepare the speech model, then exit.",
    )
    p.add_argument(
        "--list-devices", action="store_true", help="List microphones and exit."
    )
    p.add_argument(
        "--print-config", action="store_true", help="Print effective settings and exit."
    )
    p.add_argument(
        "--vocab-manager",
        action="store_true",
        help="Open the interactive vocabulary manager window and exit.",
    )
    p.add_argument(
        "--persona-manager",
        action="store_true",
        help="Open the interactive Personalized-AI profile window and exit.",
    )
    p.add_argument(
        "--license",
        action="store_true",
        help="Open the license window (activate / manage your VibeFlow license) and exit.",
    )
    p.add_argument(
        "--models-manager",
        action="store_true",
        help="Open the AI model manager (remove models / free disk) and exit.",
    )
    p.add_argument(
        "--settings",
        action="store_true",
        help="Open the Settings window and exit.",
    )
    p.add_argument(
        "--update",
        action="store_true",
        help="Open the Updates window (check + install) and exit.",
    )
    p.add_argument(
        "--check-ai",
        action="store_true",
        help="Test the local-LLM (AI formatting) connection and exit.",
    )
    p.add_argument(
        "--setup-ai",
        metavar="TIER",
        nargs="?",
        const="fast",
        default=None,
        help="Managed AI setup: install Ollama + download a model tier "
        "(fast|balanced|best) + enable AI, then exit.",
    )
    return p


def _apply_overrides(cfg: config_mod.Config, args: argparse.Namespace) -> None:
    if args.model:
        cfg.set("model.size", args.model)
    if args.mode:
        cfg.set("hotkey.mode", args.mode)
    if args.language:
        cfg.set("model.language", args.language)


def _configure_console() -> None:
    """Set up logging and make stdout/stderr safe — including windowed
    (no-console) builds where they are ``None``. See :mod:`vibeflow.logsetup`."""
    from .logsetup import setup

    setup()


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    cfg = config_mod.load_config(args.config)
    _apply_overrides(cfg, args)

    if args.vocab_manager:
        from .vocab_window import run as run_vocab_manager

        return run_vocab_manager(str(config_mod.config_dir() / "vocabulary.json"))
    if args.persona_manager:
        from .persona_window import run as run_persona_manager

        return run_persona_manager(str(config_mod.config_dir() / "persona.json"))
    if args.license:
        from .license_window import run as run_license
        return run_license(args.config)
    if args.models_manager:
        from .models_window import run as run_models_manager

        return run_models_manager(args.config)
    if args.settings:
        from .settings_window import run as run_settings

        return run_settings(args.config)
    if args.update:
        from .update_window import run as run_update

        return run_update(args.config)
    if args.check_ai:
        return _check_ai(cfg)
    if args.setup_ai:
        return _setup_ai(cfg, args.setup_ai)
    if args.list_devices:
        return _list_devices()
    if args.print_config:
        return _print_config(cfg)
    if args.doctor:
        return _doctor(cfg)
    if args.download_model:
        return _download_model(cfg)

    return _run(cfg)


def _run(cfg: config_mod.Config) -> int:
    from .app import VibeFlowApp
    from .single_instance import SingleInstance, notify_already_running

    # Enforce a single running instance (fixes accidental double-launches).
    instance = SingleInstance()
    if not instance.acquire():
        notify_already_running()
        return 0

    try:
        VibeFlowApp(cfg).run()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        instance.release()
    return 0


def _check_ai(cfg: config_mod.Config) -> int:
    from .core import ai_format

    ok, message = ai_format.check(cfg)
    print(("OK: " if ok else "NOT READY: ") + message)
    return 0 if ok else 1


def _setup_ai(cfg: config_mod.Config, tier: str) -> int:
    from . import ai_setup

    model, size = ai_setup.MODEL_TIERS.get(tier, ai_setup.MODEL_TIERS["fast"])
    print(f"Setting up AI formatting: {model} ({size})...")
    ok, message = ai_setup.setup(model, progress=lambda m: print("  " + m))
    if ok:
        cfg.set("ai.enabled", True)
        cfg.set("ai.model", model)
        try:
            cfg.save()
        except Exception:
            pass
    print(("OK: " if ok else "FAILED: ") + message)
    return 0 if ok else 1


def _list_devices() -> int:
    from .audio import list_input_devices

    print("Available microphones (input devices):")
    for line in list_input_devices():
        print(f"  {line}")
    return 0


def _print_config(cfg: config_mod.Config) -> int:
    import json

    print(f"# config file: {cfg.path}")
    print(json.dumps(cfg.as_dict(), indent=2))
    return 0


def _download_model(cfg: config_mod.Config) -> int:
    from .transcriber import Transcriber, TranscriptionError

    size = cfg.get("model.size", "base")
    print(f"Preparing model '{size}' (first time may download a few hundred MB)...")
    t = Transcriber(
        size=size,
        language=cfg.get("model.language", "en"),
        device=cfg.get("model.device", "auto"),
        compute_type=cfg.get("model.compute_type", "auto"),
        models_dir=str(config_mod.models_dir()),
    )
    try:
        t.load()
    except TranscriptionError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 2
    print("Model ready. VibeFlow can now run fully offline.")
    return 0


def _doctor(cfg: config_mod.Config) -> int:
    print(f"{__app_name__} {__version__} - setup check\n")
    print(f"Python            : {sys.version.split()[0]} ({sys.platform})")
    print(f"Config file       : {cfg.path}")
    print(f"Models folder     : {config_mod.models_dir()}")

    from .transcriber import _resolve_device

    device, compute = _resolve_device(
        cfg.get("model.device", "auto"), cfg.get("model.compute_type", "auto")
    )
    print(f"Model             : {cfg.get('model.size')} on {device}/{compute}")
    if cfg.get("hotkey.mode") == "push_to_talk":
        print(f"Trigger           : hold '{cfg.get('hotkey.push_to_talk_key')}'")
    else:
        print(f"Trigger           : press '{cfg.get('hotkey.toggle_combo')}'")

    print("\nDependencies:")
    ok = True
    required = [
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("faster_whisper", "faster-whisper"),
        ("pynput", "pynput"),
        ("pyperclip", "pyperclip"),
        ("pystray", "pystray"),
        ("PIL", "Pillow"),
        ("yaml", "PyYAML"),
    ]
    if sys.platform == "win32":
        required.append(("comtypes", "comtypes"))
    for module, package in required:
        present = _can_import(module)
        ok = ok and present
        print(f"  [{'OK' if present else '--'}] {package}")

    print("\nMicrophones:")
    from .audio import list_input_devices

    for line in list_input_devices():
        print(f"  {line}")

    _mic_signal_test(cfg)

    print(
        "\nResult: "
        + (
            "All core dependencies present. Run 'python -m vibeflow' to start."
            if ok
            else "Some dependencies are missing — run the installer or "
            "'pip install -r requirements.txt'."
        )
    )
    return 0 if ok else 1


def _mic_signal_test(cfg: config_mod.Config) -> None:
    """Record ~1.5s and report whether the mic actually delivers sound.

    This catches the most confusing failure on a fresh machine: the mic stream
    opens fine but Windows feeds it silence (mic access blocked, muted, or the
    wrong default device), so dictation just says "no speech" with no clue why.
    """
    print("\nMicrophone signal test:")
    try:
        import time

        from .audio import Recorder, SILENCE_PEAK, peak_level

        rec = Recorder(
            sample_rate=int(cfg.get("audio.sample_rate", 16000)),
            input_device=cfg.get("audio.input_device", "default"),
        )
        print("  Recording 1.5s — please say a few words…")
        rec.start()
        time.sleep(1.5)
        audio = rec.stop()
    except Exception as exc:  # noqa: BLE001 - diagnostic, never fatal
        print(f"  (could not run the mic test: {exc})")
        return

    peak = peak_level(audio)
    secs = rec.duration(audio)
    if secs <= 0.0:
        print("  [--] No audio captured at all — the mic stream returned nothing.")
    elif peak < SILENCE_PEAK:
        print(f"  [--] SILENT — captured {secs:.1f}s but the level is ~0 (peak {peak:.5f}).")
        print("       The mic opened but delivered no sound. Most likely Windows is")
        print("       blocking mic access for desktop apps, the mic is muted, or the")
        print("       wrong input device is selected.")
        print("       Fix: Settings ▸ Privacy & security ▸ Microphone ▸ turn ON")
        print("       'Microphone access' AND 'Let desktop apps access your microphone';")
        print("       then Settings ▸ System ▸ Sound ▸ Input (right mic, not muted).")
    else:
        print(f"  [OK] Mic is producing audio (peak {peak:.3f} over {secs:.1f}s).")


def _can_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
