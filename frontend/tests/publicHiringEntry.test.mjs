import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { authEntryDestination } from '../src/utils/homeFor.js'

const read = path => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')

test('public manager links preserve the employer destination through authentication', () => {
  for (const page of ['index.html', 'about/index.html', 'contact/index.html', 'learn/index.html']) {
    const html = read(`public-site/${page}`)
    const links = [...html.matchAll(/href="(https:\/\/hiring\.cookcredit\.com[^" ]*)"/g)].map(match => new URL(match[1]))
    const login = links.find(url => url.pathname === '/login')
    assert.ok(login, page)
    assert.equal(authEntryDestination({ search: login.search }), '/business/roles', page)
    assert.ok(!html.includes('href="/hiring/"'), page)
  }
})

test('legacy public hiring bookmarks redirect only to the canonical hiring home', () => {
  const redirects = JSON.parse(read('deploy/public-hiring-redirects.json'))
  assert.deepEqual(redirects.map(row => row.glob), ['/hiring', '/hiring/', '/hiring/index.html'])
  for (const row of redirects) {
    assert.equal(row.statusCode, 301)
    assert.equal(row.location, 'https://hiring.cookcredit.com/')
  }
  const fallback = read('public-site/hiring/index.html')
  assert.match(fallback, /http-equiv="refresh" content="0;url=https:\/\/hiring\.cookcredit\.com\/"/)
  assert.ok(!fallback.includes('request-access'))
})
