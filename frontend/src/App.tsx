import { NavLink, Route, Routes } from "react-router-dom";
import { StatusBanner } from "./components/StatusBanner";
import { useAppData } from "./hooks/useAppData";
import { Builder } from "./pages/Builder";
import { Guided } from "./pages/Guided";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Scan } from "./pages/Scan";

export function App() {
  const { status } = useAppData();
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">VisualNmap</NavLink>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/guided">Guided</NavLink>
          <NavLink to="/builder">Builder</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <span className={`badge ${status.can_raw ? "badge-ok" : "badge-warn"}`} title="Whether 🔒 options are available">
          {status.can_raw ? "🔒 unlocked" : "no root"}
        </span>
      </header>
      <StatusBanner status={status} />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/guided" element={<Guided />} />
          <Route path="/builder" element={<Builder />} />
          <Route path="/scans/:id" element={<Scan />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
