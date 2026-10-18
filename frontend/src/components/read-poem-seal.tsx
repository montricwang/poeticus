/** 朱文式阅读入口：普通状态红字红框，悬停/按下时朱红填充。 */
export function ReadPoemSeal({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="home-read-seal inline-flex h-auto w-6 shrink-0 items-center justify-center rounded-sm border-2 border-editorial-red bg-transparent px-1 py-1.5 text-xs font-semibold leading-none text-editorial-red transition-colors hover:bg-editorial-red hover:text-background active:bg-editorial-red active:text-background focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-editorial-red disabled:cursor-not-allowed disabled:opacity-50"
      aria-label="读这首词"
    >
      {/* 汉字各自横排，纵向堆叠；不使用竖排字形度量。 */}
      <span aria-hidden="true" className="home-read-seal-glyphs flex flex-col items-center">
        <span>读</span>
        <span>这</span>
        <span>首</span>
        <span>词</span>
      </span>
    </button>
  )
}
