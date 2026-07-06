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

# ── Lemon Squeezy per-device activation (one-time online, then fully offline) ──
# Model: 14-day full trial → whole app LOCKS → $10 one-time unlocks THIS device for
# life. Each key has activation_limit=1 in LS, so a 2nd device needs its own key.
# Everything below is PUBLIC (no secrets) — the license key the customer pastes is
# the only credential, and LS's activate endpoint needs no API token.
LS_ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
LS_VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"
LS_PRODUCT_ID = 0  # TODO: set to your LS product id (keys for other products are rejected)
LS_CHECKOUT_URL = "https://vibeflow.lemonsqueezy.com/buy/REPLACE-ME"  # TODO: your $10 buy link
ACTIVATION_FILENAME = "activation.json"
_ACT_HMAC_KEY = b"vibeflow-activation-v1"


class ActivationError(Exception):
    """Raised with a user-facing message when activation can't complete."""


# ─────────────────────────── status model ────────────────────────────
@dataclass(frozen=True)
class LicenseStatus:
    state: str            # "licensed" | "trial" | "locked"
    edition: str = "lifetime"
    name: Optional[str] = None
    email: Optional[str] = None
    seats: int = 1
    days_left: Optional[int] = None
    expired: bool = False

    @property
    def tool_unlocked(self) -> bool:
        """The whole app is usable (a valid device activation, or still in trial)."""
        return self.state in ("licensed", "trial")

    # Back-compat alias — older call sites gated AI on this.
    @property
    def is_paid(self) -> bool:
        return self.tool_unlocked

    @property
    def badge(self) -> str:
        if self.state == "licensed":
            return "VibeFlow — Licensed (this device)"
        if self.state == "trial":
            n = self.days_left or 0
            return f"Trial — {n} day{'s' if n != 1 else ''} left"
        return "Trial ended — activate to unlock"


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


# ─────────────────── device fingerprint + LS activation ───────────────────
def device_fingerprint() -> str:
    """A stable, per-device id — hashed so we never store the raw hardware id.
    Windows: MachineGuid; macOS: IOPlatformUUID; fallback: the MAC address."""
    raw = ""
    try:
        import sys
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True, timeout=5)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    raw = line.split('"')[-2]
                    break
    except Exception:
        raw = ""
    if not raw:
        import uuid
        raw = f"node:{uuid.getnode()}"
    return hashlib.sha256(f"vibeflow|{raw}".encode()).hexdigest()[:32]


def _ls_post(url: str, payload: dict, timeout: int = 15) -> dict:
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _activation_mac(key: str, instance_id: str, device: str) -> str:
    return hmac.new(_ACT_HMAC_KEY, f"{key}|{instance_id}|{device}".encode(),
                    hashlib.sha256).hexdigest()


def _read_activation(path: Path) -> Optional[dict]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if hmac.compare_digest(d.get("mac", ""),
                               _activation_mac(d["key"], d["instance_id"], d["device"])):
            return d
    except Exception:
        pass
    return None


def _write_activation(path: Path, key: str, instance_id: str, device: str,
                      product_id) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "key": key, "instance_id": instance_id, "device": device,
        "product_id": product_id, "activated_at": _today().isoformat(),
        "mac": _activation_mac(key, instance_id, device),
    }), encoding="utf-8")


def activate_license(config_dir: Path, key: str) -> LicenseStatus:
    """One-time online activation of a Lemon Squeezy key on THIS device. Persists a
    device-bound record so the app runs offline forever after. Raises
    ActivationError (user-facing message) on any failure."""
    key = (key or "").strip()
    if not key:
        raise ActivationError("Enter your license key.")
    device = device_fingerprint()
    try:
        resp = _ls_post(LS_ACTIVATE_URL,
                        {"license_key": key, "instance_name": f"VibeFlow {device[:8]}"})
    except Exception:
        raise ActivationError(
            "Couldn't reach the license server. Check your internet connection and try again.")

    if not resp.get("activated"):
        msg = resp.get("error") or "This license key could not be activated."
        if "activation limit" in msg.lower():
            msg = ("This key is already active on another device. Each VibeFlow license "
                   "is for one device — buy another to use it here.")
        elif "not found" in msg.lower():
            msg = "That license key wasn't recognized. Check for typos and try again."
        raise ActivationError(msg)

    meta = resp.get("meta") or {}
    if LS_PRODUCT_ID and int(meta.get("product_id", 0) or 0) != int(LS_PRODUCT_ID):
        raise ActivationError("That key isn't a VibeFlow license.")
    instance_id = (resp.get("instance") or {}).get("id") or ""
    _write_activation(config_dir / ACTIVATION_FILENAME, key, instance_id, device,
                      meta.get("product_id"))
    return LicenseStatus(state="licensed", edition="lifetime")


def evaluate(config_dir: Path) -> LicenseStatus:
    """Single entry point: licensed (activated on THIS device) → trial → locked."""
    # A device activation is only valid on the machine it was made on: a copied
    # activation.json fails the device check → locked. LS also caps the key at 1
    # device server-side, so the key can't be re-activated elsewhere either.
    act = _read_activation(config_dir / ACTIVATION_FILENAME)
    if act and hmac.compare_digest(str(act.get("device", "")), device_fingerprint()):
        return LicenseStatus(state="licensed", edition="lifetime")

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
        started = last_seen = today
        _write_trial(trial, started, last_seen)
        used = 0

    left = TRIAL_DAYS - used
    if left >= 0:
        return LicenseStatus(state="trial", edition="trial", days_left=left)
    return LicenseStatus(state="locked", expired=True)


def install_license(config_dir: Path, text: str) -> Optional[LicenseStatus]:
    """Validate & persist a pasted/loaded license. Returns new status or None if invalid."""
    payload = verify_license_text(text)
    if not payload:
        return None
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / LICENSE_FILENAME).write_text(text.strip(), encoding="utf-8")
    return _status_from_payload(payload)
