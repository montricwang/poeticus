/**
 * Independent short rule below the chat/analysis view switch.
 * A whole CSS pixel avoids the varying two-pixel antialiasing of a 1.5px rule
 * without changing any of the other editorial dividers.
 */
export function ViewToolbarDivider() {
  return <div aria-hidden="true" className="mb-3 h-px w-[7.75rem] shrink-0 bg-border/80" />
}
