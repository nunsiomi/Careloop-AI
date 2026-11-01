import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const page = (path) => resolve(import.meta.dirname, path);

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        landing: page('index.html'),
        patient: page('patient/index.html'),
        clinician: page('clinician/index.html')
      }
    }
  },
  optimizeDeps: { entries: ['index.html', 'patient/index.html', 'clinician/index.html'] },
  server: {
    port: 5173,
    // FastAPI runs on 8000 during development; the browser only talks to Vite.
    proxy: { '/api': 'http://127.0.0.1:8000' }
  }
});
