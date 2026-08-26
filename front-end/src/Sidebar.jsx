import React from 'react';
import { Link } from 'react-router-dom';
import './Sidebar.css';

function Sidebar() {
  return (
    <div className="sidebar">
      <h2>Menu</h2> {/* Changed 'Navigation' to 'Menu' */}
        <ul>
            <li><Link to="/">Home</Link></li>
            <li><Link to="/upload-record">Upload Record</Link></li>
            <li><Link to={"/engagments"}>Engagments</Link></li>
            <li><Link to="/query">Query</Link></li>
            <li><Link to="/blank">Blank Page</Link></li>
        </ul>
    </div>
  );
}

export default Sidebar;
