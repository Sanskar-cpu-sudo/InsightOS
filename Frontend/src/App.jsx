import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppHeader from "./components/AppHeader";
import AppFooter from "./components/AppFooter";
import Dashboard from "./pages/Dashboard";
import AskPage from "./pages/AskPage";
import HistoryPage from "./pages/HistoryPage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <AppHeader />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/ask" element={<AskPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/upload" element={<UploadPage />} />
        </Routes>
        <AppFooter />
      </div>
    </BrowserRouter>
  );
}
