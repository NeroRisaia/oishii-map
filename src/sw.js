'use strict';

// おいしい店マップ（非公式）の Service Worker。
// データ更新・画面変更のたびに番号を上げる（全体を入れ替えるため）。
// 自分のキャッシュ（oishii-map- で始まる名前）以外には触らない。同じオリジンの他アプリに影響させないため。
const CACHE = 'oishii-map-v3';
const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './vendor/leaflet/leaflet.css',
  './vendor/leaflet/leaflet.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then(async (cache) => {
        for (const path of SHELL) {
          try {
            await cache.add(new Request(path, { cache: 'reload' }));
          } catch {
            // 1ファイル失敗しても install 全体を中止しない
          }
        }
      })
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith('oishii-map-') && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

// 自分のスコープ内・同一オリジンの GET だけ。キャッシュがあれば即返し、裏で更新する（次回起動で反映）。地図タイルは対象外。
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET' || !req.url.startsWith(self.registration.scope)) return;

  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(req, { ignoreSearch: true });
      const network = fetch(req, { signal: AbortSignal.timeout(8000) }).then((response) => {
        if (response.ok) cache.put(req, response.clone());
        return response;
      });
      if (cached) {
        event.waitUntil(network.catch(() => {}));
        return cached;
      }
      return network.catch(() => new Response('オフラインです', {
        status: 503,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      }));
    }),
  );
});
