#!/usr/bin/env bash
set -euo pipefail

VERSION=""
OUTPUT_DIR=".dist"
PYTHON_VERSION="3.11.9"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version)
      VERSION="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --python-version)
      PYTHON_VERSION="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

PROJECT_NAME="ilab-conjure"
APP_BUNDLE_NAME="iLab GPT CONJURE.app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_MINOR="${PYTHON_VERSION%.*}"
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
  arm64)
    PACKAGE_ARCH="arm64"
    ;;
  x86_64)
    PACKAGE_ARCH="x64"
    ;;
  *)
    echo "Unsupported macOS architecture: ${HOST_ARCH}" >&2
    exit 1
    ;;
esac

if [[ "$OUTPUT_DIR" = /* ]]; then
  BUILD_ROOT="$OUTPUT_DIR"
else
  BUILD_ROOT="${REPO_ROOT}/${OUTPUT_DIR}"
fi

if [[ -z "$VERSION" ]]; then
  if VERSION="$(git -C "$REPO_ROOT" describe --tags --always --dirty 2>/dev/null)"; then
    :
  else
    VERSION="$(date +"%Y%m%d-%H%M%S")"
  fi
fi

SAFE_VERSION="$(printf "%s" "$VERSION" | sed -E 's/[^A-Za-z0-9_.-]+/-/g; s/^-+//; s/-+$//')"
if [[ -z "$SAFE_VERSION" ]]; then
  SAFE_VERSION="dev"
fi

APP_BUNDLE_ROOT="${BUILD_ROOT}/${APP_BUNDLE_NAME}"
APP_BUNDLE_CONTENTS="${APP_BUNDLE_ROOT}/Contents"
APP_BUNDLE_MACOS="${APP_BUNDLE_CONTENTS}/MacOS"
APP_BUNDLE_RESOURCES="${APP_BUNDLE_CONTENTS}/Resources"
APP_BUNDLE_HELPERS="${APP_BUNDLE_CONTENTS}/Helpers"
APP_RESOURCES_APP_PATH="Contents/Resources/app"
APP_RESOURCES_PYTHON_PATH="Contents/Resources/python"
APP_DIR="${APP_BUNDLE_RESOURCES}/app"
PYTHON_DIR="${APP_BUNDLE_RESOURCES}/python"
PYTHON_FRAMEWORK="${PYTHON_DIR}/Python.framework"
CACHE_DIR="${BUILD_ROOT}/_cache"
DMG_ROOT="${BUILD_ROOT}/create-dmg-root"
DMG_NAME="iLab-GPT-CONJURE-macos-${PACKAGE_ARCH}-${SAFE_VERSION}.dmg"
DMG_PATH="${BUILD_ROOT}/${DMG_NAME}"
HASH_PATH="${DMG_PATH}.sha256.txt"
MANIFEST_PATH="${BUILD_ROOT}/macos-app-build.json"

PYTHON_PKG="python-${PYTHON_VERSION}-macos11.pkg"
PYTHON_PKG_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_PKG}"

APP_ITEMS=(
  "codex_image"
  "launcher"
  "assets"
  "requirements-webui.txt"
  "package.json"
  "package-lock.json"
  "tsconfig.webui.json"
  "scripts/build-webui-css.mjs"
  "pyproject.toml"
  "README.md"
  "README.zh-CN.md"
  "LICENSE"
  "SECURITY.md"
  "CONTRIBUTING.md"
)

copy_app_item() {
  local relative="$1"
  local source="${REPO_ROOT}/${relative}"
  local target="${APP_DIR}/${relative}"
  if [[ ! -e "$source" ]]; then
    return
  fi
  mkdir -p "$(dirname "$target")"
  cp -R "$source" "$target"
}

remove_local_artifacts() {
  local root="$1"
  chflags -R nouchg,noschg,nohidden "$root" 2>/dev/null || true
  find "$root" \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name "target" \) -prune -exec rm -rf {} + 2>/dev/null || true
  find "$root" \( -name ".DS_Store" -o -name "*.pyc" -o -name "*.pyo" \) -type f -delete 2>/dev/null || true
}

remove_build_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    return
  fi
  remove_local_artifacts "$path"
  rm -rf "$path" 2>/dev/null || true
  if [[ -e "$path" ]]; then
    local stale_path="${path}.stale.$$"
    rm -rf "$stale_path" 2>/dev/null || true
    mv "$path" "$stale_path" 2>/dev/null || true
    if [[ -e "$path" ]]; then
      echo "Could not remove old build path: ${path}" >&2
      exit 1
    fi
    remove_local_artifacts "$stale_path"
    rm -rf "$stale_path" 2>/dev/null || true
  fi
}

relocate_python_framework() {
  local framework_root="$1"
  local python_minor="$2"
  local version_dir="${framework_root}/Versions/${python_minor}"
  local original_prefix="/Library/Frameworks/Python.framework/Versions/${python_minor}"
  local original="${original_prefix}/Python"
  local framework_binary="${version_dir}/Python"

  if [[ ! -x "$framework_binary" ]]; then
    echo "Python framework binary was not found at ${framework_binary}" >&2
    exit 1
  fi

  install_name_tool -id "@rpath/Python.framework/Versions/${python_minor}/Python" "$framework_binary"
  while IFS= read -r dylib; do
    install_name_tool -id "@rpath/Python.framework/Versions/${python_minor}/lib/$(basename "$dylib")" "$dylib" || true
  done < <(find "${version_dir}/lib" -maxdepth 1 -type f -name "*.dylib")

  while IFS= read -r file; do
    while IFS= read -r dependency; do
      if [[ -z "$dependency" ]]; then
        continue
      fi
      local replacement="@rpath/Python.framework/Versions/${python_minor}/${dependency#"${original_prefix}/"}"
      case "$dependency" in
        "$original")
          case "$file" in
            "${version_dir}/bin"/python*)
              replacement="@executable_path/../Python"
              ;;
            "${version_dir}/Resources/Python.app/Contents/MacOS/Python")
              replacement="@executable_path/../../../../Python"
              ;;
            *)
              replacement="@rpath/Python.framework/Versions/${python_minor}/Python"
              ;;
          esac
          ;;
        "${original_prefix}/lib/"*)
          local library_name
          library_name="$(basename "$dependency")"
          case "$file" in
            "${version_dir}/lib/python${python_minor}/lib-dynload/"*)
              replacement="@loader_path/../../${library_name}"
              ;;
            "${version_dir}/lib/"*)
              replacement="@loader_path/${library_name}"
              ;;
            *)
              replacement="@rpath/Python.framework/Versions/${python_minor}/lib/${library_name}"
              ;;
          esac
          ;;
      esac
      install_name_tool -change "$dependency" "$replacement" "$file" || true
    done < <(otool -L "$file" 2>/dev/null | awk '{print $1}' | grep "^${original_prefix}/" || true)
    codesign --force --sign - "$file" >/dev/null 2>&1 || true
  done < <(find "$version_dir" -type f -perm -111)

  codesign --force --sign - "$framework_binary" >/dev/null 2>&1 || true
}

create_macos_app_icon() {
  local source_svg="$1"
  local output_icns="$2"
  local work_dir="$3"
  local iconset_dir="${work_dir}/AppIcon.iconset"
  local source_png="${work_dir}/source.png"

  rm -rf "$work_dir"
  mkdir -p "$iconset_dir"
  sips -s format png -z 1024 1024 "$source_svg" --out "$source_png" >/dev/null

  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$source_png" --out "${iconset_dir}/icon_${size}x${size}.png" >/dev/null
    local retina_size=$((size * 2))
    sips -z "$retina_size" "$retina_size" "$source_png" --out "${iconset_dir}/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$iconset_dir" -o "$output_icns"
}

write_macos_app_plist() {
  local plist_path="$1"
  cat > "$plist_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>iLab CONJURE</string>
  <key>CFBundleExecutable</key>
  <string>ilab-conjure-launcher</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.ilab.gpt-conjure</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>iLab CONJURE</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>${SAFE_VERSION}</string>
  <key>CFBundleVersion</key>
  <string>${SAFE_VERSION}</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST
  plutil -lint "$plist_path" >/dev/null
}

mkdir -p "$BUILD_ROOT" "$CACHE_DIR"
remove_build_path "$APP_BUNDLE_ROOT"
remove_build_path "$DMG_ROOT"
rm -f "$DMG_PATH" "$HASH_PATH" "$MANIFEST_PATH"
mkdir -p "$APP_BUNDLE_MACOS" "$APP_BUNDLE_RESOURCES" "$APP_BUNDLE_HELPERS" "$APP_DIR" "$PYTHON_DIR"

for item in "${APP_ITEMS[@]}"; do
  copy_app_item "$item"
done

cp "${SCRIPT_DIR}/standard_webui_app.py" "${APP_DIR}/standard_webui_app.py"
cp "${SCRIPT_DIR}/README-app.md" "${APP_BUNDLE_RESOURCES}/README-app.md"
cp "${SCRIPT_DIR}/THIRD_PARTY_NOTICES.md" "${APP_BUNDLE_RESOURCES}/THIRD_PARTY_NOTICES.md"
if [[ -f "${APP_DIR}/LICENSE" ]]; then
  cp "${APP_DIR}/LICENSE" "${APP_BUNDLE_RESOURCES}/LICENSE"
fi
printf "%s\n" "$VERSION" > "${APP_BUNDLE_RESOURCES}/app-version.txt"
remove_local_artifacts "$APP_DIR"

PYTHON_PKG_PATH="${CACHE_DIR}/${PYTHON_PKG}"
if [[ ! -f "$PYTHON_PKG_PATH" ]]; then
  echo "Downloading ${PYTHON_PKG_URL}"
  curl -L --fail --show-error --output "$PYTHON_PKG_PATH" "$PYTHON_PKG_URL"
fi

EXPANDED_PKG="${CACHE_DIR}/python-${PYTHON_VERSION}-expanded"
rm -rf "$EXPANDED_PKG"
pkgutil --expand-full "$PYTHON_PKG_PATH" "$EXPANDED_PKG"

FRAMEWORK_PAYLOAD="${EXPANDED_PKG}/Python_Framework.pkg/Payload"
if [[ ! -d "${FRAMEWORK_PAYLOAD}/Versions/${PYTHON_MINOR}" ]]; then
  echo "Could not find Python framework payload in ${PYTHON_PKG_PATH}" >&2
  exit 1
fi

mkdir -p "$PYTHON_FRAMEWORK"
cp -R "${FRAMEWORK_PAYLOAD}/"* "$PYTHON_FRAMEWORK/"
relocate_python_framework "$PYTHON_FRAMEWORK" "$PYTHON_MINOR"

PYTHON_BIN="${PYTHON_FRAMEWORK}/Versions/${PYTHON_MINOR}/bin/python3"
"$PYTHON_BIN" -m ensurepip --upgrade
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install --target "${APP_DIR}/.deps" -r "${APP_DIR}/requirements-webui.txt"
if [[ ! -f "${APP_DIR}/.deps/certifi/cacert.pem" ]]; then
  echo "certifi CA bundle was not installed at ${APP_DIR}/.deps/certifi/cacert.pem" >&2
  exit 1
fi
PYTHONPATH="${APP_DIR}:${APP_DIR}/.deps" "$PYTHON_BIN" -m pip freeze | tee "${APP_BUNDLE_RESOURCES}/python-requirements.lock.txt" >/dev/null
APP_LAUNCHER_MODE=standard \
ILAB_CONJURE_APP_DIR="$APP_DIR" \
ILAB_CONJURE_DATA_DIR="${BUILD_ROOT}/_standard-data-probe" \
PYTHONPATH="${APP_DIR}:${APP_DIR}/.deps" \
  "$PYTHON_BIN" -c "import fastapi, uvicorn, multipart, httpx, PIL; import standard_webui_app; print('standard import ok')"
rm -rf "${BUILD_ROOT}/_standard-data-probe"

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo was not found. Install Rust toolchain before building the standard app launcher." >&2
  exit 1
fi
cargo build --manifest-path "${REPO_ROOT}/launcher/Cargo.toml" --release --locked --bin ilab-conjure-launcher --bin ilab-conjure-standard-updater
cp "${REPO_ROOT}/launcher/target/release/ilab-conjure-launcher" "${APP_BUNDLE_MACOS}/ilab-conjure-launcher"
chmod +x "${APP_BUNDLE_MACOS}/ilab-conjure-launcher"
cp "${REPO_ROOT}/launcher/target/release/ilab-conjure-standard-updater" "${APP_BUNDLE_HELPERS}/ilab-conjure-standard-updater"
chmod +x "${APP_BUNDLE_HELPERS}/ilab-conjure-standard-updater"
create_macos_app_icon "${REPO_ROOT}/launcher/assets/rabbit-logo.svg" "${APP_BUNDLE_RESOURCES}/AppIcon.icns" "${BUILD_ROOT}/_app-icon"
write_macos_app_plist "${APP_BUNDLE_CONTENTS}/Info.plist"
remove_local_artifacts "$APP_BUNDLE_ROOT"
codesign --force --deep --sign - "$APP_BUNDLE_ROOT" >/dev/null 2>&1 || true

mkdir -p "$DMG_ROOT"
cp -R "$APP_BUNDLE_ROOT" "$DMG_ROOT/${APP_BUNDLE_NAME}"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create -volname "iLab CONJURE" -srcfolder "$DMG_ROOT" -ov -format UDZO "$DMG_PATH"

SHA256="$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')"
printf "%s  %s\n" "$SHA256" "$(basename "$DMG_PATH")" > "$HASH_PATH"

cat > "$MANIFEST_PATH" <<JSON
{
  "project": "${PROJECT_NAME}",
  "version": "${VERSION}",
  "bundle": "iLab GPT CONJURE.app",
  "standard_updater": "Contents/Helpers/ilab-conjure-standard-updater",
  "dmg": "${DMG_PATH}",
  "sha256": "${SHA256}",
  "python_version": "${PYTHON_VERSION}",
  "architecture": "${PACKAGE_ARCH}",
  "data_dir": "~/Library/Application Support/iLab GPT CONJURE"
}
JSON

echo "Built ${DMG_PATH}"
echo "SHA256 ${SHA256}"
