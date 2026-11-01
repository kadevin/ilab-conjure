# Dependency security notes

Assessment date: 2026-10-31. A package advisory match is not evidence that an
application path is exploitable. These notes describe the source and build
configuration, not the contents of previously published or installed packages.

## Image and TLS dependencies

- Pillow is pinned to **13.0.0**. PNG EXIF parsing is relevant to untrusted
  reference images and generated images: thumbnail creation calls
  `ImageOps.exif_transpose`, which reads EXIF metadata. The fixed quadratic
  parsing issue is [GHSA-g4qv-2jxx-769h](https://github.com/python-pillow/Pillow/security/advisories/GHSA-g4qv-2jxx-769h).
  Raster validation now limits parser selection to GIF, JPEG, PNG and WebP at
  `Image.open`, while retaining byte, dimension, pixel and frame budgets.
  Existing local reference conversion, including MPO to PNG, remains available.
- The [JPEG draft/scaling advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782)
  requires scaling before loading. Current thumbnail functions load through
  `exif_transpose` before calling `thumbnail`; this assessment does not claim
  that path directly triggers that issue. Format restriction alone would not
  fix a JPEG decoder issue, so upgrading Pillow remains necessary.
- certifi is a direct application dependency pinned to **2026.10.23**, including
  wheel/editable installations as well as the runtime lock, after the
  [emSign trust-store correction](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
  The application uses it for default outbound HTTPS verification. Explicit
  `SSL_CERT_FILE` / `SSL_CERT_DIR` settings retain their existing behavior;
  owners of custom CA bundles must maintain those bundles separately.
  Certificate and hostname verification are not disabled.
  Portable startup scripts only supply a default CA when neither explicit SSL
  setting is present; an explicit Requests CA bundle is also preserved.

## Runtime and build baseline

- macOS standard/portable and Windows x64 standard/portable build scripts default
  to **Python 3.14.10** and **pip 26.2.2**, following the
  [Python security notice](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576).
  Python 3.11.18 is source-only and cannot replace 3.11.9 in installer URLs.
  The selected macOS universal installer and Windows x64 embedded ZIP are real
  python.org artifacts. Scripts verify their pinned SHA256 before extraction,
  including cached downloads. Overriding the version requires a verified hash
  (`--python-sha256` on macOS, `-PythonSha256` on Windows).
- pip is bootstrapped from a pinned, hash-checked wheel, not a mutable bootstrap
  script. Runtime packages continue to require hashes. macOS launch/update paths
  use the framework's `Versions/Current` link instead of a hard-coded minor.
- Source startup, CLI, WebUI server and native launcher paths check the Python
  security baseline before starting work, including Python 3.15.2 for the 3.15
  branch. Manual WebUI and CLI startup also reject missing, prerelease or older
  Pillow/certifi versions below the security floors (13.0.0 and 2026.10.19).
  These minimum checks do not replace the exact installation lock.
  Pip is checked only when dependencies
  need installation; final native packages can still run with pip removed.
  Checks report the required version without changing global environments.
  Windows builders stop if the dependency inventory, application import probe or
  runtime cleanup fails. Windows CI exercises those failure paths with synthetic
  commands, independently of a full native package build.
  All four native builders check the selected interpreter before bootstrapping
  pip, including version overrides. After cleanup, they check the security
  floors and exact locked dependencies/imports again without requiring pip.
- The audited PEP 517 backend is **setuptools 84.2.1**. Its
  [legacy Windows wheel-installation advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
  is fixed in 84.1.0. This project uses PEP 517, not the affected legacy
  `setup_requires` / `install_as_egg` path; the update is defensive build hygiene.
- Frontend CI uses **Node 22.23.4**, from the
  [October security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases).
  Node builds/tests frontend assets; the WebUI server is Python. The project
  version file does not upgrade an existing developer's global Node executable.

## Rust assessment and deferred warnings

`wayland-scanner` was updated to **0.31.11**, bringing `quick-xml` to **0.41.0**
and addressing [RUSTSEC-2026-0194](https://rustsec.org/advisories/RUSTSEC-2026-0194.html)
and [RUSTSEC-2026-0195](https://rustsec.org/advisories/RUSTSEC-2026-0195.html).
The scanner processes protocol XML during Linux Wayland compilation; it does
not parse uploaded images or provider responses. Its current parser uses
`Reader`, not the `NsReader` API described by the second advisory.

The following warnings remain visible to cargo-audit; no blanket ignores were
added:

- **glib 0.18.5**, [RUSTSEC-2024-0429](https://rustsec.org/advisories/RUSTSEC-2024-0429.html):
  a real unsound iterator API, fixed in glib 0.20. It is pulled through the Linux
  GTK/libappindicator tray stack. No application call to the affected iterator
  was found, and it is absent from the checked macOS arm64 and Windows x64
  dependency trees. This is not a proof of safety for all Linux transitive
  calls. Updating it requires a compatible GTK/tray migration and Linux testing;
  that migration is deferred rather than forcing mismatched GTK crate versions.
- **proc-macro-error**, [RUSTSEC-2024-0370](https://rustsec.org/advisories/RUSTSEC-2024-0370.html),
  and **ttf-parser**, [RUSTSEC-2026-0192](https://rustsec.org/advisories/RUSTSEC-2026-0192.html):
  unmaintained-package notices, not demonstrated application vulnerabilities.
  Replacement depends on the upstream Linux GUI dependency graph.

The release workflow currently packages macOS arm64/x64 and Windows x64, not
Linux. A future Linux release must revisit these warnings. A clean vulnerability
count does not mean that warnings or untested platform behavior are resolved.

## Verification boundaries

Use synthetic images and an isolated local TLS server for regression checks.
Verify allowed uploads, EXIF orientation, thumbnails, format conversion, output
downloads, custom CA acceptance, rejection of unknown CAs/wrong hostnames, and
proxy routing. Do not run resource-exhaustion payloads against a user's service.

Before release, build and launch every supported native package, exercise its
update path, and inspect the actual bundled Python/Pillow/certifi versions and
build manifests. The existing cleanup step removes pip and other build-only
tools from final native packages; verify that removal as well.
Lock audits, wheel availability and source-level packaging checks cannot replace
those package-level checks. Existing running processes must be restarted with
updated dependencies and a patched interpreter to receive the runtime fixes.
