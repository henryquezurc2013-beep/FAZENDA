// Service Worker — Controle Bovino /campo
// Estratégia: cache-first pra shell estático, network-first pra HTML.
// NÃO faz cache de POST/PUT/PATCH/DELETE — fila offline é Frente C.

const CACHE_VERSION = 'campo-v2';
const SHELL = [
  '/campo',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Só GET; outros métodos passam direto (Frente C cuidará da fila)
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Não interceptar requests de outras origens
  if (url.origin !== location.origin) return;

  // Estratégia network-first pra HTML (sempre que possível, busca fresh)
  if (request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(request, copy));
          return resp;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Cache-first pra assets estáticos (manifest, ícones, etc)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(request, copy));
          return resp;
        });
      })
    );
    return;
  }

  // Demais requests (API GET): network-only por enquanto.
  // Frente C tratará offline com fila.
});
