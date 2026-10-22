/** Fade newly streamed graphemes without changing the SSE or reveal rate. */
type Node = {
  type: string
  tagName?: string
  value?: string
  properties?: Record<string, string | string[]>
  children?: Node[]
}

export function rehypeCharacterFade() {
  const segmenter = new Intl.Segmenter('zh', { granularity: 'grapheme' })

  return (root: Node) => {
    function visit(node: Node, skip = false): void {
      if (!node.children) return
      const excluded = skip || node.tagName === 'code' || node.tagName === 'pre'
      node.children = node.children.flatMap((child): Node[] => {
        if (child.type === 'text' && !excluded) {
          return Array.from(segmenter.segment(child.value ?? ''), ({ segment }) => {
            if (/^\s+$/u.test(segment)) return { type: 'text', value: segment }
            return {
              type: 'element',
              tagName: 'span',
              properties: {
                className: ['stream-character-fade'],
              },
              children: [{ type: 'text', value: segment }],
            }
          })
        }
        visit(child, excluded)
        return [child]
      })
    }
    visit(root)
  }
}
