import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

type AssistantMarkdownProps = {
  content: string
  variant?: 'assistant' | 'user'
}

export function AssistantMarkdown({ content, variant = 'assistant' }: AssistantMarkdownProps) {
  const isUser = variant === 'user'

  return (
    <div
      className={
        isUser
          ? 'min-w-0 wrap-break-word text-sm leading-6 text-foreground/90'
          : 'min-w-0 wrap-break-word text-sm leading-7 text-foreground/90'
      }
    >
      <ReactMarkdown
        remarkPlugins={isUser ? [remarkGfm, remarkBreaks] : [remarkGfm]}
        skipHtml
        components={{
          p: ({ children }) => (
            <p className={isUser ? 'my-1 first:mt-0 last:mb-0' : 'my-3 first:mt-0 last:mb-0'}>
              {children}
            </p>
          ),

          h1: ({ children }) => (
            <h1 className="mb-3 mt-5 text-lg font-semibold first:mt-0">{children}</h1>
          ),

          h2: ({ children }) => (
            <h2 className="mb-3 mt-5 text-base font-semibold first:mt-0">{children}</h2>
          ),

          h3: ({ children }) => (
            <h3 className="mb-2 mt-4 text-sm font-semibold first:mt-0">{children}</h3>
          ),

          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),

          ul: ({ children }) => (
            <ul
              className={isUser ? 'my-1 list-disc space-y-0 pl-5' : 'my-3 list-disc space-y-1 pl-6'}
            >
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
                  ? 'my-2 border-l-2 border-violet-400/70 pl-3 text-muted-foreground'
                  : 'my-4 border-l-2 border-violet-400/70 pl-4 text-muted-foreground'
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
              className="text-violet-600 underline underline-offset-4 hover:text-violet-700 dark:text-violet-300"
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
                  ? 'my-2 max-w-full overflow-x-auto rounded-lg bg-muted p-2 text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0'
                  : 'my-3 max-w-full overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-6 [&_code]:bg-transparent [&_code]:p-0'
              }
            >
              {children}
            </pre>
          ),

          table: ({ children }) => (
            <div className="my-4 max-w-full overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),

          th: ({ children }) => (
            <th className="border-b border-border bg-muted/60 px-3 py-2 font-semibold">
              {children}
            </th>
          ),

          td: ({ children }) => (
            <td className="border-b border-border/60 px-3 py-2 align-top">{children}</td>
          ),

          hr: () => <hr className="my-5 border-border/60" />,

          // 暂不自动加载模型生成的远程图片。
          img: () => null,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
