// The session lives in localStorage of this browser only.
const KEY = "liky_vchasno_session";

export function saveSession(session) {
  try {
    localStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    // private mode or storage blocked: the user stays logged in until reload
  }
}

export function getSession(now = new Date()) {
  try {
    const session = JSON.parse(localStorage.getItem(KEY));
    if (!session?.session) return null;
    if (session.expiresAt && new Date(session.expiresAt) <= now) {
      clearSession();
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // nothing to clear
  }
}
