import { vi } from "vitest";

/** Replace window.fetch with a function returning the given responses one by one. */
export function mockFetch(...responses) {
  const fn = vi.fn();
  for (const r of responses) {
    if (r instanceof Error) {
      fn.mockRejectedValueOnce(r);
    } else {
      fn.mockResolvedValueOnce({
        ok: r.status >= 200 && r.status < 300,
        status: r.status,
        json: async () => r.body ?? {},
      });
    }
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const OK_EXCHANGE = {
  status: 200,
  body: {
    session: "session-123",
    expires_at: "2099-01-01T00:00:00Z",
    user: { id: 5, name: "Олена" },
  },
};

export const PATIENTS_RESPONSE = {
  status: 200,
  body: {
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
        medications: [{ id: 12, name: "Аспірин", dose: "75 мг", times: [], end_date: null }],
      },
    ],
  },
};
