import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./shell/AppLayout";
import { AboutPage } from "./pages/AboutPage";
import { BlogsPage } from "./pages/BlogsPage";
import { ControlPage } from "./pages/ControlPage";
import { GraphPage } from "./pages/GraphPage";
import { CurrentRuntimePage } from "./pages/CurrentRuntimePage";
import { StatsPage } from "./pages/StatsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <StatsPage /> },
      { path: "blogs", element: <BlogsPage /> },
      { path: "graph", element: <GraphPage /> },
      { path: "runtime/current", element: <CurrentRuntimePage /> },
      { path: "stats", element: <StatsPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "control", element: <ControlPage /> },
    ],
  },
]);
