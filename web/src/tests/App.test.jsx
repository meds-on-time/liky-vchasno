import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "../App.jsx";
import { getSession, saveSession } from "../session.js";
import { mockFetch, OK_EXCHANGE } from "./helpers.js";

describe("App", () => {
  it("link from the bot logs in and removes the token from the address", async () => {
    mockFetch(OK_EXCHANGE);
    window.history.replaceState(null, "", "/login?token=abc");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Вітаємо, Олена!" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(window.location.search).toBe("");
  });

  it("without a session asks to log in through the bot", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Вхід до веб-кабінету" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Вийти" })).not.toBeInTheDocument();
  });

  it("«Вийти» clears the session", async () => {
    saveSession({ session: "s", expiresAt: "2099-01-01T00:00:00Z", user: { name: "Олена" } });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Вийти" }));

    expect(screen.getByRole("heading", { name: "Ви вийшли з кабінету" })).toBeInTheDocument();
    expect(getSession()).toBeNull();
  });
});
