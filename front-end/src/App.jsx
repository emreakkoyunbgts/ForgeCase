import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Workbench from './Workbench';
import Engagements from './Engagements';
import Query from './Query';
import './App.css';

export default function App() {
  return <div className="app-container"><Sidebar /><div className="main-content">
    <Routes>
      <Route path="/" element={<Workbench />} />
      <Route path="/upload-record" element={<Workbench />} />
      <Route path="/engagements/:id" element={<Workbench />} />
      <Route path="/engagements" element={<Engagements />} />
      <Route path="/engagments" element={<Navigate to="/engagements" replace />} />
      <Route path="/query" element={<Query />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </div></div>;
}
