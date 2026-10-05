import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";

const literaryFont = new URLSearchParams(window.location.search).get("font");
if (literaryFont === "sc-variable" || literaryFont === "kr") {
  document.documentElement.dataset.literaryFont = literaryFont;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
