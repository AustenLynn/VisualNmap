import { NavLink, Route, Routes } from "react-router-dom";
import { StatusBanner } from "./components/StatusBanner";
import { useAppData } from "./hooks/useAppData";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";

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
          <Route path="/guided" element={<Placeholder name="Guided" />} />
          <Route path="/builder" element={<Placeholder name="Builder" />} />
          <Route path="/scans/:id" element={<Placeholder name="Scan" />} />
          <Route path="/history" element={<Placeholder name="History" />} />
        </Routes>
      </main>
    </div>
  );
}
