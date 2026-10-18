import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('quotes, links, reader underlines, and unread dots use the editorial red palette', () => {
  const components = [
    '../src/components/assistant-markdown.tsx',
    '../src/components/quote-preview.tsx',
    '../src/components/user-message.tsx',
    '../src/components/chat-message-list.tsx',
    '../src/components/mobile-layout.tsx',
    '../src/components/poem-body.tsx',
  ].map(read)

  assert.match(components[0], /border-editorial-red(?:\s|\b)/)
  assert.match(components[0], /text-editorial-red/)
  assert.match(components[1], /border-editorial-red(?:\s|\b)/)
  assert.match(components[2], /border-editorial-red(?:\s|\b)/)
  assert.match(components[3], /bg-editorial-red/)
  assert.match(components[4], /bg-editorial-red/)
  assert.match(components[5], /className="poem-quote-underline"/)
  assert.match(components[5], /quoteTextRects\(block, selected!\.start, selected!\.end\)/)
  assert.doesNotMatch(components[5], /selection:bg-editorial-red\/20/)
  assert.doesNotMatch(components.join('\n'), /(?:violet|purple|fuchsia)-/)
  assert.match(components[0], /border-editorial-red pl-4 text-muted-foreground/)
})

test('semantic errors use the original editorial red while retaining error roles', () => {
  const css = read('../src/index.css')
  assert.match(css, /--editorial-red-base: #aa381e/)
  assert.match(css, /--editorial-red: var\(--editorial-red-base\)/)
  assert.match(
    css,
    /--editorial-red: color-mix\(in srgb, var\(--editorial-red-base\) 75%, transparent\)/,
  )
  assert.doesNotMatch(css, /editorial-red-readable|color-mix\(in srgb, var\(--editorial-red\)/)
  assert.equal(css.match(/--destructive: var\(--editorial-red\);/g)?.length, 2)
  assert.match(
    read('../src/components/assistant-message.tsx'),
    /role=\{notice \? 'status' : 'alert'\}/,
  )
})
