import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    // three.js (~545 kB, 140 kB gzip) грузится отдельным ленивым чанком
    // только когда на экране появляется 3D-персонаж.
    chunkSizeWarningLimit: 600,
  },
})
