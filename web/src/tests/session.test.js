import { describe, expect, it } from "vitest";

import { clearSession, getSession, saveSession } from "../session.js";

const SESSION = { session: "s", expiresAt: "2026-11-20T10:00:00Z", user: { name: "Олена" } };

describe("session", () => {
  it("is saved and read back", () => {
    saveSession(SESSION);
    expect(getSession(new Date("2026-11-19T10:00:00Z"))).toEqual(SESSION);
  });

  it("expired session is dropped", () => {
    saveSession(SESSION);
    expect(getSession(new Date("2026-11-20T10:00:01Z"))).toBeNull();
    expect(getSession(new Date("2026-11-19T10:00:00Z"))).toBeNull();
  });

  it("clearSession logs out", () => {
    saveSession(SESSION);
    clearSession();
    expect(getSession()).toBeNull();
  });

  it("broken data in storage is ignored", () => {
    localStorage.setItem("liky_vchasno_session", "{not json");
    expect(getSession()).toBeNull();
  });
});
