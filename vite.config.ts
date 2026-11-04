import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: fileURLToPath(new URL('./frontend', import.meta.url)),
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./frontend/src', import.meta.url)) } },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    target: 'es2022',
    rollupOptions: { output: { manualChunks(id) {
      if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react';
    } } }
  },
  server: {
    // Exact internal Work preview host; localhost remains Vite's default.
    allowedHosts: ['terminal.local'],
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url))] }
  }
});
