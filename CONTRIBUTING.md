# Contributing

Thanks for your interest in improving iLab CONJURE.

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
```

Local `unittest discover` still includes these suites. In CI, the WebUI job runs
the pure Node suites once and checks generated assets; the Python version matrix
sets `ILAB_SKIP_PURE_FRONTEND_TESTS=1` to avoid repeating that work. The two tests
that pass a real backend catalog into TypeScript remain in every Python job.
Keep the full expected model list in `test_generation_catalog.py`, asset URL
consistency in `test_webui_static_pwa.py`, and action pins in
`test_release_contracts.py`, rather than copying those lists into feature tests.

The three real-browser suites share an isolated host:

```bash
.venv/bin/python -m tests.browser_fixture
```

Open `http://127.0.0.1:18792/qa` in the in-app browser and run the history,
image-mentions and prompt-paste pages one at a time. Each page displays a JSON
report with `passed`; prompt-paste also requires zero unexpected resource
requests. The host uses synthetic data, binds only to loopback, and removes its
temporary files on normal shutdown. Stop it with Ctrl+C after acceptance.
Before each suite, the harness unregisters service workers and clears caches on
this dedicated fixture origin, reloading once if an old worker still controls it.
Fixture app pages disable PWA registration and report startup errors, unhandled
rejections and failed resources as failures. These suites do not test offline PWA
behavior; do not host them on an origin containing real user data.
For a history bundle comparison, pass `--baseline-bundle PATH` and open
`/qa/history?variant=baseline`. The old `tests.history_browser_fixture` command
remains an alias. These browser checks are manual acceptance, not part of the
Node-only CI job.
