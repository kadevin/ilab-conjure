# Security Policy

## Local and trusted LAN access

iLab CONJURE listens on loopback by default. The optional **Allow LAN access**
setting binds to all IPv4 interfaces after the WebUI service restarts. Turning it
off also takes effect after a restart; saving alone does not disconnect clients.

LAN access has no login or user roles. Anyone who can reach the listener shares
the same workspace and can generate images using the host's configured channels,
view tasks and images, change settings, and delete shared data. Use it only on a
trusted network. The setting does not limit access to a particular subnet; do not
port-forward or expose this unauthenticated listener to the public internet.

Same-origin write checks, request size limits, and file/parameter validation still
apply. LAN URLs use HTTP; browser features that require a secure context, such as
system notifications, may be unavailable. Address copying falls back to selecting
the address for manual copying when the browser cannot copy it automatically.

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
