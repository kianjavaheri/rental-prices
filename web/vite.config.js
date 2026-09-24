import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',              // works under a subpath (GitHub Pages) as well as root
  build: { chunkSizeWarningLimit: 1200 },
});
