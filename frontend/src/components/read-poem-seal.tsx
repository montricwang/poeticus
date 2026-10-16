/** 朱文式阅读入口：普通状态红字红框，悬停/按下时朱红填充。 */
export function ReadPoemSeal({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex h-auto w-7 shrink-0 items-center justify-center rounded-sm border-2 border-[#AA381E] bg-transparent px-1 py-0.5 font-sans text-xs font-medium leading-none tracking-[0.18em] text-[#AA381E] transition-colors [writing-mode:vertical-rl] hover:bg-[#AA381E] hover:text-background active:bg-[#AA381E] active:text-background focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#AA381E] disabled:cursor-not-allowed disabled:opacity-50"
    >
      读这首词
    </button>
  )
}
