import { Button } from '@/components/ui/button'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'

export type ActiveView = 'chat' | 'analysis'

type ViewToolbarProps = {
  activeView: ActiveView
  onViewChange: (view: ActiveView) => void
}

/** Switch buttons and their short underline remain one editorial unit. */
export function ViewToolbar({ activeView, onViewChange }: ViewToolbarProps) {
  return (
    <div className="mb-3 w-fit shrink-0">
      <div className="mb-3 flex items-center gap-2" role="group" aria-label="讨论视图">
        <Button
          type="button"
          variant={activeView === 'chat' ? 'default' : 'ghost'}
          size="sm"
          aria-pressed={activeView === 'chat'}
          onClick={() => onViewChange('chat')}
        >
          对话
        </Button>
        <Button
          type="button"
          variant={activeView === 'analysis' ? 'default' : 'ghost'}
          size="sm"
          aria-pressed={activeView === 'analysis'}
          onClick={() => onViewChange('analysis')}
        >
          赏析
        </Button>
      </div>
      <HorizontalEditorialDivider className="w-[calc(100%+0.75rem)]" />
    </div>
  )
}
