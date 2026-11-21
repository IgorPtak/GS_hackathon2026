import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { AppLayout } from "./components/layout/AppLayout";
import { PRODUCT_NAME } from "./lib/brand";
import { applyUrlOverrides } from "./lib/urlOverrides";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("index.html has no #root element");
}

applyUrlOverrides();
document.title = PRODUCT_NAME;

createRoot(rootElement).render(
  <StrictMode>
    <AppLayout />
  </StrictMode>,
);
