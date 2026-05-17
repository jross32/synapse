import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Vite config for the renderer (React UI loaded inside Electron's BrowserWindow).
// The Electron main process is compiled separately by `tsc -p electron/tsconfig.json`.
export default defineConfig({
  root: path.resolve(__dirname, 'renderer'),
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@renderer': path.resolve(__dirname, 'renderer'),
      '@shared': path.resolve(__dirname, 'renderer/lib'),
    },
  },
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    // Pin to IPv4 loopback. Vite 5 otherwise binds "localhost" which Windows
    // resolves to [::1] (IPv6) first -- synapse.cmd's health poll hits
    // 127.0.0.1 and never matches. Electron's loadURL('http://localhost:5173')
    // still works (it falls back from ::1 to 127.0.0.1).
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
});
