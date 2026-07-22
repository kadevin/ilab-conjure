const CACHE_NAME = "ilab-gpt-conjure-shell-v53";
const APP_SHELL_URLS = [
  "/",
  "/history",
  "/manifest.webmanifest",
  "/static/styles.css",
  "/static/app.js",
  "/static/history.js",
  "/static/pwa.js",
  "/static/brand/favicon.svg",
  "/static/brand/pwa-icon-192.png",
  "/static/brand/pwa-icon-512.png"
];
const APP_SHELL_PATHS = new Set(APP_SHELL_URLS.map((url) => new URL(url, self.location.origin).pathname));

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const requestUrl = new URL(request.url);
  if (requestUrl.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/", { ignoreSearch: true }))
    );
    return;
  }

  if (!APP_SHELL_PATHS.has(requestUrl.pathname)) return;

  event.respondWith(
    caches.match(request).then((cached) => (
      cached || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      }).catch(() => caches.match(request, { ignoreSearch: true }))
    ))
  );
});
