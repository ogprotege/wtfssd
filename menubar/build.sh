#!/bin/sh
# Build WTFSSDMonitor.app from the SwiftPM package.
set -eu
cd "$(dirname "$0")"

APP="build/WTFSSDMonitor.app"
REPO_ROOT="$(cd .. && pwd)"

swift build -c release

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/wtfssd-menubar "$APP/Contents/MacOS/"
sed "s|REPO_ROOT_PLACEHOLDER|$REPO_ROOT|" Info.plist > "$APP/Contents/Info.plist"
codesign --sign - --force "$APP" 2>/dev/null || true

echo "built $APP"
echo "run:  open $APP"
