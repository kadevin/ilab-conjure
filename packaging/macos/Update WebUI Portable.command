#!/bin/zsh
set -e
set -o pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

REPO_SLUG="kadevin/ilab-conjure"
LATEST_UPDATE_MANIFEST_URL="https://github.com/kadevin/ilab-conjure/releases/latest/download/latest.json"
BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${BUNDLE_DIR}/data"
VERSION_FILE="${BUNDLE_DIR}/portable-version.txt"
UPDATE_NOTICE_FILE="${DATA_DIR}/update-notice.json"
POST_UPDATE_ONBOARDING_FILE="${DATA_DIR}/post-update-onboarding.json"
PYTHON_BIN="${BUNDLE_DIR}/python/Python.framework/Versions/3.11/bin/python3"
LAUNCHER_BIN="${BUNDLE_DIR}/Start iLab GPT CONJURE.app/Contents/MacOS/ilab-conjure-launcher"
HOST_ARCH="$(uname -m)"
TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
TEMP_ROOT="${TMPDIR:-/tmp}/ilab-gpt-conjure-update-${TIMESTAMP}"
EXTRACT_DIR="${TEMP_ROOT}/extract"
BACKUP_DIR="${BUNDLE_DIR}/.backup/update-${TIMESTAMP}"
AUTO_INSTALL=0
RESTART_LAUNCHER=0

for arg in "$@"; do
  case "$arg" in
    --auto|--assume-yes)
      AUTO_INSTALL=1
      ;;
    --restart-launcher)
      RESTART_LAUNCHER=1
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

pause_to_close() {
  if [[ "$AUTO_INSTALL" == "1" ]]; then
    return 0
  fi
  read -r "?Press Enter to close..."
}

pause_to_continue() {
  if [[ "$AUTO_INSTALL" == "1" ]]; then
    echo "Auto install requested; continuing without prompt."
    return 0
  fi
  read -r "?Press Enter to continue..."
}

if [[ "$AUTO_INSTALL" == "1" ]]; then
  mkdir -p "$DATA_DIR"
  exec >> "${DATA_DIR}/portable-updater.log" 2>&1
  echo ""
  echo "==== $(date -u +"%Y-%m-%dT%H:%M:%SZ") auto update ===="
fi

case "$HOST_ARCH" in
  arm64)
    PACKAGE_ARCH="arm64"
    PLATFORM_KEY="darwin-aarch64"
    ;;
  x86_64)
    PACKAGE_ARCH="x64"
    PLATFORM_KEY="darwin-x86_64"
    ;;
  *)
    echo "Unsupported macOS architecture: ${HOST_ARCH}" >&2
    pause_to_close
    exit 1
    ;;
esac
ASSET_PREFIX="ilab-gpt-conjure_macos_portable_${PACKAGE_ARCH}_"

# Do not move data. The data directory contains user settings, API keys, gallery
# assets, inputs, outputs, history, task databases, and logs.
REPLACE_ITEMS=(
  "app"
  "python"
  "Start iLab GPT CONJURE.app"
  "Start WebUI Portable.command"
  "Update WebUI Portable.command"
  "README-portable.md"
  "THIRD_PARTY_NOTICES.md"
  "LICENSE"
  "python-requirements.lock.txt"
  "portable-version.txt"
)

step() {
  echo ""
  echo "==> $1"
}

cleanup() {
  rm -rf "$TEMP_ROOT" 2>/dev/null || true
}

assert_replace_item_name() {
  case "$1" in
    /*|..|../*|*/../*|*/..)
      return 1
      ;;
  esac
  return 0
}

assert_in_bundle() {
  "$PYTHON_BIN" - "$BUNDLE_DIR" "$1" <<'PY'
import os
import sys

root = os.path.realpath(sys.argv[1])
target = os.path.realpath(sys.argv[2])
if target != root and not target.startswith(root + os.sep):
    raise SystemExit(1)
PY
}

restore_backup() {
  if [[ ! -d "$BACKUP_DIR" ]]; then
    return 0
  fi
  echo "Restoring previous files from ${BACKUP_DIR}"
  local item backup_item target_item
  for item in "${REPLACE_ITEMS[@]}"; do
    assert_replace_item_name "$item" || continue
    backup_item="${BACKUP_DIR}/${item}"
    target_item="${BUNDLE_DIR}/${item}"
    assert_in_bundle "$backup_item" || continue
    assert_in_bundle "$target_item" || continue
    if [[ ! -e "$backup_item" ]]; then
      continue
    fi
    rm -rf "$target_item"
    mkdir -p "$(dirname "$target_item")"
    mv "$backup_item" "$target_item"
  done
}

fail_update() {
  echo ""
  echo "Update failed: $1" >&2
  restore_backup || true
  cleanup
  pause_to_close
  exit 1
}

trap cleanup EXIT

current_portable_version() {
  if [[ ! -f "$VERSION_FILE" ]]; then
    return 0
  fi
  head -n 1 "$VERSION_FILE" | tr -d '[:space:]'
}

clear_update_notice() {
  rm -f "$UPDATE_NOTICE_FILE" 2>/dev/null || true
}

write_post_update_onboarding_notice() {
  "$PYTHON_BIN" - "$POST_UPDATE_ONBOARDING_FILE" "$1" "$2" <<'PY' || true
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


def normalize(value):
    match = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    if not match:
        return None
    return ".".join(match.groups())


path = Path(sys.argv[1])
from_version = normalize(sys.argv[2])
to_version = normalize(sys.argv[3])
if not to_version:
    raise SystemExit(0)
release_url = f"https://github.com/kadevin/ilab-conjure/releases/tag/v{to_version}"
payload = {
    "kind": "portable_standard_app_transition",
    "to_version": to_version,
    "to_version_label": f"v{to_version}",
    "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "dismissed": False,
    "release_url": release_url,
    "standard_download_url": release_url,
}
if from_version:
    payload["from_version"] = from_version
    payload["from_version_label"] = f"v{from_version}"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

version_is_current_or_newer() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import re
import sys


def parse(value):
    match = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


current = parse(sys.argv[1])
latest = parse(sys.argv[2])
print("1" if current and latest and current >= latest else "0")
PY
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Portable Python was not found at ${PYTHON_BIN}." >&2
  pause_to_close
  exit 1
fi

echo "iLab CONJURE portable updater"
echo "Bundle: ${BUNDLE_DIR}"
echo "Data:   ${DATA_DIR}"

mkdir -p "$DATA_DIR" "$EXTRACT_DIR"

step "Checking latest release"
MANIFEST_JSON="${TEMP_ROOT}/latest.json"
curl -fsSL \
  -H "Accept: application/json" \
  -H "User-Agent: ilab-gpt-conjure-portable-updater" \
  "$LATEST_UPDATE_MANIFEST_URL" \
  -o "$MANIFEST_JSON" || fail_update "Could not fetch update manifest."

if [[ ! -x "$LAUNCHER_BIN" ]]; then
  fail_update "Could not verify update manifest because the tray launcher was not found."
fi
"$LAUNCHER_BIN" --verify-update-manifest "$MANIFEST_JSON" \
  || fail_update "Update manifest signature verification failed."

ASSET_INFO="$("$PYTHON_BIN" - "$MANIFEST_JSON" "$PLATFORM_KEY" "$ASSET_PREFIX" <<'PY'
import json
import sys

manifest_path, platform_key, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
with open(manifest_path, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)

platform = manifest.get("platforms", {}).get(platform_key)
if not isinstance(platform, dict):
    raise SystemExit(f"missing update manifest platform entry: {platform_key}")

asset_name = str(platform.get("asset") or "")
url = str(platform.get("url") or "")
sha256 = str(platform.get("sha256") or "").lower()
if not asset_name.startswith(prefix) or not asset_name.endswith(".zip"):
    raise SystemExit(f"manifest asset does not match expected macOS portable package: {asset_name}")
if not url:
    raise SystemExit(f"manifest platform {platform_key} does not include url")
if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
    raise SystemExit(f"manifest platform {platform_key} does not include a valid sha256")

print(manifest.get("version", ""))
print(asset_name)
print(url)
print(sha256)
PY
)" || fail_update "Could not resolve update manifest asset."

RELEASE_TAG="$(printf "%s\n" "$ASSET_INFO" | sed -n '1p')"
ZIP_NAME="$(printf "%s\n" "$ASSET_INFO" | sed -n '2p')"
ZIP_URL="$(printf "%s\n" "$ASSET_INFO" | sed -n '3p')"
EXPECTED_HASH="$(printf "%s\n" "$ASSET_INFO" | sed -n '4p')"

CURRENT_VERSION="$(current_portable_version)"
if [[ "$(version_is_current_or_newer "$CURRENT_VERSION" "$RELEASE_TAG")" == "1" ]]; then
  clear_update_notice
  echo ""
  echo "Already up to date (${RELEASE_TAG})."
  echo "No app files were changed."
  pause_to_close
  exit 0
fi

echo ""
if [[ -n "$CURRENT_VERSION" ]]; then
  echo "Current version: ${CURRENT_VERSION}"
else
  echo "Current version: unknown"
fi
echo "Latest version:  ${RELEASE_TAG}"
echo "Release asset:   ${ZIP_NAME}"
echo "Manifest SHA256: ${EXPECTED_HASH}"
echo "Download URL:    ${ZIP_URL}"
echo ""
echo "Quit the menu bar launcher and close any WebUI server window before updating."
pause_to_continue

ZIP_PATH="${TEMP_ROOT}/${ZIP_NAME}"

step "Downloading ${RELEASE_TAG}"
curl -fL --show-error --output "$ZIP_PATH" "$ZIP_URL" || fail_update "Could not download update zip."

step "Verifying SHA256"
ACTUAL_HASH="$(shasum -a 256 "$ZIP_PATH" | awk '{print tolower($1)}')"
if [[ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]]; then
  fail_update "SHA256 mismatch. Expected ${EXPECTED_HASH} but got ${ACTUAL_HASH}."
fi

step "Extracting update package"
ditto -x -k "$ZIP_PATH" "$EXTRACT_DIR" || fail_update "Could not extract update zip."
NEW_ROOT="$EXTRACT_DIR"
if [[ ! -d "${NEW_ROOT}/app" ]]; then
  candidate_count=0
  while IFS= read -r candidate; do
    NEW_ROOT="$candidate"
    candidate_count=$((candidate_count + 1))
  done < <(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d -exec test -d "{}/app" \; -print)
  if [[ "$candidate_count" -ne 1 ]]; then
    fail_update "Could not identify extracted portable bundle root."
  fi
fi

for required_item in "app" "python" "Start iLab GPT CONJURE.app" "portable-version.txt"; do
  if [[ ! -e "${NEW_ROOT}/${required_item}" ]]; then
    fail_update "Downloaded package is missing required item: ${required_item}"
  fi
done

mkdir -p "$BACKUP_DIR"

if [[ "$AUTO_INSTALL" == "1" ]]; then
  echo "Waiting for the current launcher process to exit before replacing files."
  sleep 2
fi

step "Backing up current app files"
for item in "${REPLACE_ITEMS[@]}"; do
  assert_replace_item_name "$item" || fail_update "Refusing unsafe replace item: ${item}"
  current_item="${BUNDLE_DIR}/${item}"
  backup_item="${BACKUP_DIR}/${item}"
  if [[ ! -e "$current_item" ]]; then
    continue
  fi
  assert_in_bundle "$current_item" || fail_update "Refusing to modify path outside bundle: ${current_item}"
  assert_in_bundle "$backup_item" || fail_update "Refusing to modify path outside bundle: ${backup_item}"
  mkdir -p "$(dirname "$backup_item")"
  mv "$current_item" "$backup_item" || fail_update "Could not back up ${item}."
done

step "Installing updated app files"
for item in "${REPLACE_ITEMS[@]}"; do
  assert_replace_item_name "$item" || fail_update "Refusing unsafe replace item: ${item}"
  source_item="${NEW_ROOT}/${item}"
  target_item="${BUNDLE_DIR}/${item}"
  if [[ ! -e "$source_item" ]]; then
    continue
  fi
  assert_in_bundle "$target_item" || fail_update "Refusing to modify path outside bundle: ${target_item}"
  mkdir -p "$(dirname "$target_item")"
  cp -R "$source_item" "$target_item" || fail_update "Could not install ${item}."
done

chmod +x "${BUNDLE_DIR}/Start WebUI Portable.command" 2>/dev/null || true
chmod +x "${BUNDLE_DIR}/Update WebUI Portable.command" 2>/dev/null || true
xattr -dr com.apple.quarantine "$BUNDLE_DIR" 2>/dev/null || true
clear_update_notice
write_post_update_onboarding_notice "$CURRENT_VERSION" "$RELEASE_TAG"

step "Update complete"
echo "Updated to ${RELEASE_TAG}."
echo "Data was preserved at ${DATA_DIR}"
echo "Backup was saved at ${BACKUP_DIR}"
if [[ "$RESTART_LAUNCHER" == "1" && -d "${BUNDLE_DIR}/Start iLab GPT CONJURE.app" ]]; then
  echo "Restarting Start iLab GPT CONJURE.app."
  open "${BUNDLE_DIR}/Start iLab GPT CONJURE.app" || true
else
  echo "Start the WebUI again with Start iLab GPT CONJURE.app."
fi
pause_to_close
