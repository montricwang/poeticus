/** /api/poems 返回的是轻量目录；只有按 UUID 查询时才获取完整正文。 */
export type PoemSummary = {
  id: string;
  source_order: number;
  collection: string;
  author: string | null;
  cipai: string | null;
  title: string | null;
  yusheng_title: string | null;
  incipit: string;
  review_status: string;
};

export type Poem = Omit<PoemSummary, "incipit"> & {
  body_segments: string[];
  prefaces: string[];
  text_version: number;
};

export type PoemPage = {
  items: PoemSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type PoemContext = {
  id: string;
  title: string;
  author: string | null;
  dynasty: string | null;
  review_status: string;
};

export type PoemFilters = {
  q?: string;
  author?: string;
  cipai?: string;
  limit: number;
  offset: number;
};

/** 词牌和题目分别保存；无题目时借首句区分目录中的同调作品。 */
export function poemTitle(work: Pick<PoemSummary, "cipai" | "title">): string {
  return [work.cipai, work.title].filter(Boolean).join("·") || "未题作品";
}

export function poemLabel(work: PoemSummary): string {
  const title = poemTitle(work);
  if (work.title) return title;

  // 无独立词题时，截取第一个主要句读标点前的文字作短标签。
  // 同时兼容中文/英文标点与换行；无句读时才依赖下方长度上限。
  // 这只是目录展示规则，不改变词正文，也不判定词句/上下阕。
  const firstPhrase = work.incipit.split(/[，,。.!！?？；;\r\n]/, 1)[0].trim();
  const shortPhrase = Array.from(firstPhrase).slice(0, 18).join("");
  return shortPhrase ? `${title} · ${shortPhrase}` : title;
}

/** 这一份字符串同时进入阅读器、聊天、赏析及原文选区校验。 */
export function poemText(work: Poem): string {
  return work.body_segments.join("\n\n");
}

export function poemContext(work: Poem): PoemContext {
  return {
    id: work.id,
    title: poemTitle(work),
    author: work.author,
    // 当前数据库没有可靠的逐首朝代字段，不凭词集补猜。
    dynasty: null,
    review_status: work.review_status,
  };
}

async function readJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? body.detail
        : null;
    throw new Error(
      typeof detail === "string" ? detail : `作品加载失败（HTTP ${response.status}）`,
    );
  }
  return (await response.json()) as T;
}

export async function fetchPoemPage(
  filters: PoemFilters,
  signal?: AbortSignal,
): Promise<PoemPage> {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.author?.trim()) params.set("author", filters.author.trim());
  if (filters.cipai?.trim()) params.set("cipai", filters.cipai.trim());
  return readJson<PoemPage>(`/api/poems?${params}`, signal);
}

export function fetchPoem(id: string, signal?: AbortSignal): Promise<Poem> {
  return readJson<Poem>(`/api/poems/${encodeURIComponent(id)}`, signal);
}
