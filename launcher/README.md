# iLab CONJURE Rust Launcher

This crate is the Rust system tray / macOS menu bar launcher for iLab CONJURE.

It starts the existing Python WebUI backend without a separate terminal window, opens the default browser at `http://127.0.0.1:8787/`, and keeps a tray/menu bar icon alive with these actions:

- Open WebUI
- Open Settings
- History Library
- Check for Updates
- About iLab CONJURE
- Restart WebUI Service
- Quit

The menu labels follow the WebUI language preference when it exists, otherwise
they fall back to the operating system UI language. The About action shows a
native dialog with the app version, open-source project URL, and an update
check button.

The update checker reads the published signed `latest.json` manifest from the
latest GitHub Release, verifies its Ed25519 signatures with the bundled public
key, and compares the local portable/standard/source version with the manifest
version. In a standard macOS app package that includes the helper, Install
Update copies the helper outside the running bundle, exits the launcher, then
downloads and SHA256-verifies the matching DMG, validates the bundle identity,
replaces the installed app with rollback protection, and relaunches it. Standard
macOS apps without the helper and Windows standard App ZIP packages fall back to
opening the installer download. In a portable package, Install Update starts the bundled updater in
automatic mode, exits the current launcher, lets the updater download and
SHA256-verify the matching zip, replace package-managed files while preserving
`data/`, and restart the launcher. Source checkouts do not have a package
updater, so they fall back to opening the release page.

The launcher does not replace the Python WebUI backend. It wraps startup,
process lifetime, browser opening, signed update checking, updater handoff, and
user-facing menu actions. Server logs are written to
`output/webui-outputs/webui-server.log` by default.

The source logo is `assets/rabbit-logo.svg`. The macOS app icon is generated
from this filled rabbit SVG during portable packaging. Windows builds embed
`assets/rabbit-logo.ico` into the launcher executable so File Explorer and
taskbar entries show the rabbit icon instead of the default executable icon.
Runtime tray/menu-bar drawing uses a small template RGBA rabbit icon generated
in Rust, so the executable does not need an SVG renderer.

The launcher also exposes `--verify-update-manifest <path>` for the updater
scripts. It parses the manifest and verifies the signature without starting the
WebUI or creating a tray icon.

## Development

```bash
cargo test
cargo run
```

On Windows the binary uses the GUI subsystem, so double-clicking it does not create a console window.
