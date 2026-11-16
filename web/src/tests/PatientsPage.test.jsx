import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PatientsPage, { formatDate } from "../pages/PatientsPage.jsx";
import { mockFetch, PATIENTS_RESPONSE } from "./helpers.js";

describe("PatientsPage", () => {
  it("shows each person with medications, dose, times and course end", async () => {
    const fetch = mockFetch(PATIENTS_RESPONSE);

    render(<PatientsPage session="session-123" onUnauthorized={vi.fn()} />);

    const olena = await screen.findByRole("region", { name: "Олена" });
    expect(within(olena).getByText("Сертралін")).toBeInTheDocument();
    expect(within(olena).getByText("50 мг, таблетка")).toBeInTheDocument();
    const times = within(olena).getByRole("list", { name: "Час прийому: Сертралін" });
    expect(within(times).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "08:00",
      "20:00",
    ]);
    expect(within(olena).getByText("Курс до 30.11.2026")).toBeInTheDocument();
    expect(within(olena).getByText("Без кінцевої дати")).toBeInTheDocument();

    const petro = screen.getByRole("region", { name: "Петро" });
    expect(within(petro).getByText("Час прийому не задано")).toBeInTheDocument();

    expect(fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer session-123");
  });

  it("empty state when nobody has invited you", async () => {
    mockFetch({ status: 200, body: { patients: [] } });
    render(<PatientsPage session="s" onUnauthorized={vi.fn()} />);
    expect(
      await screen.findByRole("heading", { name: "Вас ще ніхто не запросив" }),
    ).toBeInTheDocument();
  });

  it("page is read-only: no buttons or inputs", async () => {
    mockFetch(PATIENTS_RESPONSE);
    render(<PatientsPage session="s" onUnauthorized={vi.fn()} />);
    await screen.findByRole("region", { name: "Олена" });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("401 from the server ends the session", async () => {
    mockFetch({ status: 401, body: { detail: "Not authenticated" } });
    const onUnauthorized = vi.fn();
    render(<PatientsPage session="old" onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledOnce());
  });

  it("server error: retry loads again", async () => {
    mockFetch({ status: 500, body: {} }, PATIENTS_RESPONSE);
    render(<PatientsPage session="s" onUnauthorized={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Спробувати ще раз" }));

    expect(await screen.findByRole("region", { name: "Олена" })).toBeInTheDocument();
  });

  it("formatDate keeps the calendar date", () => {
    expect(formatDate("2026-11-30")).toBe("30.11.2026");
  });
});
