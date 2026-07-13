// 전설이 키우기 PWA 서비스 워커
// 게임 데이터는 항상 최신이어야 하므로 페이지·API는 네트워크 우선(캐시 안 함),
// 아이콘/매니페스트 같은 정적 자원만 캐시해 오프라인·재방문 속도를 높입니다.
const CACHE = 'legend-static-v1';
const ASSETS = [
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-maskable.png',
  '/static/apple-touch-icon.png',
  '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;                 // POST(액션)는 건드리지 않음
  // 정적 자원만 캐시 우선
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
    return;
  }
  // 그 외(대시보드·API)는 항상 네트워크 (최신 동기화 유지)
});
