import { describe, expect, it } from "vitest";

import { exchangeToken } from "../api.js";
import { mockFetch, OK_EXCHANGE } from "./helpers.js";

describe("exchangeToken (POST /auth/exchange)", () => {
  it("sends the token and returns the session", async () => {
    const fetch = mockFetch(OK_EXCHANGE);

    const result = await exchangeToken("abc");

    expect(result).toEqual({
      session: "session-123",
      expiresAt: "2099-01-01T00:00:00Z",
      user: { id: 5, name: "Олена" },
    });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/auth/exchange");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ token: "abc" });
  });

  it.each([
    ["Token expired", "token_expired"],
    [{ code: "token_expired", message: "Посилання застаріло" }, "token_expired"],
    ["Token already used", "token_used"],
    [{ code: "token_used" }, "token_used"],
    ["Invalid token", "token_invalid"],
  ])("401 with detail %j -> %s", async (detail, code) => {
    mockFetch({ status: 401, body: { detail } });
    await expect(exchangeToken("abc")).rejects.toMatchObject({ code, status: 401 });
  });

  it("server error -> server_error", async () => {
    mockFetch({ status: 500, body: {} });
    await expect(exchangeToken("abc")).rejects.toMatchObject({ code: "server_error" });
  });

  it("no connection -> network", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    await expect(exchangeToken("abc")).rejects.toMatchObject({ code: "network" });
  });
});
