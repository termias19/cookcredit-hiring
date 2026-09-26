import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { extname, join, resolve } from 'node:path'

const root = resolve(process.cwd(), 'preview-dist')
const port = Number(process.argv[2] || 5202)
const types = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url || '/', 'http://localhost').pathname)
    const requested = resolve(root, `.${pathname}`)
    let file = requested.startsWith(root) ? requested : join(root, 'index.html')
    const info = await stat(file).catch(() => null)
    if (!info?.isFile()) file = join(root, 'index.html')
    const bytes = await readFile(file)
    response.writeHead(200, {
      'Content-Type': types[extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    })
    response.end(bytes)
  } catch (error) {
    response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
    response.end(`Preview server error: ${error.message}`)
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`CookCredit preview: http://127.0.0.1:${port}/preview`)
})
