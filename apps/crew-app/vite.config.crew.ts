import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dependencies provided at runtime by the Kiro Crew dashboard host
const HOST_PROVIDED = [
  'react',
  'react-dom',
  'react/jsx-runtime',
  'lucide-react',
  '@kirocrew/app-sdk',
  '@kirocrew/app-sdk/ui',
];

// Kiro Crew App Kit library build -> outputs dist/index.mjs per app.json
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: 'src/App.tsx',
      formats: ['es'],
      fileName: () => 'index.mjs',
    },
    rollupOptions: {
      external: HOST_PROVIDED,
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
          '@kirocrew/app-sdk': 'KiroCrewAppSdk',
        },
      },
    },
  },
});
