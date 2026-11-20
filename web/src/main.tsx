import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { AppLayout } from "./components/layout/AppLayout";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("index.html has no #root element");
}

createRoot(rootElement).render(
  <StrictMode>
    <AppLayout />
  </StrictMode>,
);
