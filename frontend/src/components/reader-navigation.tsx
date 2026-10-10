import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import type { PoemNeighbors } from '@/data/poem-library'

type ReaderNavigationProps = {
  neighbors: PoemNeighbors | null
  disabled: boolean
  onNavigate: (id: string) => void
}

export function ReaderNavigation({ neighbors, disabled, onNavigate }: ReaderNavigationProps) {
  return (
    <footer
      className="mx-auto mt-6 w-full shrink-0 px-0 pb-4 lg:mt-auto lg:max-w-[27rem] lg:px-4 lg:pt-8 lg:pb-0"
    >
      <HorizontalEditorialDivider className="mb-3 hidden w-full lg:block" />
      <nav
        aria-label="切换作品"
        className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2"
      >
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-fit justify-self-start px-1 font-normal text-muted-foreground hover:text-foreground"
          disabled={disabled || !neighbors?.previous_id}
          onClick={() => {
            if (neighbors?.previous_id) onNavigate(neighbors.previous_id)
          }}
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          上一首
        </Button>
        <p
          className="min-w-0 text-center text-[10px] leading-4 text-muted-foreground sm:text-[11px]"
        >
          划选诗句，即可引用提问
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-fit justify-self-end px-1 font-normal text-muted-foreground hover:text-foreground"
          disabled={disabled || !neighbors?.next_id}
          onClick={() => {
            if (neighbors?.next_id) onNavigate(neighbors.next_id)
          }}
        >
          下一首
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </nav>
    </footer>
  )
}
