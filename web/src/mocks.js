// Test data for working without the backend (VITE_USE_MOCKS=true).
// Remove once Masha's endpoints are in main.
import { ApiError } from "./errors.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function mockSession(session, name) {
  const expires = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  return { session, expiresAt: expires.toISOString(), user: { id: 1, name } };
}

export async function mockExchange(token) {
  await wait(400);
  if (token === "demo") return mockSession("mock-session", "Тарас");
  if (token === "demo-empty") return mockSession("mock-empty", "Тарас");
  if (token === "expired") throw new ApiError("token_expired", 401);
  if (token === "used") throw new ApiError("token_used", 401);
  throw new ApiError("token_invalid", 401);
}

// Same shape as GET /contacts/patients (web/README.md)
const PATIENTS = {
  patients: [
    {
      id: 7,
      name: "Олена",
      medications: [
        {
          id: 3,
          name: "Сертралін",
          dose: "50 мг",
          form: "таблетка",
          times: ["20:00", "08:00"],
          end_date: "2026-11-30",
        },
        { id: 4, name: "Вітамін D", dose: "2000 МО", form: null, times: ["09:00"], end_date: null },
      ],
    },
    {
      id: 9,
      name: "Петро",
      medications: [
        {
          id: 11,
          name: "Метформін",
          dose: "500 мг",
          form: "таблетка",
          times: ["08:30", "13:30", "19:30"],
          end_date: null,
        },
        { id: 12, name: "Аспірин", dose: "75 мг", form: null, times: [], end_date: null },
      ],
    },
  ],
};

export async function mockPatients(session) {
  await wait(400);
  if (session === "mock-empty") return { patients: [] };
  if (session === "mock-session") return PATIENTS;
  throw new ApiError("unauthorized", 401);
}
