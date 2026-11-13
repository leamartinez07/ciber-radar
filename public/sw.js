"use strict";

const CACHE = "ciber-radar-54581a90b863";
const PRECACHE = ["/", "/en", "/assets/styles.78ee843a38a0.css", "/assets/app.c2ae314dad58.js", "/assets/theme.38de132543d0.js", "/data/latest.json", "/icons/icon-192.png", "/fonts/archivo-latin-wdth-normal.woff2", "/fonts/jetbrains-mono-latin-500-normal.woff2", "/fonts/source-serif-4-latin-400-normal.woff2", "/fonts/source-serif-4-latin-600-normal.woff2"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

// Primero la red, para tener siempre la última edición; el caché solo cubre la falta de conexión.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(networkFirst(request));
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") await cache.put(request.url, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request.url);
    if (cached) return cached;
    return request.mode === "navigate" ? cache.match("/") : Response.error();
  }
}
