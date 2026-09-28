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

type ChatMessage = {
  question: string;
  quote: string | null;
};

function App() {
  const poemRef = useRef<HTMLParagraphElement>(null);
  const [selected, setSelected] = useState<SelectedText | null>(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

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

  function handleSend() {
    if (!question.trim()) return;

    setMessages((previous) => [
      ...previous,
      {
        question: question.trim(),
        quote: selected?.text ?? null,
      },
    ]);

    setQuestion("");
    setSelected(null);
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
          {messages.length === 0 && (
            <p style={{ opacity: 0.6 }}>选中左侧的诗句，开始讨论。</p>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              style={{
                padding: 12,
                marginBottom: 16,
                borderRadius: 8,
                background: "rgba(120, 140, 160, 0.15)",
              }}
            >
              {message.quote && (
                <blockquote
                  style={{
                    margin: "0 0 12px",
                    paddingLeft: 12,
                    borderLeft: "3px solid #888",
                    opacity: 0.7,
                  }}
                >
                  {message.quote}
                </blockquote>
              )}

              <p>{message.question}</p>
            </div>
          ))}
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
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />

          <button
            type="button"
            onClick={handleSend}
            disabled={!question.trim()}
          >
            发送
          </button>
        </div>
      </aside>
    </main>
  );
}

export default App;
