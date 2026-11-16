import { useCallback, useState } from "react";

import { isMockMode } from "./api.js";
import LoginPage from "./pages/LoginPage.jsx";
import PatientsPage from "./pages/PatientsPage.jsx";
import SignedOutPage from "./pages/SignedOutPage.jsx";
import { clearSession, getSession } from "./session.js";

function go(path) {
  window.history.replaceState(null, "", path);
}

export default function App() {
  const [path] = useState(() => window.location.pathname);
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token"));
  const [session, setSession] = useState(() => getSession());
  // Why there is no session: "logout" after «Вийти», "expired" when the server rejected it
  const [signedOutReason, setSignedOutReason] = useState(null);
  const [loggingIn, setLoggingIn] = useState(path === "/login");

  const handleLogin = useCallback((newSession) => {
    // Drop the used token from the address bar
    go("/");
    setSession(newSession);
    setLoggingIn(false);
  }, []);

  const signOut = useCallback((reason) => {
    clearSession();
    setSession(null);
    setSignedOutReason(reason);
    go("/");
  }, []);

  const handleUnauthorized = useCallback(() => signOut("expired"), [signOut]);

  let page;
  if (loggingIn) {
    page = <LoginPage token={token} onSuccess={handleLogin} />;
  } else if (session) {
    page = <PatientsPage session={session.session} onUnauthorized={handleUnauthorized} />;
  } else {
    page = <SignedOutPage reason={signedOutReason} />;
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
            <button type="button" className="button button-secondary" onClick={() => signOut("logout")}>
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
