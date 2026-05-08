import { BrowserRouter as Router, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { Activity, Zap, Map, LayoutDashboard } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import PowerTree from './pages/PowerTree';
import PlantLayout from './pages/PlantLayout';
import './index.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <aside className="sidebar">
          <h1>
            <Activity className="text-accent-primary" size={28} />
            Ball Mill Monitor
          </h1>
          <nav className="nav-links">
            <NavLink to="/power-tree" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Zap size={20} />
              Power Distribution
            </NavLink>
            <NavLink to="/dashboard" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <LayoutDashboard size={20} />
              Historical Data
            </NavLink>
            <NavLink to="/layout" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Map size={20} />
              Plant Layout
            </NavLink>
          </nav>
        </aside>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Navigate to="/power-tree" replace />} />
            <Route path="/power-tree" element={<PowerTree />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/layout" element={<PlantLayout />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
