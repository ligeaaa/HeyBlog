import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Navigation } from "./components/Navigation";
import { hasStoredAdminSession } from "./lib/auth";
import { AboutPage } from "./pages/AboutPage";
import { AdminPage } from "./pages/AdminPage";
import { BlogDetailPage } from "./pages/BlogDetailPage";
import { FilterStatsPage } from "./pages/FilterStatsPage";
import { HomePage } from "./pages/HomePage";
import { ProfilePage } from "./pages/ProfilePage";
import { RandomBlogPage } from "./pages/RandomBlogPage";
import { VisualizationPage } from "./pages/VisualizationPage";

function NotFoundPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navigation />
      <main className="mx-auto max-w-3xl px-6 pt-32 text-slate-950">
        <p className="text-sm font-medium text-slate-500">404</p>
        <h1 className="mt-3 text-3xl font-semibold">页面不存在</h1>
      </main>
    </div>
  );
}

function AdminRoute() {
  return hasStoredAdminSession() ? <AdminPage /> : <NotFoundPage />;
}

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
        <Route path="/blogs/:blogId" element={<BlogDetailPage />} />
        <Route path="/random" element={<RandomBlogPage />} />
        <Route path="/visualization" element={<VisualizationPage />} />
        <Route path="/visualization/benchmark" element={<VisualizationPage />} />
        <Route path="/filter-stats" element={<FilterStatsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/admin" element={<AdminRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
