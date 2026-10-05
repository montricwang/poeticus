import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";

if (new URLSearchParams(window.location.search).get("font") === "kr") {
  document.documentElement.dataset.literaryFont = "kr";
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
