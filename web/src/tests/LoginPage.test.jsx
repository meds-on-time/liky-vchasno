import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "../pages/LoginPage.jsx";
import { getSession } from "../session.js";
import { mockFetch, OK_EXCHANGE } from "./helpers.js";

describe("LoginPage", () => {
  it("exchanges the token, saves the session and reports success", async () => {
    mockFetch(OK_EXCHANGE);
    const onSuccess = vi.fn();

    render(<LoginPage token="abc" onSuccess={onSuccess} />);

    expect(screen.getByText("Входимо до кабінету…")).toBeInTheDocument();
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(onSuccess.mock.calls[0][0].user.name).toBe("Олена");
    expect(getSession().session).toBe("session-123");
  });

  it("expired link: clear text and how to get a new one", async () => {
    mockFetch({ status: 401, body: { detail: "Token expired" } });

    render(<LoginPage token="old" onSuccess={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Посилання застаріло" })).toBeInTheDocument();
    expect(screen.getByText(/\/web/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(getSession()).toBeNull();
  });

  it("used link", async () => {
    mockFetch({ status: 401, body: { detail: { code: "token_used" } } });
    render(<LoginPage token="again" onSuccess={vi.fn()} />);
    expect(
      await screen.findByRole("heading", { name: "Це посилання вже використано" }),
    ).toBeInTheDocument();
  });

  it("no token in the link: no request is sent", () => {
    const fetch = mockFetch();
    render(<LoginPage token={null} onSuccess={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "У посиланні немає коду входу" })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("one-time token is sent only once even in StrictMode", async () => {
    const fetch = mockFetch(OK_EXCHANGE, OK_EXCHANGE);
    const onSuccess = vi.fn();

    render(
      <StrictMode>
        <LoginPage token="abc" onSuccess={onSuccess} />
      </StrictMode>,
    );

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("network error: retry button tries again", async () => {
    mockFetch(new TypeError("Failed to fetch"), OK_EXCHANGE);
    const onSuccess = vi.fn();
    render(<LoginPage token="abc" onSuccess={onSuccess} />);

    const retry = await screen.findByRole("button", { name: "Спробувати ще раз" });
    await userEvent.click(retry);

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
  });
});
