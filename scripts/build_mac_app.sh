#!/usr/bin/env bash
# =============================================================================
#  Build VibeFlow.app (unsigned dev bundle) with PyInstaller.
#
#  Output: release/VibeFlow.app — a menu-bar agent (no Dock icon). The speech
#  model is NOT bundled; it downloads on first run into ~/.config/VibeFlow/models
#  and then runs fully offline.
#
#  Unsigned: macOS Gatekeeper will block a double-click the first time. Open it
#  once via right-click → Open (or: xattr -dr com.apple.quarantine release/VibeFlow.app).
#  For distribution you need a Developer ID signature + notarization (see below).
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "No venv at .venv — create it and 'pip install -r requirements.txt' first." >&2
    exit 1
fi

echo "==> Ensuring build tool (PyInstaller) ..."
"$PY" -m pip install --upgrade "pyinstaller>=6" --quiet

# --- Generate the .icns app icon from the VibeFlow logo ----------------------
echo "==> Generating app icon (VibeFlow.icns) ..."
mkdir -p build
ICONSET="build/VibeFlow.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
"$PY" - "$ICONSET" <<PY
import sys
sys.path.insert(0, "$ROOT/src")
from vibeflow import icons
out = sys.argv[1]
# Apple's required iconset members: 16,32,128,256,512 each at 1x and 2x.
for size in (16, 32, 64, 128, 256, 512, 1024):
    img = icons.render_logo(size)
    if size in (16, 32, 128, 256, 512):
        img.save(f"{out}/icon_{size}x{size}.png")
    # @2x variants are the double-resolution of the next size down.
    half = size // 2
    if half in (16, 32, 128, 256, 512):
        img.save(f"{out}/icon_{half}x{half}@2x.png")
print("iconset written:", out)
PY
if command -v iconutil >/dev/null 2>&1; then
    iconutil -c icns "$ICONSET" -o build/VibeFlow.icns
    echo "    build/VibeFlow.icns"
else
    echo "    (iconutil not found — building without a custom icon)"
fi

# --- Build the .app ----------------------------------------------------------
echo "==> Building VibeFlow.app (this takes a few minutes) ..."
"$PY" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath release \
    --workpath build/pyinstaller \
    packaging/VibeFlow-mac.spec

APP="release/VibeFlow.app"
if [ ! -d "$APP" ]; then
    echo "Build failed — see the messages above." >&2
    exit 1
fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
echo ""
echo "Done (unsigned): $APP"

# --- Optional Developer ID signing ------------------------------------------
# If a dedicated build keychain with a Developer ID Application identity exists
# (set up once — see docs/MACOS_PORT.md / MACOS_INSTALL.md), install a SIGNED
# copy to ~/Applications. Signing gives the app a STABLE identity so macOS keeps
# its Accessibility/Microphone grants across rebuilds (no re-granting), and makes
# it notarization-ready. Without the keychain, this block is skipped.
SIGN_ID="${VIBEFLOW_SIGN_ID:-Developer ID Application: Scuts Technologies Private Limited (CJ8SV692GN)}"
BUILD_KC="$ROOT/build/signing/vibeflow-build.keychain-db"
BUILD_KC_PW="${VIBEFLOW_KC_PW:-vibeflow-build}"
ENTITLEMENTS="$ROOT/packaging/entitlements.plist"
DEST="$HOME/Applications/VibeFlow.app"

if [ -f "$BUILD_KC" ]; then
    echo "==> Signing with Developer ID and installing to ~/Applications ..."
    # Make sure the build keychain is unlocked and on the search list.
    security unlock-keychain -p "$BUILD_KC_PW" "$BUILD_KC" 2>/dev/null || true
    case "$(security list-keychains -d user)" in
        *vibeflow-build.keychain-db*) : ;;
        *) security list-keychains -d user -s "$BUILD_KC" \
               $(security list-keychains -d user | sed -e 's/"//g') ;;
    esac

    mkdir -p "$HOME/Applications"
    rm -rf "$DEST"
    ditto "$APP" "$DEST"
    xattr -cr "$DEST"   # strip any FinderInfo/quarantine before signing
    if codesign --deep --force --options runtime --timestamp \
            --entitlements "$ENTITLEMENTS" -s "$SIGN_ID" "$DEST" 2>/dev/null \
       && codesign --verify --strict "$DEST" 2>/dev/null; then
        echo "Done (signed): $DEST"

        # Notarize only when asked (it takes a few minutes + needs network).
        # Normal dev rebuilds stay fast & signed; set VIBEFLOW_NOTARIZE=1 for a
        # release build that anyone can run with no Gatekeeper warning.
        if [ "${VIBEFLOW_NOTARIZE:-0}" = "1" ]; then
            echo "==> Notarizing (this takes a few minutes) ..."
            ZIP="/tmp/vibeflow-notarize.zip"
            rm -f "$ZIP"
            ditto -c -k --keepParent "$DEST" "$ZIP"
            if xcrun notarytool submit "$ZIP" \
                   --keychain-profile "${VIBEFLOW_NOTARY_PROFILE:-vibeflow-notary}" \
                   --wait 2>&1 | tee /tmp/vibeflow-notarize.log | tail -3 \
               | grep -q "status: Accepted"; then
                xcrun stapler staple "$DEST" && echo "Notarized + stapled."
                # Refresh the shareable zip from the stapled app.
                rm -f "$HOME/Desktop/VibeFlow-mac.zip"
                ditto -c -k --keepParent "$DEST" "$HOME/Desktop/VibeFlow-mac.zip"
                echo "Shareable: ~/Desktop/VibeFlow-mac.zip"
            else
                echo "WARNING: notarization not Accepted — see /tmp/vibeflow-notarize.log" >&2
            fi
        fi
        echo "Launch it:  open \"$DEST\""
    else
        echo "WARNING: signing failed — use the unsigned $APP instead." >&2
        echo "Launch it:  open \"$APP\""
    fi
else
    echo "(no signing keychain found — skipping signing; using unsigned build)"
    echo "Launch it:  open \"$APP\""
fi
