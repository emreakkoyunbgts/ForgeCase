import { NavLink } from 'react-router-dom';
import './Sidebar.css';

export default function Sidebar() {
  return <nav className="sidebar" aria-label="Main navigation">
    <h2>CaseForge</h2>
    <ul>
      <li><NavLink to="/" end>Workbench</NavLink></li>
      <li><NavLink to="/engagements">Engagements</NavLink></li>
      <li><NavLink to="/query">Find a source</NavLink></li>
    </ul>
  </nav>;
}
