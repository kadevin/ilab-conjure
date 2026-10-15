/** Shared setup for the synthetic browser fixture, never the user's WebUI origin. */
export async function prepareFixtureOrigin(): Promise<void> {
  if ("serviceWorker" in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const removed = await Promise.all(registrations.map(registration => registration.unregister()));
    if (removed.some(result => !result)) throw new Error("Could not unregister a fixture service worker");
  }
  if ("caches" in window) {
    await Promise.all((await caches.keys()).map(name => caches.delete(name)));
  }
  // Unregistering does not release the current document's existing controller.
  const url = new URL(location.href);
  if (navigator.serviceWorker?.controller) {
    if (url.searchParams.has("qa-worker-reset")) throw new Error("Fixture is still controlled by a service worker");
    url.searchParams.set("qa-worker-reset", "1");
    location.replace(url);
    await new Promise<void>(() => {}); // The replacement document restarts the suite.
  }
  if (url.searchParams.has("qa-worker-reset")) {
    url.searchParams.delete("qa-worker-reset");
    history.replaceState(null, "", url);
  }
}

export async function loadAcceptanceFrame(frame: HTMLIFrameElement, url: string, errors: string[]): Promise<void> {
  // The fixture injects this reporter before any application script can execute.
  window.addEventListener("message", event => {
    if (event.origin === location.origin && event.source === frame.contentWindow
      && event.data?.type === "qa-runtime-error" && typeof event.data.message === "string") {
      errors.push(event.data.message);
    }
  });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      frame.removeEventListener("load", loaded);
      reject(new Error(`Timeout loading ${url}`));
    }, 15000);
    function loaded() {
      if (frame.contentWindow?.location.href === "about:blank") return;
      clearTimeout(timer);
      frame.removeEventListener("load", loaded);
      if (frame.contentDocument?.documentElement.dataset.qaErrorCapture !== "ready") {
        reject(new Error("Fixture startup error capture is missing"));
      } else if (frame.contentWindow?.navigator.serviceWorker?.controller) {
        reject(new Error("Application frame is controlled by a service worker"));
      } else resolve();
    }
    frame.addEventListener("load", loaded);
    frame.src = url;
  });
  // Let errors posted during startup reach the host before running assertions.
  await new Promise(resolve => setTimeout(resolve, 0));
  if (errors.length) throw new Error(`Application startup failed: ${errors.join("; ")}`);
}
