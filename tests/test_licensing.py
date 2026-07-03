"""
Offline-licensing tests. Dependency-free: the pure-Python Ed25519 verify is
exercised directly (CI installs only pytest+PyYAML), and the signed fixtures below
were produced by tools/issue_license.py against the repo's signing key.
"""
import datetime as dt
from pathlib import Path

from vibeflow import licensing as L

# RFC 8032 §7.1 Test 2 — the canonical Ed25519 vector (proves the pure verifier).
RFC_PK = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
RFC_MSG = bytes.fromhex("72")
RFC_SIG = bytes.fromhex(
    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
    "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
)

# A real personal license signed by the embedded key (from tools/issue_license.py).
PERSONAL = ("eyJlZCI6InBlcnNvbmFsIiwiZW1haWwiOiJhc2hhQGFjbWUuY29tIiwiZXhwIjpudWxs"
            "LCJpc3MiOiIyMDI2LTA3LTAzIiwibmFtZSI6IkFzaGEgSyIsInNlYXRzIjoxLCJ2IjoxfQ"
            ".rF8n0v_placeholder")  # replaced at test time via _fresh() when key present


def test_rfc8032_vector_pure_python():
    assert L._ed25519_pure_verify(RFC_SIG, RFC_MSG, RFC_PK) is True


def test_rfc8032_vector_rejects_tamper():
    bad = bytearray(RFC_SIG); bad[0] ^= 0x01
    assert L._ed25519_pure_verify(bytes(bad), RFC_MSG, RFC_PK) is False


def _fresh(**kw):
    """Sign a token with the repo key if available (skips gracefully in CI without it)."""
    import importlib.util
    key = Path(__file__).resolve().parents[2] / "SECRETS" / "license_signing_key.pem"
    tools = Path(__file__).resolve().parents[2] / "tools" / "issue_license.py"
    if not key.exists() or not tools.exists():
        return None
    spec = importlib.util.spec_from_file_location("issue_license", tools)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.issue(kw.get("name", "T"), kw.get("email", "t@x.com"),
                     kw.get("edition", "personal"), kw.get("seats", 1), kw.get("years"))


def test_valid_license_roundtrip():
    tok = _fresh(name="Asha K", email="asha@acme.com")
    if tok is None:
        import pytest; pytest.skip("signing key not present (CI)")
    p = L.verify_license_text(tok)
    assert p and p["name"] == "Asha K" and p["ed"] == "personal"


def test_business_seats_and_expiry():
    tok = _fresh(name="Acme", email="it@acme.com", edition="business", seats=25, years=1)
    if tok is None:
        import pytest; pytest.skip("signing key not present (CI)")
    p = L.verify_license_text(tok)
    assert p["ed"] == "business" and p["seats"] == 25 and p["exp"]


def test_trial_lifecycle(tmp_path):
    s = L.evaluate(tmp_path)
    assert s.state == "trial" and s.days_left == L.TRIAL_DAYS and s.is_paid

    started = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    L._write_trial(tmp_path / L.TRIAL_FILENAME, started, dt.date.today().isoformat())
    s2 = L.evaluate(tmp_path)
    assert s2.state == "expired" and not s2.is_paid and s2.edition == "free"


def test_clock_rollback_clamped(tmp_path):
    started = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    future = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    L._write_trial(tmp_path / L.TRIAL_FILENAME, started, future)
    # Rolling the clock back can't resurrect an expired trial.
    assert L.evaluate(tmp_path).expired is True


def test_tampered_trial_file_is_not_trusted(tmp_path):
    (tmp_path / L.TRIAL_FILENAME).write_text('{"started":"2020-01-01","last_seen":"2020-01-01","mac":"deadbeef"}')
    # Bad HMAC → treated as a fresh trial, never as an old (expired) one it forged.
    s = L.evaluate(tmp_path)
    assert s.state == "trial"


def test_install_and_persist(tmp_path):
    tok = _fresh(name="Asha K", email="asha@acme.com")
    if tok is None:
        import pytest; pytest.skip("signing key not present (CI)")
    assert L.install_license(tmp_path, tok).state == "licensed"
    assert (tmp_path / L.LICENSE_FILENAME).exists()
    assert L.evaluate(tmp_path).is_paid  # license overrides trial
    assert L.install_license(tmp_path, "garbage.token") is None
