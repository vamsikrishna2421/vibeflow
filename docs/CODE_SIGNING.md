# Code signing (removing the SmartScreen warning)

VibeFlow's installer and `VibeFlow.exe` are currently **unsigned**, so Windows
SmartScreen shows *"Unknown publisher"* and testers must click *More info → Run
anyway*. Signing removes that warning and builds reputation over time.

## What you need

An **Authenticode code-signing certificate** (`.pfx`). Options:

- **OV certificate** (~$200–400/yr from Sectigo, DigiCert, SSL.com, etc.).
  Cheaper, but SmartScreen reputation builds up gradually as more people install.
- **EV certificate** (~$300–600/yr, hardware token or cloud HSM). Gets
  instant SmartScreen trust, but requires a token/HSM (no plain `.pfx`).

For a beta, an OV cert is usually enough.

## How to sign during the build

Set two environment variables before building, then run the build as usual:

```powershell
$env:VIBEFLOW_PFX = "C:\path\to\codesign.pfx"
$env:VIBEFLOW_PFX_PASSWORD = "your-pfx-password"
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

`build_exe.ps1` signs `VibeFlow.exe` and `build_installer.ps1` signs
`VibeFlowSetup.exe` automatically when `VIBEFLOW_PFX` is set (using `signtool`
from the Windows SDK, with a SHA-256 timestamp). If `VIBEFLOW_PFX` is not set,
the build is simply left unsigned.

## Verify

```powershell
Get-AuthenticodeSignature .\release\installer\VibeFlowSetup.exe
```

`Status` should read **Valid**.
