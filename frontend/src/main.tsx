import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles/tokens.css";
import "./styles.css";
import "./styles/console.css";
import "./styles/app.css";
import "./styles/hardware.css";
import "./styles/console-studio.css";
import "./styles/refinements.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("缺少 #root 挂载点");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
