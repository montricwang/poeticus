import { useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'
import { rehypeCharacterFade } from '@/lib/character-fade'

type AssistantMarkdownProps = {
  content: string
  variant?: 'assistant' | 'user'
  animateNewCharacters?: boolean
}

export function AssistantMarkdown({
  content,
  variant = 'assistant',
  animateNewCharacters = false,
}: AssistantMarkdownProps) {
  const isUser = variant === 'user'
  // Keep Markdown element component identities stable between SSE updates.
  // Otherwise React remounts every paragraph and restarts old glyph animations.
  const components = useMemo<Components>(
    () => ({
      p: ({ children }) => (
        <p className={isUser ? 'my-1 first:mt-0 last:mb-0' : 'my-3 first:mt-0 last:mb-0'}>
          {children}
        </p>
      ),

      h1: ({ children }) => (
        <h1 className="mb-3 mt-5 text-xl font-semibold first:mt-0">{children}</h1>
      ),

      h2: ({ children }) => (
        <h2 className="mb-3 mt-5 text-lg font-semibold first:mt-0">{children}</h2>
      ),

      h3: ({ children }) => (
        <h3 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h3>
      ),

      strong: ({ children }) => (
        <strong className="font-semibold text-foreground">{children}</strong>
      ),

      ul: ({ children }) => (
        <ul className={isUser ? 'my-1 list-disc space-y-0 pl-5' : 'my-3 list-disc space-y-1 pl-6'}>
          {children}
        </ul>
      ),

      ol: ({ children }) => (
        <ol
          className={
            isUser ? 'my-1 list-decimal space-y-0 pl-5' : 'my-3 list-decimal space-y-1 pl-6'
          }
        >
          {children}
        </ol>
      ),

      blockquote: ({ children }) => (
        <blockquote
          className={
            isUser
              ? 'my-2 border-l-2 border-editorial-red pl-3 text-muted-foreground'
              : 'my-4 border-l-2 border-editorial-red pl-4 text-muted-foreground'
          }
        >
          {children}
        </blockquote>
      ),

      li: ({ children }) => <li className="pl-1">{children}</li>,

      a: ({ href, children }) => (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-editorial-red underline underline-offset-4 hover:opacity-80"
        >
          {children}
        </a>
      ),

      code: ({ children, className }) => (
        <code className={`${className ?? ''} rounded bg-muted px-1.5 py-0.5 font-mono text-xs`}>
          {children}
        </code>
      ),

      pre: ({ children }) => (
        <pre
          className={
            isUser
              ? 'poeticus-scrollport my-2 max-w-full overflow-x-auto rounded-lg bg-muted p-2 text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0'
              : 'poeticus-scrollport my-3 max-w-full overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-6 [&_code]:bg-transparent [&_code]:p-0'
          }
        >
          {children}
        </pre>
      ),

      table: ({ children }) => (
        <div className="poeticus-scrollport my-4 max-w-full overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">{children}</table>
        </div>
      ),

      th: ({ children }) => (
        <th className="border-b border-border bg-muted/60 px-3 py-2 font-semibold">{children}</th>
      ),

      td: ({ children }) => (
        <td className="border-b border-border/60 px-3 py-2 align-top">{children}</td>
      ),

      hr: () => <hr className="my-5 border-border/60" />,

      // 暂不自动加载模型生成的远程图片。
      img: () => null,
    }),
    [isUser],
  )

  return (
    <div className="min-w-0 wrap-break-word text-base leading-7 text-foreground/90">
      <ReactMarkdown
        remarkPlugins={isUser ? [remarkGfm, remarkBreaks] : [remarkGfm]}
        skipHtml
        rehypePlugins={animateNewCharacters ? [rehypeCharacterFade] : []}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
