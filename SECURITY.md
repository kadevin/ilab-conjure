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
apply. Host names are limited to loopback, the server's interface addresses,
its system hostname/local name, and an explicitly configured listener host.
Arbitrary DNS aliases are not accepted. LAN URLs use HTTP; browser features that require a secure context, such as
system notifications, may be unavailable. Address copying falls back to selecting
the address for manual copying when the browser cannot copy it automatically.

## Secrets and local data

Generated image URLs are resolved and checked before download and on every
redirect. Indirect assets must use public addresses; assets on the exact origin
of a user-configured local provider remain supported. Connections use the checked
IP while retaining the original HTTP Host and TLS hostname. Credentials are only
retried on the configured provider origin and never follow a cross-origin redirect.

Each image redirect re-evaluates the configured proxy and system `NO_PROXY` rules
using the original hostname and effective port. Temporary image DNS failures retry only resolution.
Exhausted DNS or connection attempts, unsafe asset URLs, and invalid image
responses stop the task instead of automatically resubmitting generation.
A user-requested retry remains available after a failed task.

Downloaded images must pass full raster decoding and byte, dimension, pixel and
frame limits. If a CDN mislabels one supported raster type as another (for
example, WebP as PNG), the decoded format takes precedence and determines the
saved extension. HTML and invalid image bytes are rejected; explicit MIME
declarations inside provider JSON or data URLs remain strictly checked.

SVG is accepted only for an Images API request explicitly selecting SVG. It
must be bounded UTF-8 static SVG: no scripts, event handlers, foreign objects,
embedded raster images, external resources, DTDs or entities. Media responses
use a sandboxed CSP. Raster inputs remain raster-only; SVG output does not
relax upload validation. History imports validate SVG outputs under the same
static-image rules.

Read/write failures, HTTP 5xx responses and total timeouts after a generation
request may have been sent never replay that request automatically. Connection
retries are limited to failures known to occur before sending. Image decoding,
download limits and local output write failures also stop automatic generation
retries. Batch responses retain successful images and record failed image slots
separately, including empty image fields. On a total timeout, validated partial
images received before the deadline are retained; late results and results from
a user-cancelled request are discarded. A failed local write cannot guarantee
recovery of image bytes that were never saved.

T8 asynchronous task IDs and their output slots are checkpointed in local task
metadata before polling. Progress updates preserve these checkpoints atomically.
Poll retries and user-requested retries resume those tasks, including after a
restart, and download only the pending output slots. Explicit provider changes
or a confirmed failed remote task can start a new generation.

The optional Fake-IP DNS compatibility setting applies only to indirect image
assets whose system DNS answers are entirely in `198.18.0.0/15`. It queries
Cloudflare DNS over HTTPS for the hostname only, then applies the same public
address validation and pinned connections on every redirect. No API credentials,
prompts, or complete image URLs are sent to the DNS resolver. The setting is off
by default and does not change system or LAN DNS.

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
