# VibeFlow Desktop — Offline Licensing

VibeFlow desktop is **100% offline by design** (the compliance/governance wedge). Its
licensing is offline too: a license is a small **Ed25519-signed token** the app verifies
against an **embedded public key** — no server call, works with Wi-Fi off, air-gap safe.

## How it works

- **Keys.** One Ed25519 keypair. The **private** key lives only in `SECRETS/license_signing_key.pem`
  (never in any repo, never shipped). The **public** key is embedded in `licensing.py`
  (`LICENSE_PUBLIC_KEY_B64`). Only the private key can mint a valid token; anyone can verify.
- **Token.** `b64url(payload).b64url(signature)`. Payload: `{v,name,email,ed,seats,exp,iss}`.
- **Verification** (`licensing.py`) uses `cryptography` when available and falls back to a
  vendored pure-Python Ed25519 verify, so the app and CI need **no extra dependency**. Proven
  against the RFC 8032 test vector in `tests/test_licensing.py`.
- **Trial.** First run stamps `config_dir/trial.json` (HMAC'd, clock-rollback-clamped). Fully
  featured for 14 days, then → **Free** mode.
- **Free mode.** Local voice-to-text stays free **forever**. Only **AI formatting** (the local
  Ollama pass) and business features lock. This keeps the free tier genuinely useful and the
  upgrade honest.
- **UI.** Tray ▸ *License · <status>* opens `--license` (a standalone Tk window) to paste/open a
  key or buy. The running app hot-reloads a newly-activated license within ~1s (watched in the
  clipboard loop).

## Editions

| Edition | Token | Unlocks | Price (planned) |
|---|---|---|---|
| Personal | `ed:personal`, `exp:null` (perpetual) | AI formatting, all personal features | **$59 one-time** per major version |
| Business | `ed:business`, `seats:N`, `exp:+1yr` (support window) | Everything + seat licensing, priority support, deployment/GPO, shared vocab files | **$49–79 / seat / year**, min 10 |
| Lifetime (early-bird) | `ed:personal`, `exp:null` | Everything, first 200 buyers | **$149** (validated demand: superwhisper did exactly this) |

## Issuing a license

**Day-1 (manual, zero-risk — how superwhisper started):** when Paddle emails you a paid order, run:

```bash
# personal, perpetual
python tools/issue_license.py --name "Asha K" --email asha@acme.com --edition personal
# business, 25 seats, 1-year support window
python tools/issue_license.py --name "Acme Corp" --email it@acme.com --edition business --seats 25 --years 1
```

Copy the printed token, paste it into the buyer's confirmation email. Done. (`cryptography` is
required to *issue* — `pip install cryptography` — but NOT to run the app.)

**Later (automated):** a webhook auto-issues on payment. Provider recommendation: **Paddle**
(merchant-of-record: handles global VAT/GST + tax-compliant invoices corporate procurement
accepts, supports India-based individual founders, 5% + $0.50). India-native runner-up:
**Dodo Payments** (4% + $0.40, native license-key generation). Flow:

1. Buyer pays via Paddle Checkout (pass `name`/`email`/`edition`/`seats` in `custom_data`).
2. Paddle sends a signed `transaction.completed` webhook to your endpoint (a small Vercel
   function; put the Ed25519 private key in a Vercel env var, NOT in git).
3. The endpoint verifies Paddle's signature, calls the same `issue()` logic, emails the token.

Don't automate until manual issuance becomes a chore — first ~50 sales by hand is fine and
lets you talk to every early customer.

## Packaging notes

- `licensing.py` and `license_window.py` are picked up automatically by PyInstaller's
  `--collect-submodules vibeflow`; no spec change needed, no new runtime dependency.
- **Uninstaller/updater must never delete `config_dir/license.key`** — verify `[UninstallDelete]`
  in `installer/vibeflow.iss` excludes it (updates already preserve the config dir).
- Version source of truth is `src/vibeflow/__init__.py __version__` (bump in lockstep with the
  Inno Setup `#define MyAppVersion`). `pyproject.toml`'s version is stale.
- This work is on branch `feature/offline-licensing` off `main` (Windows). To bring it to the
  **macos** branch: cherry-pick `licensing.py`, `license_window.py`, `tests/`, `tools/`, then
  add the ~20-line hookup in `platform_mac/menubar.py` (`_build_menu` + startup eval + AI gate)
  mirroring the `app.py` changes.

## Before selling: make the repo private

The desktop repo is currently **public with a free installer link** — so today it literally is
a free tool. Before charging: make `vibeflow` private (or source-available with a commercial
license), and gate release binaries. The license check ships in the binary regardless, but a
public repo invites trivial patch-out.
