"""
VibeFlow licensing — fully offline, air-gap friendly, zero hard dependencies.

A license is a signed token: b64url(json_payload) + "." + b64url(ed25519_sig).
The app ships ONLY the public key and verifies with no network access — the point
for compliance/governance buyers. There is no phone-home, ever.

Verification uses `cryptography` when present (fast path, bundled in the packaged
app) and falls back to a vendored pure-Python Ed25519 verify so this module has NO
import-time third-party dependency — tests and CI run without extra installs.

Payload: v, name, email, ed("personal"|"business"), seats, exp(ISO|null), iss(ISO).

Editions & modes:
  licensed  → paid features on (AI formatting, business tools)
  trial     → 14 days, fully featured
  free      → after trial/expiry: local voice-to-text stays free forever; AI locks
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Embedded Ed25519 PUBLIC key (raw, base64). Private key lives only in SECRETS/.
LICENSE_PUBLIC_KEY_B64 = "Z/gHlCh0UoyLZSamzhs2SgwlauVkIfNLsZWBv5NJ3TM="

TRIAL_DAYS = 14
LICENSE_FILENAME = "license.key"
TRIAL_FILENAME = "trial.json"
# App-embedded key for the trial-file HMAC (tamper/rollback friction, not secrecy).
_TRIAL_HMAC_KEY = b"vibeflow-trial-v1"


# ─────────────────────────── status model ────────────────────────────
@dataclass(frozen=True)
class LicenseStatus:
    state: str            # "licensed" | "trial" | "expired" | "free"
    edition: str          # "personal" | "business" | "free"
    name: Optional[str] = None
    email: Optional[str] = None
    seats: int = 1
    days_left: Optional[int] = None
    expired: bool = False

    @property
    def is_paid(self) -> bool:
        """Paid features (AI formatting, business tools) unlocked?"""
        return self.state in ("licensed", "trial")

    @property
    def badge(self) -> str:
        if self.state == "licensed":
            base = f"VibeFlow {self.edition.title()}"
            return base + (f" · {self.seats} seats" if self.edition == "business" else "")
        if self.state == "trial":
            n = self.days_left or 0
            return f"Trial — {n} day{'s' if n != 1 else ''} left"
        if self.state == "expired":
            return "Trial ended · Free mode"
        return "Free"


# ─────────────────────────── ed25519 verify ──────────────────────────
def _verify_sig(message: bytes, signature: bytes, pub_raw: bytes) -> bool:
    # Fast path: cryptography (present in the packaged app).
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            Ed25519PublicKey.from_public_bytes(pub_raw).verify(signature, message)
            return True
        except Exception:
            return False
    except Exception:
        pass
    # Fallback: vendored pure-Python RFC 8032 verify (slow, one-shot at startup — fine).
    try:
        return _ed25519_pure_verify(signature, message, pub_raw)
    except Exception:
        return False


def _ed25519_pure_verify(sig: bytes, msg: bytes, pk: bytes) -> bool:
    q = 2 ** 255 - 19
    L = 2 ** 252 + 27742317777372353535851937790883648493

    def H(m: bytes) -> bytes:
        return hashlib.sha512(m).digest()

    def inv(x): return pow(x, q - 2, q)
    d = (-121665 * inv(121666)) % q
    I = pow(2, (q - 1) // 4, q)

    def xrecover(y):
        xx = (y * y - 1) * inv(d * y * y + 1)
        x = pow(xx, (q + 3) // 8, q)
        if (x * x - xx) % q != 0:
            x = (x * I) % q
        if x % 2 != 0:
            x = q - x
        return x

    By = (4 * inv(5)) % q
    Bx = xrecover(By)
    B = (Bx % q, By % q)

    def edwards(P, Q):
        x1, y1 = P; x2, y2 = Q
        denom = d * x1 * x2 * y1 * y2
        x3 = (x1 * y2 + x2 * y1) * inv(1 + denom)
        y3 = (y1 * y2 + x1 * x2) * inv(1 - denom)
        return (x3 % q, y3 % q)

    def scalarmult(P, e):  # iterative (avoids recursion-limit issues)
        result = (0, 1)
        addend = P
        while e > 0:
            if e & 1:
                result = edwards(result, addend)
            addend = edwards(addend, addend)
            e >>= 1
        return result

    def bit(h, i): return (h[i // 8] >> (i % 8)) & 1

    def decodeint(s, nbits=256): return sum(2 ** i * bit(s, i) for i in range(0, nbits))

    def isoncurve(P):
        x, y = P
        return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0

    def decodepoint(s):
        y = sum(2 ** i * bit(s, i) for i in range(0, 255))
        x = xrecover(y)
        if x & 1 != bit(s, 255):
            x = q - x
        P = (x, y)
        if not isoncurve(P):
            raise ValueError("point off curve")
        return P

    def encodepoint(P):
        x, y = P
        bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
        return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))

    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        R = decodepoint(sig[:32])   # a malformed/off-curve point == invalid signature
        A = decodepoint(pk)
    except Exception:
        return False
    S = decodeint(sig[32:])
    if S >= L:
        return False
    h = decodeint(H(encodepoint(R) + pk + msg), 512)  # full 512-bit reduction
    return scalarmult(B, S) == edwards(R, scalarmult(A, h))


# ─────────────────────────── token / eval ────────────────────────────
def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _today() -> _dt.date:
    return _dt.date.today()


def verify_license_text(text: str) -> Optional[dict]:
    """Return the payload dict iff the token is authentically signed, else None."""
    try:
        token = text.strip().replace("\n", "").replace("\r", "").replace(" ", "")
        payload_b64, sig_b64 = token.split(".", 1)
        pub = base64.b64decode(LICENSE_PUBLIC_KEY_B64)
        if not _verify_sig(payload_b64.encode("ascii"), _b64url_decode(sig_b64), pub):
            return None
        return json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None


def _status_from_payload(p: dict) -> LicenseStatus:
    edition = p.get("ed", "personal")
    exp = p.get("exp")
    days_left = None
    if exp:
        try:
            end = _dt.date.fromisoformat(exp)
            days_left = (end - _today()).days
            if days_left < 0:
                return LicenseStatus(state="expired", edition="free",
                                     name=p.get("name"), email=p.get("email"), expired=True)
        except ValueError:
            pass
    return LicenseStatus(state="licensed", edition=edition, name=p.get("name"),
                         email=p.get("email"), seats=int(p.get("seats", 1)), days_left=days_left)


def _trial_mac(started: str, last_seen: str) -> str:
    return hmac.new(_TRIAL_HMAC_KEY, f"{started}|{last_seen}".encode(), hashlib.sha256).hexdigest()


def _read_trial(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if hmac.compare_digest(data.get("mac", ""), _trial_mac(data["started"], data["last_seen"])):
            return data
    except Exception:
        pass
    return None


def _write_trial(path: Path, started: str, last_seen: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"started": started, "last_seen": last_seen,
                                "mac": _trial_mac(started, last_seen)}), encoding="utf-8")


def evaluate(config_dir: Path) -> LicenseStatus:
    """Single entry point: read license/trial state from the config dir."""
    lic = config_dir / LICENSE_FILENAME
    if lic.exists():
        payload = verify_license_text(lic.read_text(encoding="utf-8"))
        if payload:
            return _status_from_payload(payload)
        return LicenseStatus(state="free", edition="free")  # tampered file → free, not trial

    trial = config_dir / TRIAL_FILENAME
    today = _today().isoformat()
    rec = _read_trial(trial)
    if rec:
        started = rec["started"]
        # Clock-rollback clamp: "now" can never precede the last run we recorded.
        last_seen = max(rec["last_seen"], today)
        _write_trial(trial, started, last_seen)
        used = (_dt.date.fromisoformat(last_seen) - _dt.date.fromisoformat(started)).days
    else:
        # Fresh (or tampered) trial file → start now.
        started = last_seen = today
        _write_trial(trial, started, last_seen)
        used = 0

    left = TRIAL_DAYS - used
    if left >= 0:
        return LicenseStatus(state="trial", edition="personal", days_left=left)
    return LicenseStatus(state="expired", edition="free", expired=True)


def install_license(config_dir: Path, text: str) -> Optional[LicenseStatus]:
    """Validate & persist a pasted/loaded license. Returns new status or None if invalid."""
    payload = verify_license_text(text)
    if not payload:
        return None
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / LICENSE_FILENAME).write_text(text.strip(), encoding="utf-8")
    return _status_from_payload(payload)
