import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  // The interactive employer preview uses a separate dependency cache so a running production
  // workspace cannot leave Windows file locks on Vite's normal cache during design review.
  cacheDir: process.env.VITE_PREVIEW === '1' ? '.vite-preview-cache' : undefined,
  plugins: [
    react(),
    // Real offline shell (replaces the old no-op public/sw.js). Generates dist/sw.js via Workbox.
    // AppUpdateNotice registers /sw.js and offers waiting releases (injectRegister:null). The hand-written
    // public/manifest.json (manifest:false). The separate public/firebase-messaging-sw.js is left
    // untouched and excluded from both precache and the navigation fallback.
    VitePWA({
      strategies: 'generateSW',
      registerType: 'prompt',
      filename: 'sw.js',
      injectRegister: null,
      manifest: false,
      workbox: {
        // After an explicit Update, take control so AppUpdateNotice receives
        // controllerchange and reloads only the tab that accepted the update.
        // Other tabs keep their unsaved work and receive their own prompt.
        clientsClaim: true,
        globPatterns: ['**/*.{js,css,html,woff2,png,svg,ico}'],
        globIgnores: ['**/firebase-messaging-sw.js', '**/vendor-cv-parser-*', '**/readCvPdf-*', '**/pdf.worker*'],
        navigateFallback: '/index.html',
        // /landing is a standalone marketing page, NOT a route of this SPA. It is copied into dist
        // after the build (scripts/copy-landing.mjs), so it never enters the precache manifest —
        // which meant this navigation fallback swallowed it. Any visitor who had ever loaded
        // cookcredit.com got the React shell for /landing/, and the router then rewrote the URL
        // to /. curl saw the real page and a browser did not. Denylisted so the request goes to
        // the network and Firebase serves the actual file.
        navigateFallbackDenylist: [/^\/api/, /^\/landing/, /firebase-messaging-sw\.js$/],
        cleanupOutdatedCaches: true,
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        // Cross-origin assets the precache can't cover: Google Fonts CSS/files
        // (Inter/Cormorant), user photos on GCS, and the mediapipe WASM. All
        // cache-first with bounded entries so repeat visits work on flaky
        // connections without unbounded growth.
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /^https:\/\/storage\.googleapis\.com\/.*\.(?:png|jpe?g|webp|gif)/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'user-photos',
              expiration: { maxEntries: 120, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /^https:\/\/cdn\.jsdelivr\.net\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'cdn-wasm',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 90 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react':   ['react', 'react-dom', 'react-router-dom'],
          'vendor-motion':  ['framer-motion'],
          'vendor-cv-parser': ['pdfjs-dist'],
          'vendor-icons':   ['lucide-react'],
          // Only the boot-path firebase modules: firestore/storage are gone from
          // the app entirely and messaging is dynamic-imported on demand, so
          // pinning them here would drag them back into an eagerly-loaded chunk.
          'vendor-firebase':['firebase/app', 'firebase/auth'],
        },
      },
    },
  },
})
