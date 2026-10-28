import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Auth uses an HttpOnly session cookie, so the browser must see the API on the page's own origin.
  server: { port: 5173, proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } } },
  preview: { proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } } },
});
