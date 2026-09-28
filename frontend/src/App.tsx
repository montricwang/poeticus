
import { useRef, useState } from "react";

const poem = `风卷珠帘自上钩，萧萧乱叶报新秋。
独携纤手上高楼。

缺月向人舒窈窕，三星当户照绸缪。
香生雾縠见纤柔。`;

function App() {
  const poemRef = useRef<HTMLParagraphElement>(null);
  const [selected, setSelected] = useState("");

  function handleSelection() {
    const selection = window.getSelection();

    if (!selection || selection.isCollapsed) {
      return;
    }

    const range = selection.getRangeAt(0);
    const textNode = poemRef.current?.firstChild;

    // 目前原文只有一个文本节点
    if (
      range.startContainer !== textNode ||
      range.endContainer !== textNode
    ) {
      return;
    }

    const start = range.startOffset;
    const end = range.endOffset;

    setSelected(poem.slice(start, end));

    console.log("选中范围：", start, end);
  }

  return (
    <main style={{ maxWidth: 680, margin: "0 auto", padding: 32 }}>
      <h1>Poeticus</h1>

      <article>
        <h2>浣溪沙</h2>
        <p
          ref={poemRef}
          onMouseUp={handleSelection}
          style={{ whiteSpace: "pre-line", lineHeight: 2.5, fontSize: 20 }}
        >
          {poem}
        </p>
      </article>

      {selected && (
        <section>
          <h3>当前选中的文字</h3>
          <p>{selected}</p>
        </section>
      )}
    </main>
  );
}

export default App;
