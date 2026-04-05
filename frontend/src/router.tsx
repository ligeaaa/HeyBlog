import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./shell/AppLayout";
import { AboutPage } from "./pages/AboutPage";
import { BlogDetailPage } from "./pages/BlogDetailPage";
import { BlogLabelingPage } from "./pages/BlogLabelingPage";
import { BlogsPage } from "./pages/BlogsPage";
import { ControlPage } from "./pages/ControlPage";
import { GraphPage } from "./pages/GraphPage";
import { CurrentRuntimePage } from "./pages/CurrentRuntimePage";
import { RuntimeProgressPage } from "./pages/RuntimeProgressPage";
import { SearchPage } from "./pages/SearchPage";
import { StatsPage } from "./pages/StatsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <StatsPage /> },
      { path: "blogs", element: <BlogsPage /> },
      { path: "blog-labeling", element: <BlogLabelingPage /> },
      { path: "blogs/:blogId", element: <BlogDetailPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "graph", element: <GraphPage /> },
      { path: "runtime/progress", element: <RuntimeProgressPage /> },
      { path: "runtime/current", element: <CurrentRuntimePage /> },
      { path: "stats", element: <StatsPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "control", element: <ControlPage /> },
    ],
  },
]);
