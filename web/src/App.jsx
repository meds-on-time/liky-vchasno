import { useCallback, useState } from "react";

import { isMockMode } from "./api.js";
import HomePage from "./pages/HomePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SignedOutPage from "./pages/SignedOutPage.jsx";
import { clearSession, getSession } from "./session.js";

function go(path) {
  window.history.replaceState(null, "", path);
}

export default function App() {
  const [path] = useState(() => window.location.pathname);
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token"));
  const [session, setSession] = useState(() => getSession());
  const [justLoggedOut, setJustLoggedOut] = useState(false);
  const [loggingIn, setLoggingIn] = useState(path === "/login");

  const handleLogin = useCallback((newSession) => {
    // Drop the used token from the address bar
    go("/");
    setSession(newSession);
    setLoggingIn(false);
  }, []);

  function handleLogout() {
    clearSession();
    setSession(null);
    setJustLoggedOut(true);
    go("/");
  }

  let page;
  if (loggingIn) {
    page = <LoginPage token={token} onSuccess={handleLogin} />;
  } else if (session) {
    page = <HomePage user={session.user} />;
  } else {
    page = <SignedOutPage justLoggedOut={justLoggedOut} />;
  }

  return (
    <div className="layout">
      <header className="header">
        <div className="brand">
          <span className="logo" aria-hidden="true">
            Л
          </span>
          <span>
            Ліки вчасно <span className="muted">· веб-кабінет</span>
          </span>
        </div>
        {session && !loggingIn && (
          <div className="user">
            {session.user?.name && <span className="muted">{session.user.name}</span>}
            <button type="button" className="button button-secondary" onClick={handleLogout}>
              Вийти
            </button>
          </div>
        )}
      </header>
      {isMockMode() && <p className="mock-banner">Тестовий режим: дані не з сервера</p>}
      <main className="main">{page}</main>
    </div>
  );
}
