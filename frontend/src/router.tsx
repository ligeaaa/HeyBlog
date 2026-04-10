import { createBrowserRouter } from "react-router-dom";
import { AdminLayout } from "./shell/AdminLayout";
import { PublicLayout } from "./shell/PublicLayout";
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
    element: <PublicLayout />,
    children: [
      { index: true, element: <StatsPage /> },
      { path: "stats", element: <StatsPage /> },
      { path: "blogs", element: <BlogsPage /> },
      { path: "blogs/:blogId", element: <BlogDetailPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "graph", element: <GraphPage /> },
      { path: "about", element: <AboutPage /> },
    ],
  },
  {
    path: "/admin",
    element: <AdminLayout />,
    children: [
      { index: true, element: <ControlPage /> },
      { path: "control", element: <ControlPage /> },
      { path: "runtime/progress", element: <RuntimeProgressPage /> },
      { path: "runtime/current", element: <CurrentRuntimePage /> },
      { path: "blog-labeling", element: <BlogLabelingPage /> },
    ],
  },
]);
