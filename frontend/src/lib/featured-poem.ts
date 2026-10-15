import type { Poem } from '@/data/poem-library'

export type FeaturedExcerpt = { text: string; isExcerpt: boolean }

/** Keep complete clauses; do not cut a Chinese poem at an arbitrary character. */
export function featuredExcerpt(work: Pick<Poem, 'body_segments'>): FeaturedExcerpt {
  const segments = work.body_segments.map((segment) => segment.trim()).filter(Boolean)
  const whole = segments.join('\n')
  if (Array.from(whole).length <= 90) return { text: whole, isExcerpt: false }

  const first = segments[0] ?? ''
  const chars = Array.from(first)
  // A first stanza often fits on a phone. For very long stanzas, finish on punctuation.
  if (chars.length <= 82) return { text: first, isExcerpt: true }
  const head = chars.slice(0, 82).join('')
  const lastStop = Math.max(head.lastIndexOf('。'), head.lastIndexOf('！'), head.lastIndexOf('？'))
  return { text: lastStop >= 25 ? head.slice(0, lastStop + 1) : head + '…', isExcerpt: true }
}
