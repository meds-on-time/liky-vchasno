// Calls to the backend (SCRUM-16, SCRUM-31). Contract: web/README.md.
import { ApiError } from "./errors.js";
import { mockExchange, mockPatients } from "./mocks.js";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export function isMockMode() {
  return import.meta.env.VITE_USE_MOCKS === "true";
}

export { ApiError };

// FastAPI returns `detail` either as a string or as {code, message}.
export function errorCodeFrom(status, detail) {
  const raw = typeof detail === "string" ? detail : detail?.code || detail?.message || "";
  if (status === 401 || status === 400 || status === 410) {
    if (/expired|застар|прострочен/i.test(raw)) return "token_expired";
    if (/used|використ/i.test(raw)) return "token_used";
    return "token_invalid";
  }
  return "server_error";
}

/**
 * POST /auth/exchange: swaps the one-time token from the bot link for a session.
 * Returns {session, expiresAt, user}.
 */
export async function exchangeToken(token) {
  if (isMockMode()) return mockExchange(token);

  let response;
  try {
    response = await fetch(`${API_URL}/auth/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
  } catch {
    throw new ApiError("network");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(errorCodeFrom(response.status, data.detail), response.status);
  }
  return {
    session: data.session,
    expiresAt: data.expires_at ?? null,
    user: data.user ?? null,
  };
}

function normalizeMedication(m) {
  return {
    id: m.id,
    name: m.name,
    dose: m.dose ?? "",
    form: m.form ?? null,
    times: [...(m.times ?? [])].sort(),
    endDate: m.end_date ?? null,
  };
}

/** Accepts {patients: [...]} or a bare list, so a small format change does not break the page. */
export function normalizePatients(data) {
  const list = Array.isArray(data) ? data : (data?.patients ?? []);
  return list.map((p) => ({
    id: p.id,
    name: p.name,
    medications: (p.medications ?? []).map(normalizeMedication),
  }));
}

/**
 * GET /contacts/patients: people who invited the logged-in trusted contact,
 * with their medications and intake times (SCRUM-31). 401 -> "unauthorized".
 */
export async function fetchPatients(session) {
  if (isMockMode()) return normalizePatients(await mockPatients(session));

  let response;
  try {
    response = await fetch(`${API_URL}/contacts/patients`, {
      headers: { Authorization: `Bearer ${session}` },
    });
  } catch {
    throw new ApiError("network");
  }

  const data = await response.json().catch(() => ({}));
  if (response.status === 401) throw new ApiError("unauthorized", 401);
  if (!response.ok) throw new ApiError("server_error", response.status);
  return normalizePatients(data);
}
