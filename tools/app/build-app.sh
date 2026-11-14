#!/bin/zsh
# Builds the "Shielded Labs" app, runs its tests and installs it in ~/Applications.
#
# Usage: zsh tools/app/build-app.sh [--package] [--no-install] [--force]
#   --package     also write a zip to hand to someone else, in dist/ (or in $PACKAGE_DIR)
#   --no-install  build and test only; leave the installed app alone
#   --force       replace the installed app even if its code has not changed
set -euo pipefail

HERE="${0:A:h}"
FOLDER="${HERE:h:h}"
NAME="Shielded Labs"
INSTALLED="$HOME/Applications/$NAME.app"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

APP="$WORK/$NAME.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "Compiling..."
# One binary for each kind of Mac (Apple silicon and Intel), joined into one, so the app opens on both.
for ARCH in arm64 x86_64; do
  swiftc -swift-version 5 -O -target "$ARCH-apple-macosx13.0" -o "$WORK/board-$ARCH" "$HERE/main.swift" \
    -framework Cocoa -framework WebKit -framework Security
done
lipo -create "$WORK/board-arm64" "$WORK/board-x86_64" -output "$APP/Contents/MacOS/board"

echo "Running the tests..."
# The tests work on a scratch board with one sample item, never on a real one.
SCRATCH="$WORK/scratch"
mkdir -p "$SCRATCH/tools/app"
echo '{"me":"","items":[{"id":"p1","group":"Sample","item":"Sample item","openedOn":"2026-01-01","owner":"Ana"}],"meetings":[],"dates":[]}' > "$SCRATCH/board.json"
"$APP/Contents/MacOS/board" --selftest "$SCRATCH"

echo "Drawing the icon..."
swift "$HERE/icon.swift" "$HERE/shield.png" "$WORK/icon.png"
ICONSET="$WORK/icon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  double=$((size * 2))
  sips -z "$size" "$size" "$WORK/icon.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  sips -z "$double" "$double" "$WORK/icon.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>local.workstation.shielded-labs</string>
  <key>CFBundleExecutable</key><string>board</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

echo "Embedding the empty board..."
python3 "$FOLDER/tools/build.py" --empty "$APP/Contents/Resources/board.html"

codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "Note: the app was not signed (it still opens on this Mac)."

# macOS ties each Keychain secret to the signature of the app, and the signature changes with every
# install. So the installed app is replaced only when its code has changed. The page (board.html)
# is read from the data folder, so a change in the page alone needs no reinstall.
STAMP="$HERE/.installed.sha"
CURRENT="$(cat "$HERE/main.swift" "$HERE/icon.swift" "$HERE/shield.png" | shasum -a 256 | cut -d' ' -f1)"
mkdir -p "$HOME/Applications"
if [[ " $* " == *" --no-install "* ]]; then
  echo "App built and tested; nothing was installed (--no-install)."
elif [ -e "$INSTALLED" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$CURRENT" ] && [[ " $* " != *" --force "* ]]; then
  echo "Installed app kept (its code has not changed). To see a new page: View > Reload in the app."
else
  if [ -e "$INSTALLED" ]; then
    osascript -e "tell application \"$NAME\" to quit" >/dev/null 2>&1 || true
    rm -rf "$INSTALLED"
  fi
  cp -R "$APP" "$INSTALLED"
  echo "$CURRENT" > "$STAMP"
  echo "Installed at $INSTALLED (macOS may ask for the Keychain password once)"
fi

# With --package, also write the zip to share, after checking that it carries no personal data.
if [[ " $* " == *" --package "* ]]; then
  OUT="${PACKAGE_DIR:-$FOLDER/dist}"
  mkdir -p "$OUT"
  ZIP="$OUT/Shielded Labs Workstation.zip"
  OWNER=""
  [ -f "$FOLDER/board.json" ] && OWNER="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("me",""))' "$FOLDER/board.json")"
  for term in "$HOME" "$USER" "$OWNER"; do
    [ -z "$term" ] && continue
    if grep -r -l -a -F -- "$term" "$APP" >/dev/null 2>&1; then
      echo "STOPPED: the app contains \"$term\". Nothing was packaged." >&2
      grep -r -l -a -F -- "$term" "$APP" >&2
      exit 1
    fi
  done
  cp "$HERE/README.txt" "$WORK/READ ME.txt"
  rm -f "$ZIP"
  (cd "$WORK" && ditto -c -k --sequesterRsrc --keepParent "$NAME.app" "$WORK/app.zip" && mkdir package && cd package && ditto -x -k "$WORK/app.zip" . && cp "$WORK/READ ME.txt" . && ditto -c -k --sequesterRsrc . "$ZIP")
  echo "Package at $ZIP"
fi
