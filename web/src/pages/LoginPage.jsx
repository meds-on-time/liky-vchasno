import { useCallback, useEffect, useRef, useState } from "react";

import { exchangeToken } from "../api.js";
import { LOGIN_ERRORS } from "../messages.js";
import { saveSession } from "../session.js";

/** /login?token=… – the page the bot link opens. */
export default function LoginPage({ token, onSuccess }) {
  const [error, setError] = useState(token ? null : "missing_token");
  // The token is one-time: React StrictMode runs effects twice in dev,
  // so remember that the exchange has already started.
  const started = useRef(false);

  const login = useCallback(async () => {
    setError(null);
    try {
      const session = await exchangeToken(token);
      saveSession(session);
      onSuccess(session);
    } catch (e) {
      setError(LOGIN_ERRORS[e.code] ? e.code : "server_error");
    }
  }, [token, onSuccess]);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    login();
  }, [token, login]);

  if (!error) {
    return (
      <section className="card" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Входимо до кабінету…</p>
      </section>
    );
  }

  const message = LOGIN_ERRORS[error];
  return (
    <section className="card card-error" role="alert">
      <h1>{message.title}</h1>
      <p>{message.hint}</p>
      {message.retry && (
        <button type="button" className="button" onClick={login}>
          Спробувати ще раз
        </button>
      )}
    </section>
  );
}
