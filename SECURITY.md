# Security Policy

## Local-only assumptions

iLab CONJURE is designed for local personal workflows. Do not expose the
WebUI directly to the public internet unless you have reviewed and hardened the
deployment yourself.

## Secrets and local data

Do not publish OAuth tokens, API keys, account files, `.env` files, input images,
generated outputs, task metadata, SQLite databases, or debug logs.

Sensitive local paths include:

- `~/.codex/auth.json`
- `output/`
- `outputs/`
- `input/`
- `inputs/`

## Advanced local auth warning

The optional Codex / ChatGPT OAuth mode calls an internal ChatGPT backend
endpoint. It is not an officially recommended OpenAI API integration path and
may change or stop working without notice. Prefer OpenAI-compatible API mode for
stable integrations.

## Portable updater behavior

Portable startup launchers only start the local WebUI server and open the local
browser URL by default. They contact GitHub only when the user chooses the
update check action from the tray/menu-bar menu.

Standard app packages do not silently self-replace app files. Updater-enabled
macOS standard apps can perform a user-confirmed one-click replacement after
verifying the signed manifest and DMG SHA256; older macOS apps and Windows
standard ZIP packages open the matching download for manual replacement.

Portable update scripts can be started by the launcher after user confirmation,
or run manually from the extracted package. They fetch the published signed
`latest.json` update manifest and the matching portable zip, verify the Ed25519
manifest signature and manifest SHA256, preserve local `data/`, only replace
package-managed files inside the extracted portable folder, keep backups under
`.backup/`, and restart the launcher when started in automatic mode.

## Reporting issues

Please report security issues privately to the maintainer instead of opening a
public issue containing credentials, tokens, private prompts, or private images.
