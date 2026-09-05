import assert from "node:assert/strict";
import test from "node:test";

class ElementStub {
  children: ElementStub[] = [];
  attributes: Record<string, string> = {};
  textContent = "";
  hidden = false;
  open = false;
  value = "";
  constructor(readonly tagName: string) {}
  get childElementCount() { return this.children.length; }
  replaceChildren() { this.children = []; }
  append(...children: ElementStub[]) { this.children.push(...children); }
  prepend(child: ElementStub) { this.children.unshift(child); }
  setAttribute(name: string, value: string) { this.attributes[name] = value; }
  set innerHTML(_value: string) { throw new Error("Paths must be rendered as text"); }
}

test("retained paths use the shared notice region even without a generation status element", async () => {
  const globals = globalThis as any;
  const original = { window: globals.window, document: globals.document, fetch: globals.fetch };
  const els = {
    settingsInputRoot: new ElementStub("input"),
    settingsPreviousPaths: new ElementStub("details"),
    settingsPreviousPathsList: new ElementStub("dl"),
    settingsStatus: new ElementStub("div"),
    taskNotificationToastRegion: new ElementStub("div"),
    // The history page has no statusText; this matches its no-op setStatus().
  };
  const methods: Record<string, any> = { setStatus() {} };
  let previousPaths: Record<string, string> = {};
  globals.window = { __codexImageWebUI: { state: {}, els, methods }, setTimeout() {} };
  globals.document = { createElement: (tag: string) => new ElementStub(tag), addEventListener() {} };
  globals.fetch = async () => ({ ok: true, json: async () => ({ settings: {}, previous_paths: previousPaths }) });
  try {
    const { initStorageSettingsFeature } = await import("../../codex_image/webui/frontend/src/storage-settings");
    const { translate } = await import("../../codex_image/webui/frontend/src/i18n");
    initStorageSettingsFeature();
    await methods.refreshSettings();
    assert.equal(els.settingsPreviousPaths.hidden, true);
    assert.equal(els.taskNotificationToastRegion.childElementCount, 0);

    previousPaths = { output_root: '/data/<img src=x onerror="alert(1)">' };
    await methods.refreshSettings();
    assert.equal(els.settingsPreviousPaths.hidden, false);
    assert.equal(els.settingsPreviousPaths.open, false);
    assert.equal(els.settingsPreviousPathsList.children[1].tagName, "dd");
    assert.equal(els.settingsPreviousPathsList.children[1].textContent, previousPaths.output_root);
    assert.equal(els.taskNotificationToastRegion.childElementCount, 1);
    const notice = els.taskNotificationToastRegion.children[0];
    assert.equal(notice.attributes.role, "status");
    assert.equal(notice.children[1].textContent, translate("settings.previousPathsNotice"));

    await methods.refreshSettings();
    assert.equal(els.taskNotificationToastRegion.childElementCount, 1, "Opening settings must not repeat the startup notice");
    previousPaths = {};
    await methods.refreshSettings();
    assert.equal(els.settingsPreviousPaths.hidden, true);
    assert.equal(els.settingsPreviousPathsList.childElementCount, 0);
  } finally {
    Object.assign(globals, original);
  }
});
