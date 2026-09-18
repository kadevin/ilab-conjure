// Bundle for a real browser with esbuild. Initialize window.__codexImageWebUI
// before loading it. The hosting test server must count /unexpected-* requests.
import { promptPasteTextFromClipboard } from "../../codex_image/webui/frontend/src/prompt-editor-paste";

const cases: Array<[string, string, string?]> = [
  ["<div>hello&nbsp;<b>world</b></div><p>next<br>line</p>", "hello world\nnext\nline"],
  ['<img src="/unexpected-image" onerror="window.pasteExecuted=true"><p>safe</p>', "safe"],
  ['<svg onload="window.pasteExecuted=true"><image href="/unexpected-svg"/></svg><p>safe</p>', "safe"],
  ['<iframe src="/unexpected-frame"></iframe><object data="/unexpected-object"></object><p>safe</p>', "safe"],
  ['<link rel="stylesheet" href="/unexpected-style"><style>@import "/unexpected-import";</style><p>safe</p>', "safe"],
  ['<script>window.pasteExecuted=true</script><p>safe</p>', "safe"],
  ['<img src="/unexpected-plain"><p>ignored</p>', "plain\ntext", "plain\r\ntext"],
];

async function run(): Promise<void> {
  const results = cases.map(([html, expected, plain]) => {
    const data = new DataTransfer();
    data.setData("text/html", html);
    if (plain) data.setData("text/plain", plain);
    const actual = promptPasteTextFromClipboard(data);
    return { expected, actual, passed: actual === expected };
  });
  await new Promise((resolve) => setTimeout(resolve, 500));
  const executed = Boolean((window as any).pasteExecuted);
  document.body.textContent = JSON.stringify({ results, executed, passed: !executed && results.every((r) => r.passed) });
}
void run();
