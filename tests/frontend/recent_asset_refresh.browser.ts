/** Verify the submit-to-thumbnail handoff on the loopback fixture. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: string[] = [];
let assertions = 0;

function check(name: string, passed: boolean): void {
  assertions++;
  if (!passed) failures.push(name);
}

async function until(predicate: () => boolean, label: string): Promise<void> {
  const deadline = Date.now() + 8000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(`Timed out: ${label}`);
    await new Promise(resolve => setTimeout(resolve, 25));
  }
}

async function imageFile(color: string, name: string): Promise<File> {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d")!;
  context.fillStyle = color;
  context.fillRect(0, 0, 64, 64);
  // Give each fixture run distinct assets so reloading still exercises a new upload.
  const pixels = context.getImageData(0, 0, 4, 1);
  const salt = crypto.getRandomValues(new Uint8Array(4));
  salt.forEach((value, index) => { pixels.data[index * 4] = value; });
  context.putImageData(pixels, 0, 0);
  const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!), "image/png"));
  return new File([blob], name, { type: "image/png" });
}

async function run(): Promise<void> {
  await prepareFixtureOrigin();
  const seed = new FormData();
  seed.set("prompt", "Synthetic reference images");
  for (const [index, color] of ["#315746", "#6485a1", "#be9146"].entries()) {
    seed.append("reference_images", await imageFile(color, `qa-reference-${index}.png`));
  }
  const seeded = await fetch("/api/generate", { method: "POST", body: seed });
  if (!seeded.ok) throw new Error(`Reference seed failed: ${seeded.status} ${await seeded.text()}`);

  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const win = frame.contentWindow!;
  const doc = frame.contentDocument!;
  const list = doc.querySelector<HTMLElement>("#recentAssetList")!;
  const runButton = doc.querySelector<HTMLButtonElement>("#runButton")!;
  const buttons = () => Array.from(list.querySelectorAll<HTMLButtonElement>("[data-reference-asset-id]"));
  const images = () => buttons().map(button => button.querySelector("img")!);
  const order = () => buttons().map(button => button.dataset.referenceAssetId!);
  const loaded = (image: HTMLImageElement) => image.complete && image.naturalWidth > 0;
  const visibleButtons = () => {
    const viewport = list.getBoundingClientRect();
    return buttons().filter(button => {
      const rect = button.getBoundingClientRect();
      return rect.right > viewport.left && rect.left < viewport.right;
    });
  };
  const visibleImages = () => visibleButtons().map(button => button.querySelector("img")!);
  await until(() => !runButton.disabled && Boolean(win.__codexImageWebUI?.state.generationCatalog) && buttons().length >= 3
    && images().slice(0, 3).every(loaded), "first three thumbnails loaded");
  const { methods } = win.__codexImageWebUI!;

  type RecentItem = { id: string; thumbnail_url: string };
  let pending: { items: RecentItem[]; release: () => void } | undefined;
  let hold = false;
  let delayedIndexes: number[] = [];
  let stalledAsset = "";
  let submissions = 0;
  const nativeFetch = win.fetch.bind(win);
  win.fetch = async (input, init) => {
    const path = new URL(typeof input === "string" ? input : input instanceof win.URL ? input.href : input.url, win.location.href).pathname;
    const response = await nativeFetch(input, init);
    if (path === "/api/edit") {
      if (response.ok) submissions++;
      else failures.push(`Edit submission failed: ${response.status} ${await response.clone().text()}`);
    }
    if (path !== "/api/reference-assets/recent" || (!hold && !stalledAsset) || !response.ok) return response;
    const shouldHold = hold;
    hold = false;
    const data = await response.json() as { items: RecentItem[] };
    for (const index of delayedIndexes) {
      const item = data.items[index];
      if (item) item.thumbnail_url = `/qa-reference-thumbnail/${item.id}`;
    }
    delayedIndexes = [];
    if (stalledAsset) {
      const item = data.items.find(item => item.id === stalledAsset)!;
      item.thumbnail_url = `/qa-reference-thumbnail/${item.id}?stalled=true`;
      stalledAsset = "";
    }
    if (shouldHold) await new Promise<void>(release => { pending = { items: data.items, release }; });
    return new win.Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  };

  async function submitAndCheck(label: string, expectedFirst?: string): Promise<void> {
    const oldOrder = order();
    const oldImages = new Map(oldOrder.map((id, index) => [id, images()[index]!]));
    const oldScrollLeft = list.scrollLeft;
    const expectedSubmissions = submissions + 1;
    methods.setPromptText!(`Use synthetic reference: ${label}`);
    pending = undefined;
    hold = true;
    runButton.click();
    await until(() => Boolean(pending), `${label} submitted and refreshed`);
    const response = pending!;
    const nextFirst = response.items[0]!.id;
    check(`${label}: submission moved the expected asset to the top`, submissions === expectedSubmissions
      && (expectedFirst ? nextFirst === expectedFirst : !oldImages.has(nextFirst)));
    check(`${label}: loaded thumbnails stay mounted while waiting for the list`, order().join() === oldOrder.join()
      && visibleButtons().every(button => {
        const image = button.querySelector("img")!;
        return image === oldImages.get(button.dataset.referenceAssetId!) && loaded(image);
      }));

    let blank = false;
    let watching = true;
    const visibleReady = () => visibleImages().length > 0 && visibleImages().every(loaded);
    const inspectFrame = () => {
      if (!watching) return;
      blank ||= !visibleReady();
      win.requestAnimationFrame(inspectFrame);
    };
    win.requestAnimationFrame(inspectFrame);
    response.release();
    try {
      await until(() => order()[0] === nextFirst && visibleReady(), `${label} new order displayed`);
    } finally {
      watching = false;
    }
    check(`${label}: visible thumbnails never go blank when the order changes`, !blank);
    check(`${label}: server order is applied and retained thumbnails are reused`, order().join()
      === response.items.slice(0, order().length).map(item => item.id).join()
      && order().every((id, index) => !oldImages.has(id) || images()[index] === oldImages.get(id))
      && Math.abs(list.scrollLeft - oldScrollLeft) <= 1);
  }

  doc.querySelector<HTMLButtonElement>('[data-theme-option="light"]')!.click();
  const later = buttons().find(button => button.querySelector("img")?.alt === "qa-reference-0.png")!;
  const laterId = later.dataset.referenceAssetId!;
  check("desktop starts with the selected reference below the top", order().indexOf(laterId) > 0
    && doc.documentElement.dataset.theme === "light");
  later.focus();
  later.click();
  await submitAndCheck("desktop existing reference", laterId);
  check("desktop: reordering keeps keyboard focus on the same thumbnail", doc.activeElement === later);

  doc.querySelector<HTMLButtonElement>("#clearImagesButton")!.click();
  doc.querySelector<HTMLButtonElement>('[data-theme-option="dark"]')?.click();
  frame.style.width = "390px";
  frame.style.height = "844px";
  await until(() => doc.documentElement.clientWidth === 390, "narrow viewport");
  check("narrow upload uses the dark theme", doc.documentElement.dataset.theme === "dark");
  const upload = await imageFile("#902e54", "qa-new-reference.png");
  const picker = doc.querySelector<HTMLInputElement>("#imageInput")!;
  const transfer = new win.DataTransfer();
  transfer.items.add(upload);
  picker.files = transfer.files;
  picker.dispatchEvent(new win.Event("change", { bubbles: true }));
  delayedIndexes = [0];
  await submitAndCheck("narrow new upload");

  doc.querySelector<HTMLButtonElement>("#clearImagesButton")!.click();
  frame.style.width = "1440px";
  frame.style.height = "900px";
  await until(() => doc.documentElement.clientWidth === 1440, "desktop viewport");
  for (let batch = 0; batch < 2; batch++) {
    const seed = new FormData();
    seed.set("prompt", "Synthetic scrollable reference images");
    for (let index = 0; index < 12; index++) {
      seed.append("reference_images", await imageFile(`rgb(${batch * 12 + index} 81 161)`, `qa-scroll-${batch}-${index}.png`));
    }
    const response = await fetch("/api/generate", { method: "POST", body: seed });
    if (!response.ok) throw new Error(`Scrollable references seed failed: ${response.status}`);
  }
  await methods.refreshRecentAssets!();
  list.scrollLeft = list.scrollWidth;
  await until(() => buttons().length > 12, "second batch mounted");
  list.scrollLeft += buttons()[12]!.getBoundingClientRect().left - list.getBoundingClientRect().left;
  await until(() => visibleImages().length > 0 && visibleImages().every(loaded), "scrolled thumbnails loaded");
  check("scroll reaches the second batch", buttons().indexOf(visibleButtons()[0]!) >= 11);
  const newFiles = await Promise.all(Array.from({ length: 15 }, (_, index) =>
    imageFile(`rgb(${index} 49 222)`, `qa-scroll-new-${index}.png`)));
  methods.addImageFiles(newFiles);
  delayedIndexes = [12, 13, 14];
  await submitAndCheck("desktop scrolled upload");

  const beforeRetry = visibleImages();
  stalledAsset = visibleButtons()[0]!.dataset.referenceAssetId!;
  void methods.refreshRecentAssets!();
  const retry = () => doc.querySelector<HTMLButtonElement>("[data-recent-assets-retry]");
  await until(() => Boolean(retry()), "thumbnail timeout exposes retry");
  check("timeout keeps the loaded row and clears busy", !list.hasAttribute("aria-busy")
    && visibleImages().every((image, index) => image === beforeRetry[index] && loaded(image)));
  retry()!.click();
  await until(() => !list.hasAttribute("aria-busy") && !retry(), "retry completed");
  check("retry leaves every visible thumbnail ready", visibleImages().length === beforeRetry.length
    && visibleImages().every(loaded));
}

void run().catch(error => { failures.push(String(error)); }).then(() => {
  output.textContent = JSON.stringify({ passed: !failures.length && !errors.length, assertions, failures, errors });
});
