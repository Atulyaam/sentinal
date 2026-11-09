import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Standard Vite configuration for browser standalone preview and Judge Demo
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    port: 4173,
    host: '127.0.0.1',
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
