import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";

const literaryFont =
  new URLSearchParams(window.location.search).get("font") === "kr" ? "kr" : "sc";
document.documentElement.dataset.literaryFont = literaryFont;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// 先让应用完成首屏渲染，再加载当前需要的一套大型 CJK WebFont。
// 这样字体实验不会阻塞 React 启动，也不会让 SC / KR 两套字体同时进入首屏请求。
window.requestAnimationFrame(() => {
  if (literaryFont === "kr") {
    void import("@fontsource-variable/noto-serif-kr");
  } else {
    void import("@fontsource-variable/noto-serif-sc");
  }
});
