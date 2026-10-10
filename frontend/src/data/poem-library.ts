/** /api/poems 返回的是轻量目录；只有按 UUID 查询时才获取完整正文。 */
export type PoemSummary = {
  id: string
  source_order: number
  collection: string
  author: string | null
  cipai: string | null
  title: string | null
  yusheng_title: string | null
  incipit: string
  review_status: string
}

export type Poem = Omit<PoemSummary, 'incipit'> & {
  body_segments: string[]
  prefaces: string[]
  text_version: number
}

export type PoemPage = {
  items: PoemSummary[]
  total: number
  limit: number
  offset: number
}

export type PoemNeighbors = {
  previous_id: string | null
  next_id: string | null
}

export type PoemContext = {
  id: string
  title: string
  author: string | null
  dynasty: string | null
  review_status: string
}

export type PoemFilters = {
  q?: string
  author?: string
  cipai?: string
  limit: number
  offset: number
}

/** 题录只组合展示字段，不改变作品的词牌、寓声与词题。 */
export function poemTitle(work: Pick<PoemSummary, 'cipai' | 'yusheng_title' | 'title'>): string {
  const tune = work.yusheng_title
    ? work.cipai
      ? `${work.yusheng_title}（${work.cipai}）`
      : work.yusheng_title
    : work.cipai || '未题作品'
  return work.title ? `${tune}·${work.title}` : tune
}

/** 目录第一行仅显示题录；正文首句固定放在第二行。 */
export function poemLabel(work: PoemSummary): string {
  return poemTitle(work)
}

export function poemIncipit(work: Pick<PoemSummary, 'incipit'>): string {
  // 截取首个主要句读前的短句。不要改变正文或把句子误归为词题。
  const firstPhrase = work.incipit.split(/[，,。.!！?？；;\r\n]/, 1)[0].trim()
  return Array.from(firstPhrase).slice(0, 28).join('') || '暂无正文'
}

/** 这一份字符串同时进入阅读器、聊天、赏析及原文选区校验。 */
export function poemText(work: Poem): string {
  return work.body_segments.join('\n\n')
}

export function poemContext(work: Poem): PoemContext {
  return {
    id: work.id,
    title: poemTitle(work),
    author: work.author,
    // 当前数据库没有可靠的逐首朝代字段，不凭词集补猜。
    dynasty: null,
    review_status: work.review_status,
  }
}

async function readJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body ? body.detail : null
    throw new Error(typeof detail === 'string' ? detail : `作品加载失败（HTTP ${response.status}）`)
  }
  return (await response.json()) as T
}

export async function fetchPoemPage(filters: PoemFilters, signal?: AbortSignal): Promise<PoemPage> {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  })
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.author?.trim()) params.set('author', filters.author.trim())
  if (filters.cipai?.trim()) params.set('cipai', filters.cipai.trim())
  return readJson<PoemPage>(`/api/poems?${params}`, signal)
}

export function fetchPoem(id: string, signal?: AbortSignal): Promise<Poem> {
  return readJson<Poem>(`/api/poems/${encodeURIComponent(id)}`, signal)
}


/** 前后首按 source_order 邻接，独立于目录分页和搜索条件。 */
export function fetchPoemNeighbors(id: string, signal?: AbortSignal): Promise<PoemNeighbors> {
  return readJson<PoemNeighbors>(`/api/poems/${encodeURIComponent(id)}/neighbors`, signal)
}
