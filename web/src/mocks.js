// Test data for working without the backend (VITE_USE_MOCKS=true).
// Remove once Masha's endpoints are in main.
import { ApiError } from "./errors.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function mockExchange(token) {
  await wait(400);
  if (token === "demo") {
    const expires = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    return {
      session: "mock-session",
      expiresAt: expires.toISOString(),
      user: { id: 1, name: "Тарас" },
    };
  }
  if (token === "expired") throw new ApiError("token_expired", 401);
  if (token === "used") throw new ApiError("token_used", 401);
  throw new ApiError("token_invalid", 401);
}
