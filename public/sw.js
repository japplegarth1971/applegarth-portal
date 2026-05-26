// Applegarth Health & Safety Portal — Service Worker
const CACHE = 'ahs-portal-v1';
const SHELL = [
  '/login',
  '/register',
  '/dashboard',
  '/admin',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

// Install: cache the app shell
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch strategy:
// - API calls: network-only (always fresh data)
// - App shell (HTML pages): network-first, fall back to cache
// - Static assets: cache-first
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API: always go to network
  if (url.pathname.startsWith('/api/')) {
    return; // default browser behaviour
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      }))
    );
    return;
  }

  // HTML pages: network-first, fall back to cache
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
