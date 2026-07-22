# iLab CONJURE macOS Portable Package

This package is intended for macOS users who want to unzip and run the WebUI
without installing Python separately.

## How to use

1. Download the zip that matches your Mac:
   - `macos_portable_arm64` for Apple Silicon Macs.
   - `macos_portable_x64` for Intel Macs.
2. Extract the zip package into a normal user directory, for example
   `~/Applications/ilab-gpt-conjure`.
3. Double-click `Start iLab GPT CONJURE.app` for the menu bar launcher, or
   `Start WebUI Portable.command` for the legacy terminal launcher.
4. Open `http://127.0.0.1:8787/` if the browser does not open automatically.
5. Choose `Codex` if this machine has a local Codex / ChatGPT OAuth session, or
   configure an OpenAI-compatible API provider in the WebUI for the recommended
   stable integration path.

The Rust menu bar launcher starts the local WebUI server without a separate
terminal window, opens the browser, and keeps a rabbit icon in the macOS menu
bar. Its menu can open the WebUI, check published updates, show project info,
restart the service, or quit. It does not contact GitHub automatically; the
check action only runs when you choose it from the menu. It can start the
bundled updater after you confirm an available update. The updater downloads
and verifies the matching zip, preserves `data/`, replaces package-managed
files, and restarts the menu bar launcher. You can also quit the launcher and
run `Update WebUI Portable.command` manually.

This is an unsigned portable zip with an unsigned `.app` launcher. It is not
notarized and does not require an Apple Developer account to build. The launcher
tries to remove quarantine attributes from its own extracted folder before
starting the bundled Python framework. If macOS still blocks the package after
download, use one of these local actions:

- Right-click or Control-click `Start iLab GPT CONJURE.app`, choose Open, then
  confirm Open again in the macOS security prompt.
- Or remove quarantine from the extracted folder:

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# or:
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

## Directory layout

- `Start iLab GPT CONJURE.app`: menu bar launcher with the rabbit Finder icon.
- `Start WebUI Portable.command`: legacy one-click terminal launcher.
- `Update WebUI Portable.command`: one-click updater for the latest GitHub
  Release manifest entry matching this Mac architecture.
- `app/`: iLab CONJURE source code, prebuilt static WebUI assets,
  frontend package metadata/build config for source rebuilds, and installed
  WebUI Python dependencies under `app/.deps`.
- `python/`: bundled Python.org Python framework.
- `data/`: local settings, gallery files, inputs, outputs, queue database, and
  logs created while using the app.

The portable startup launcher does not run `npm install` or rebuild frontend
assets. Node.js is only needed if you intentionally edit TypeScript or CSS and
rebuild `app/codex_image/webui/static/app.js` from source.

## Security notes

Do not put API keys, OAuth tokens, private prompts, input images, outputs, task
databases, or logs into GitHub issues or public repositories.

OpenAI-compatible API mode is the recommended stable integration path. The
optional Codex / ChatGPT OAuth mode defaults to the Codex Image channel for
personal local workflows only; it can be switched to the Responses compatibility
channel in API settings, but it is not an officially recommended OpenAI API
integration path.

## Upgrading

Choose `Check for Updates` from the menu bar launcher. If a newer signed
release manifest is available, confirm `Install Update`; the launcher will hand
off to the bundled updater, quit itself, and let the updater replace package
files and restart the menu bar app.

You can also quit the menu bar launcher, close any WebUI server window, then
double-click `Update WebUI Portable.command` manually.
The updater reads the published signed `latest.json` manifest, verifies its
Ed25519 signature with the launcher public key, then prints the current version,
latest version, selected release asset, manifest SHA256, and download URL before
making changes. It downloads the latest portable package for your Mac
architecture from GitHub Releases, verifies the manifest SHA256, replaces only
the package-managed app, launcher, and bundled Python files inside this portable
folder, preserves the existing `data/` directory, and clears quarantine
attributes on the updated folder. A backup of replaced files is saved under
`.backup/`.

Do not move `data/` out of the package unless you are intentionally migrating
settings, gallery assets, history, outputs, and local task databases. For a
manual upgrade, extract the new package next to the old one and copy the old
`data/` directory into the new package.
