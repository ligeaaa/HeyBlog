import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AboutPage } from "./pages/AboutPage";
import { AdminPage } from "./pages/AdminPage";
import { FilterStatsPage } from "./pages/FilterStatsPage";
import { HomePage } from "./pages/HomePage";
import { RandomBlogPage } from "./pages/RandomBlogPage";
import { VisualizationPage } from "./pages/VisualizationPage";

/**
 * Mount the routed frontend shell.
 *
 * @returns The application router plus shared toast outlet.
 */
export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/random" element={<RandomBlogPage />} />
        <Route path="/visualization" element={<VisualizationPage />} />
        <Route path="/filter-stats" element={<FilterStatsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
