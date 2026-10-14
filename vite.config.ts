import {defineConfig} from 'vite';
export default defineConfig({base:'./',server:{port:5173,watch:{ignored:['**/outputs/**','**/runtime/**','**/test-upload/**','**/.venv/**','**/.cache/**']}},build:{outDir:'dist'}});
