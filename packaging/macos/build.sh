#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/macos"
MANIFEST_PATH="$DIST_DIR/manifest.txt"

cd "$REPO_ROOT"

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  python3.12 -m pytest
  python3.12 -m ruff format --check src tests
  python3.12 -m ruff check src tests
  python3.12 tools/check_chinese_project_text.py
fi

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "缺少 PyInstaller，请先在 macOS 构建环境安装 pyinstaller。" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"

pyinstaller \
  --noconfirm \
  --clean \
  --name bagholder \
  --distpath "$DIST_DIR" \
  --workpath "$REPO_ROOT/build/macos" \
  --specpath "$REPO_ROOT/build/macos-spec" \
  -m stock_agent.bootstrap.entrypoints

find "$DIST_DIR" -type f | sed "s#^$REPO_ROOT/##" > "$MANIFEST_PATH"
python3.12 tools/packaging_guard.py "$MANIFEST_PATH"
echo "macOS 安装包构建完成：$DIST_DIR"
