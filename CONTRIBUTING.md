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
