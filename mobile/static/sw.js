// DTC Knowledge Graph Galaxy Mobile Service Worker
const CACHE_NAME = 'dtc-mobile-v1';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  // Network first strategy with graceful offline fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
