#!/bin/zsh
set -e
set -o pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

REPO_SLUG="kadevin/ilab-gpt-conjure"
LATEST_RELEASE_URL="https://api.github.com/repos/kadevin/ilab-gpt-conjure/releases/latest"
BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${BUNDLE_DIR}/data"
VERSION_FILE="${BUNDLE_DIR}/portable-version.txt"
PYTHON_BIN="${BUNDLE_DIR}/python/Python.framework/Versions/3.11/bin/python3"
HOST_ARCH="$(uname -m)"
TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
TEMP_ROOT="${TMPDIR:-/tmp}/ilab-gpt-conjure-update-${TIMESTAMP}"
EXTRACT_DIR="${TEMP_ROOT}/extract"
BACKUP_DIR="${BUNDLE_DIR}/.backup/update-${TIMESTAMP}"

case "$HOST_ARCH" in
  arm64)
    PACKAGE_ARCH="arm64"
    ;;
  x86_64)
    PACKAGE_ARCH="x64"
    ;;
  *)
    echo "Unsupported macOS architecture: ${HOST_ARCH}" >&2
    read -r "?Press Enter to close..."
    exit 1
    ;;
esac
ASSET_PREFIX="ilab-gpt-conjure_macos_portable_${PACKAGE_ARCH}_"

# Do not move data. The data directory contains user settings, API keys, gallery
# assets, inputs, outputs, history, task databases, and logs.
REPLACE_ITEMS=(
  "app"
  "python"
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

restore_backup() {
  if [[ ! -d "$BACKUP_DIR" ]]; then
    return 0
  fi
  echo "Restoring previous files from ${BACKUP_DIR}"
  local item backup_item target_item
  for item in "${REPLACE_ITEMS[@]}"; do
    backup_item="${BACKUP_DIR}/${item}"
    target_item="${BUNDLE_DIR}/${item}"
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
  read -r "?Press Enter to close..."
  exit 1
}

trap cleanup EXIT

current_portable_version() {
  if [[ ! -f "$VERSION_FILE" ]]; then
    return 0
  fi
  head -n 1 "$VERSION_FILE" | tr -d '[:space:]'
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
  read -r "?Press Enter to close..."
  exit 1
fi

echo "iLab GPT Conjure portable updater"
echo "Bundle: ${BUNDLE_DIR}"
echo "Data:   ${DATA_DIR}"

mkdir -p "$DATA_DIR" "$EXTRACT_DIR"

step "Checking latest release"
RELEASE_JSON="${TEMP_ROOT}/release.json"
curl -fsSL \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "User-Agent: ilab-gpt-conjure-portable-updater" \
  "$LATEST_RELEASE_URL" \
  -o "$RELEASE_JSON" || fail_update "Could not fetch latest release metadata."

ASSET_INFO="$("$PYTHON_BIN" - "$RELEASE_JSON" "$ASSET_PREFIX" "$PACKAGE_ARCH" <<'PY'
import json
import sys

release_path, prefix, arch = sys.argv[1], sys.argv[2], sys.argv[3]
with open(release_path, "r", encoding="utf-8") as handle:
    release = json.load(handle)

zip_asset = None
for asset in release.get("assets", []):
    name = asset.get("name", "")
    if name.startswith(prefix) and name.endswith(".zip"):
        zip_asset = asset
        break

if not zip_asset:
    raise SystemExit(f"missing macOS {arch} portable asset in {release.get('tag_name', 'latest release')}")

hash_name = f"{zip_asset['name']}.sha256.txt"
hash_asset = None
for asset in release.get("assets", []):
    if asset.get("name") == hash_name:
        hash_asset = asset
        break

if not hash_asset:
    raise SystemExit(f"missing SHA256 file for {zip_asset['name']}")

print(release.get("tag_name", ""))
print(zip_asset["name"])
print(zip_asset["browser_download_url"])
print(hash_asset["name"])
print(hash_asset["browser_download_url"])
PY
)" || fail_update "Could not resolve release asset."

RELEASE_TAG="$(printf "%s\n" "$ASSET_INFO" | sed -n '1p')"
ZIP_NAME="$(printf "%s\n" "$ASSET_INFO" | sed -n '2p')"
ZIP_URL="$(printf "%s\n" "$ASSET_INFO" | sed -n '3p')"
HASH_NAME="$(printf "%s\n" "$ASSET_INFO" | sed -n '4p')"
HASH_URL="$(printf "%s\n" "$ASSET_INFO" | sed -n '5p')"

CURRENT_VERSION="$(current_portable_version)"
if [[ "$(version_is_current_or_newer "$CURRENT_VERSION" "$RELEASE_TAG")" == "1" ]]; then
  echo ""
  echo "Already up to date (${RELEASE_TAG})."
  echo "No app files were changed."
  read -r "?Press Enter to close..."
  exit 0
fi

echo ""
if [[ -n "$CURRENT_VERSION" ]]; then
  echo "Current version: ${CURRENT_VERSION}"
else
  echo "Current version: unknown"
fi
echo "Latest version:  ${RELEASE_TAG}"
echo ""
echo "Close the WebUI server window before updating."
read -r "?Press Enter to continue..."

ZIP_PATH="${TEMP_ROOT}/${ZIP_NAME}"
HASH_PATH="${TEMP_ROOT}/${HASH_NAME}"

step "Downloading ${RELEASE_TAG}"
curl -fL --show-error --output "$ZIP_PATH" "$ZIP_URL" || fail_update "Could not download update zip."
curl -fL --show-error --output "$HASH_PATH" "$HASH_URL" || fail_update "Could not download SHA256 file."

step "Verifying SHA256"
EXPECTED_HASH="$(awk '{print tolower($1); exit}' "$HASH_PATH")"
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

for required_item in "app" "python" "Start WebUI Portable.command" "portable-version.txt"; do
  if [[ ! -e "${NEW_ROOT}/${required_item}" ]]; then
    fail_update "Downloaded package is missing required item: ${required_item}"
  fi
done

mkdir -p "$BACKUP_DIR"

step "Backing up current app files"
for item in "${REPLACE_ITEMS[@]}"; do
  current_item="${BUNDLE_DIR}/${item}"
  backup_item="${BACKUP_DIR}/${item}"
  if [[ ! -e "$current_item" ]]; then
    continue
  fi
  mkdir -p "$(dirname "$backup_item")"
  mv "$current_item" "$backup_item" || fail_update "Could not back up ${item}."
done

step "Installing updated app files"
for item in "${REPLACE_ITEMS[@]}"; do
  source_item="${NEW_ROOT}/${item}"
  target_item="${BUNDLE_DIR}/${item}"
  if [[ ! -e "$source_item" ]]; then
    continue
  fi
  mkdir -p "$(dirname "$target_item")"
  cp -R "$source_item" "$target_item" || fail_update "Could not install ${item}."
done

chmod +x "${BUNDLE_DIR}/Start WebUI Portable.command" 2>/dev/null || true
chmod +x "${BUNDLE_DIR}/Update WebUI Portable.command" 2>/dev/null || true
xattr -dr com.apple.quarantine "$BUNDLE_DIR" 2>/dev/null || true

step "Update complete"
echo "Updated to ${RELEASE_TAG}."
echo "Data was preserved at ${DATA_DIR}"
echo "Backup was saved at ${BACKUP_DIR}"
echo "Start the WebUI again with Start WebUI Portable.command."
read -r "?Press Enter to close..."
