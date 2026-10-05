// Responsive mode boundaries intentionally align with Tailwind's lg and 2xl defaults.
// They switch interaction models, so JS behavior and CSS breakpoints must stay in sync.
export const WIDE_DISCUSSION_MIN_WIDTH = 1024;
export const PERSISTENT_CATALOG_MIN_WIDTH = 1536;

export const WIDE_DISCUSSION_MEDIA =
  `(min-width: ${WIDE_DISCUSSION_MIN_WIDTH}px)`;
export const PERSISTENT_CATALOG_MEDIA =
  `(min-width: ${PERSISTENT_CATALOG_MIN_WIDTH}px)`;
export const OVERLAY_CATALOG_MEDIA =
  `(max-width: ${PERSISTENT_CATALOG_MIN_WIDTH - 1}px)`;
