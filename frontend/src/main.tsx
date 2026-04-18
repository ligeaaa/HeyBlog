import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/index.css";

/**
 * Mount the example-aligned single-page app.
 */
createRoot(document.getElementById("root")!).render(<App />);
