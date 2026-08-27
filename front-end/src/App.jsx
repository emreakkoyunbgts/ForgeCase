import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './Sidebar';
import UploadRecord from './UploadRecord';
import Engagments from "./Engagements.jsx";
import EngagementDetail from "./EngagementDetail.jsx";
import Query from "./Query.jsx";
import Analyze from "./Analyze.jsx";
import './App.css';

function Home() {
  return <h1>Welcome to the Home Page</h1>;
}

function BlankPage() {
  return <h1>This is a Blank Page</h1>;
}

function App() {
  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/upload-record" element={<UploadRecord />} />
          <Route path="/engagments" element={<Engagments/>} />
          <Route path="/engagements" element={<Engagments/>} />
          <Route path="/engagements/:id" element={<EngagementDetail/>} />
          <Route path="/blank" element={<BlankPage />} />
          <Route path="/query" element={<Query />} />
          <Route path="/analyze" element={<Analyze />} />

        </Routes>
      </div>
    </div>
  );
}

export default App;
