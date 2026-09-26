import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:5000',
      '/documents': 'http://localhost:5000',
      '/query': 'http://localhost:5000',
      '/health': 'http://localhost:5000',
      '/sessions': 'http://localhost:5000',
      '/users': 'http://localhost:5000',
    },
  },
});
