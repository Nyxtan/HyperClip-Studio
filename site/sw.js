// Monetag Service Worker Verification
// Site ID: 3591701 (nyxclip-studio.pages.dev)
// Verification Hash: 0c95113a8b03d81f340cd71931bd9697
self.addEventListener('install', () => {
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
