import { useRef, useState } from "react";

const poem = `风卷珠帘自上钩，萧萧乱叶报新秋。
独携纤手上高楼。

缺月向人舒窈窕，三星当户照绸缪。
香生雾縠见纤柔。`;

type SelectedText = {
  text: string;
  start: number;
  end: number;
};

function App() {
  const poemRef = useRef<HTMLParagraphElement>(null);
  const [selected, setSelected] = useState<SelectedText | null>(null);

  function handleSelection() {
    const selection = window.getSelection();

    if (!selection || selection.isCollapsed) {
      return;
    }

    const range = selection.getRangeAt(0);
    const textNode = poemRef.current?.firstChild;

    if (range.startContainer !== textNode || range.endContainer !== textNode) {
      return;
    }

    const start = range.startOffset;
    const end = range.endOffset;

    setSelected({
      text: poem.slice(start, end),
      start,
      end,
    });
  }

  return (
    <main
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(320px, 0.9fr)",
        gap: 40,
        width: "calc(100vw - 64px)",
        maxWidth: 1100,
        minHeight: 600,
        margin: "32px auto",
      }}
    >
      <article>
        <h1>Poeticus</h1>
        <h2>浣溪沙</h2>

        <p
          ref={poemRef}
          onMouseUp={handleSelection}
          style={{
            whiteSpace: "pre-line",
            lineHeight: 2.5,
            fontSize: 20,
          }}
        >
          {poem}
        </p>
      </article>

      <aside
        style={{
          border: "1px solid #8886",
          borderRadius: 12,
          padding: 24,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <h2>AI 阅读助手</h2>

        <div style={{ flex: 1 }}>
          <p style={{ opacity: 0.6 }}>选中左侧的诗句，开始讨论。</p>
        </div>

        <div>
          {selected && (
            <div
              style={{
                padding: 12,
                marginBottom: 12,
                borderRadius: 8,
                background: "rgba(120, 140, 160, 0.15)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                }}
              >
                <small>引用原文</small>
                <button type="button" onClick={() => setSelected(null)}>
                  ×
                </button>
              </div>

              <p>{selected.text}</p>
            </div>
          )}

          <textarea
            placeholder="针对诗句提出你的问题……"
            rows={3}
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: 12,
              resize: "vertical",
            }}
          />
        </div>
      </aside>
    </main>
  );
}

export default App;
