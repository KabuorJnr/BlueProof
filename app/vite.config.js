import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', target: 'es2020', assetsInlineLimit: 8192 },
  server: { host: true, port: 5174 },
});
