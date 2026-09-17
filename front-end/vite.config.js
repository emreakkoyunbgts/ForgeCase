import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  const env = { ...loadEnv(mode, root, ''), ...process.env }
  const ports = { vault: 8000, generator: 8001, librarian: 8002, reader: 8003, verifier: 8004, publisher: 8005, analyst: 8007 }
  const proxy = Object.fromEntries(Object.entries(ports).map(([service, port]) => [
    '^/api/' + service + '(?:/|$)',
    { target: env[service.toUpperCase() + '_URL'] || 'http://127.0.0.1:' + port,
      changeOrigin: true, timeout: 110000, proxyTimeout: 110000,
      rewrite: url => url.replace(new RegExp('^/api/' + service + '(?=/|$)'), ''),
      configure: proxy => proxy.on('proxyReq', (proxyRequest, incomingRequest) => {
        if (!incomingRequest.headers.authorization && env.CASEFORGE_TOKEN) {
          proxyRequest.setHeader('Authorization', 'Bearer ' + env.CASEFORGE_TOKEN)
        }
      }),
    },
  ]))
  return { plugins: [react()], server: { host: '127.0.0.1', proxy },
    preview: { host: '127.0.0.1', proxy } }
})
