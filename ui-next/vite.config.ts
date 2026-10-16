import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const here = (p: string) => path.resolve(__dirname, p);

// Pages rebuilt on the aunoo design system. The library is vendored from
// AuNooAI/aunoo-design (see vendor/DESIGN_SHA) and resolved from source, as in that repo.
// Output goes to static/aunoo-next/; deploy.sh copies the entry tags into templates/.
export default defineConfig({
  base: '/static/aunoo-next/',
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@aunoo/ui/styles.css', replacement: here('vendor/aunoo-ui/src/styles/index.css') },
      { find: '@aunoo/ui', replacement: here('vendor/aunoo-ui/src/index.ts') },
      { find: '@aunoo/shell', replacement: here('vendor/aunoo-shell/src/index.ts') },
      // API clients shared with the React 18 app, so both UIs call the backend the same way
      { find: /^@monolith-types\/(.*)$/, replacement: here('../ui/src/types/$1') },
      { find: /^@monolith\/(.*)$/, replacement: here('../ui/src/services/$1') },
    ],
  },
  build: {
    outDir: here('../static/aunoo-next'),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: { gather: here('gather.html'), operations: here('operations.html'), anticipate: here('anticipate.html'), submit: here('submit.html'), explore: here('explore.html'), settings: here('settings.html') },
    },
  },
  server: { port: 5178 },
});
