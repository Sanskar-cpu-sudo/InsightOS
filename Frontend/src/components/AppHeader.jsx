const tabs = [
  { id: "dashboard", label: "Dashboard" },
  { id: "ask", label: "Ask AI" },
  { id: "history", label: "History" },
  { id: "upload", label: "Upload" },
];

function AppHeader({ activeTab, setActiveTab }) {
  return (
    <header className="topbar">
      <div className="brand-block">
        <div className="brand-mark">IO</div>
        <div>
          <p className="eyebrow">Autonomous Intelligence</p>
          <h1>InsightOS</h1>
        </div>
      </div>

      <nav className="tabs" aria-label="Main navigation">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={activeTab === tab.id ? "tab active" : "tab"}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </header>
  );
}

export default AppHeader;
