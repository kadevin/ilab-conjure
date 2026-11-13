# Contributing

Thanks for your interest in improving iLab CONJURE.

Dependency updates use the hash-locked runtime and build-tool inputs. Use a
project-local environment with a security-supported Python patch release and
the Node version in `.node-version`; do not replace system runtimes:

```bash
pip-compile --generate-hashes --output-file=requirements-webui.txt --strip-extras pyproject.toml requirements-webui.in
pip-compile --allow-unsafe --generate-hashes --output-file=requirements-build.txt --strip-extras requirements-build.in
```

Restore the explicit `--require-hashes` directive after regeneration. Keep the
PEP 517 backend in `pyproject.toml` synchronized with `requirements-build.in`.
Audit both Python locks with `pip-audit --disable-pip --require-hashes -r FILE`:
these fully resolved locks must be checked even when packages are already
installed in the audit environment. Also audit the complete npm lock (including build dependencies),
and `launcher/Cargo.lock`. The dependency-audit workflow runs these checks on
dependency PRs and weekly; warnings still require a reachability assessment.
See [dependency security notes](docs/dependency-security.md) for the current
runtime baseline and deferred upstream warnings.

Before opening a pull request:

1. Keep changes focused.
2. Do not commit local inputs, outputs, credentials, task databases, or logs.
3. Run the relevant checks:

```bash
.venv/bin/python -m unittest discover -s tests -v
npm run check:webui
```

Frontend TypeScript and CSS changes should include the generated static assets
under `codex_image/webui/static/`.

For focused frontend behavior checks, install Node dependencies with `npm ci`,
then run the shared runner (Python standard library only):

```bash
python -m tests.frontend_runner
python -m tests.frontend_runner ux_recovery.test.ts
python -m tests.frontend_runner tests.test_webui_static_layout.WebUIStaticLayoutTests.test_orientation_events_preserve_requested_direction
```

Local `unittest discover` automatically collects every pure `*.test.ts` and
`*.test.cjs` file through `test_frontend_suites.py`. Do not add manual wrappers.
Old domain-specific module commands remain compatibility entrypoints and do not
duplicate discovery. Inline Node harnesses use `@frontend_test`; the shared runner
discovers those marked methods as well, preserving their scenarios and test IDs.
In CI, the WebUI job runs these pure frontend tests once and checks generated assets; the Python version matrix
sets `ILAB_SKIP_PURE_FRONTEND_TESTS=1` to avoid repeating that work. The two tests
that pass a real backend catalog into TypeScript, and the reference-file icon test
that reads the backend file policy, remain in every Python job.
Keep the full expected model list in `test_generation_catalog.py`, asset URL
consistency in `test_webui_static_pwa.py`, and action pins in
`test_release_contracts.py`, rather than copying those lists into feature tests.
Frontend module and bootstrap contracts live in `test_webui_static_architecture.py`,
short-height layout contracts in `test_webui_static_short_height.py`, and retired
account entrypoint contracts in `test_legacy_account_pool_removed.py`. Keep data
retention and compatibility scenarios even when consolidating their fixtures.
Codec payload tests must assert independent expected fields, rather than compare
two callers of the same payload builder. Public repository boundaries are checked
against the actual Git index and CI guard, not a historical export allowlist.

The real-browser suites share an isolated host:

```bash
.venv/bin/python -m tests.browser_fixture
```

Open `http://127.0.0.1:18792/qa` in the in-app browser and run the history,
image-mentions, prompt-paste, workbench-layout and api-settings pages one at a time. Each page displays a JSON
report with `passed`; prompt-paste also requires zero unexpected resource
requests. The host uses synthetic data, binds only to loopback, and removes its
temporary files on normal shutdown. Stop it with Ctrl+C after acceptance.
Before each suite, the harness unregisters service workers and clears caches on
this dedicated fixture origin, reloading once if an old worker still controls it.
The workbench suite checks viewport and sidebar boundaries, gallery growth, themes,
parameter layouts and mobile restoration with synthetic data. It also activates
the coarse-pointer stylesheet branch to verify the three-line prompt minimum at
the touch font size, including ancestor clipping and toolbar overlap with find
expanded; this does not emulate native touch events or change matchMedia.
The API settings suite checks advanced values through folding, saving, reopening,
cancellation and copying against isolated storage, plus responsive fields in both
themes and Chinese/English. Model discovery uses a synthetic response; it does not
verify external provider connectivity or native password-manager autofill.
The `workbench-feedback` page checks inline find/replace, focus restoration,
responsive toolbar geometry, placeholder contrast and shared button/card states
in both themes. It maps CSS interaction pseudo-classes to equally specific test
attributes for deterministic color checks; this does not emulate native pointer events.
The `api-provider-delete` page verifies default reassignment, rejected and delayed
writes, duplicate actions, preserved credentials and selections, and deletion
persistence after reload using synthetic providers and the real settings backend.
The `recent-asset-refresh` page submits synthetic reference images and checks
that delayed thumbnails do not blank the recent row when it reorders.
Fixture app pages disable PWA registration and report startup errors, unhandled
rejections and failed resources as failures. These suites do not test offline PWA
behavior; do not host them on an origin containing real user data.
For a history bundle comparison, pass `--baseline-bundle PATH` and open
`/qa/history?variant=baseline`. The old `tests.history_browser_fixture` command
remains an alias. CI runs Chromium checks for compact layout, provider deletion,
task menu deletion, recent reference refresh, backup navigation and transfer
cancellation with `npm run test:browser`. Install its browser with
`npx --no-install playwright install chromium`; set `QA_PYTHON` to the project
Python executable for local runs. The runner owns a loopback-only fixture and
cleans up its browser and server. Other browser pages remain manual acceptance;
Node-only tests do not cover these browser behaviors.

API Key autofill changes also need manual Chrome/Edge acceptance on `/qa-app`.
Use a separate test profile with synthetic credentials saved for the fixture
origin. First confirm that the previous version actually fills the saved password;
if it does not, record the reproduction gap rather than claiming autofill coverage.
With the fix, verify that new and existing provider editors stay empty before and
after focus and after reopening. Check typing/pasting, press-to-reveal masking,
and cancellation without saving. Static attribute checks and a browser with no
matching saved credentials do not replace this check. Never use or record real
passwords or API keys in acceptance evidence.

Release jobs inspect the final ZIP/DMG with `scripts/check-package-smoke.py`
before uploading artifacts: archive checksum, bundled Python/dependencies,
image codecs, and an isolated server's basic routes. These checks do not replace
native launcher UI or updater acceptance on each supported platform.

`scripts/publish-release.py` prepares signed manifests before external writes,
uploads only to a draft, and verifies remote asset names, sizes and SHA-256
before publishing. Failures leave a draft for inspection; an explicit rerun can
resume that draft but cannot overwrite a published release. Release notes are
read from the Markdown version section, without requiring the old “本版详情”
marker. Notes must name the exact version and no longer be marked as a draft.
