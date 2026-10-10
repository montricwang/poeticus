import { useLayoutEffect, useRef, useState } from 'react'
import { Settings2 } from 'lucide-react'
import { Popover, RadioGroup } from 'radix-ui'

import { Button } from '@/components/ui/button'

type Theme = 'light' | 'dark' | 'system'

const options: { value: Theme; label: string }[] = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '系统' },
]

export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('poeticus-theme')
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  })
  const animationTimer = useRef<number | null>(null)
  const initialized = useRef(false)

  useLayoutEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')

    function applyTheme() {
      const isDark = theme === 'dark' || (theme === 'system' && media.matches)
      const root = document.documentElement
      if (root.classList.contains('dark') === isDark) return

      if (animationTimer.current !== null) window.clearTimeout(animationTimer.current)
      root.classList.remove('theme-transition')
      const canAnimate =
        initialized.current && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      if (canAnimate) root.classList.add('theme-transition')
      root.classList.toggle('dark', isDark)

      if (canAnimate) {
        animationTimer.current = window.setTimeout(() => {
          root.classList.remove('theme-transition')
          animationTimer.current = null
        }, 240)
      }
    }

    applyTheme()
    initialized.current = true
    media.addEventListener('change', applyTheme)
    return () => {
      media.removeEventListener('change', applyTheme)
      if (animationTimer.current !== null) window.clearTimeout(animationTimer.current)
      document.documentElement.classList.remove('theme-transition')
    }
  }, [theme])

  function changeTheme(next: Theme) {
    setTheme(next)
    localStorage.setItem('poeticus-theme', next)
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button type="button" variant="ghost" size="sm" aria-label="外观设置">
          <Settings2 className="size-4" aria-hidden="true" />
          设置
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 w-60 rounded-md border border-border bg-popover p-4 text-popover-foreground shadow-md outline-none"
        >
          <p className="text-sm font-medium">外观</p>
          <RadioGroup.Root
            value={theme}
            onValueChange={(value) => changeTheme(value as Theme)}
            aria-label="颜色主题"
            className="mt-3 grid grid-cols-3 gap-1 rounded-md bg-muted/60 p-1"
          >
            {options.map((option) => (
              <RadioGroup.Item
                key={option.value}
                value={option.value}
                className={
                  'rounded-sm px-2 py-1.5 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ' +
                  (theme === option.value
                    ? 'bg-background font-medium text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground')
                }
              >
                {option.label}
              </RadioGroup.Item>
            ))}
          </RadioGroup.Root>
          <p className="mt-3 text-xs text-muted-foreground">系统模式随设备外观自动切换</p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
