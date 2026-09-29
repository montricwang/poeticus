import catalog from "./poems/index.json";

export type PoemSource = {
  kind: string;
  url: string;
};

export type Poem = {
  id: string;
  language: string;
  dynasty: string | null;
  author: string | null;
  tune: string;
  subtitle: string | null;
  title: string;
  incipit: string;
  preface: string | null;
  stanzas: string[][];
  sources: PoemSource[];
  review_status: string;
  editorial_notes: string[];
};

/** 进入 AI 上下文的最小作品元数据，与后端 PoemContext 对齐。 */
export type PoemContext = {
  id: string;
  title: string;
  author: string | null;
  dynasty: string | null;
  review_status: string;
};

const records = import.meta.glob<Poem>(
  ["./poems/*.json", "!./poems/index.json"],
  { eager: true, import: "default" },
);

export const poems: Poem[] = catalog.map((entry) => {
  const work = records[`./poems/${entry.file}`];

  if (!work) {
    throw new Error(`未找到作品数据：${entry.file}`);
  }

  if (work.id !== entry.id) {
    throw new Error(`作品目录与正文 ID 不一致：${entry.file}`);
  }

  return work;
});

// 阅读区、聊天和整首赏析只从这里读取正文，保证字符 offset 一致。
export function poemText(work: Poem): string {
  return work.stanzas.map((stanza) => stanza.join("\n")).join("\n\n");
}

export function poemContext(work: Poem): PoemContext {
  return {
    id: work.id,
    title: work.title,
    author: work.author,
    dynasty: work.dynasty,
    review_status: work.review_status,
  };
}
