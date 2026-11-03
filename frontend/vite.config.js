import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import voiceSessions from './api/voice/sessions.js';

const page = (path) => resolve(import.meta.dirname, path);

// Serves the browser-voice token route (api/voice/sessions.js) during `npm run dev`, as Vercel does on the preview.
// LiveKit settings come from the .env at the repository root; nothing from it reaches the browser bundle.
function voiceTokens() {
  return {
    name: 'careloop-voice-tokens',
    configureServer(server) {
      Object.assign(process.env, loadEnv(server.config.mode, resolve(import.meta.dirname, '..'), 'LIVEKIT_'));
      server.middlewares.use('/api/voice/sessions', (req, res, next) => {
        if (req.url !== '/' && req.url !== '') return next();
        voiceSessions(req, res).catch(next);
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), voiceTokens()],
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
