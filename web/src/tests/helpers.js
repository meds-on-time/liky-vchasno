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
