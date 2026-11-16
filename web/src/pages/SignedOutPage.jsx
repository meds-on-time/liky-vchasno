import { NEW_LINK_HINT } from "../messages.js";

const TITLES = {
  logout: "Ви вийшли з кабінету",
  expired: "Сесія завершилась",
};

/** Shown without a session: after «Вийти», when the session expired, or on a direct visit. */
export default function SignedOutPage({ reason }) {
  return (
    <section className="card">
      <h1>{TITLES[reason] ?? "Вхід до веб-кабінету"}</h1>
      <p>{NEW_LINK_HINT.replace("нове посилання", "посилання для входу")}</p>
    </section>
  );
}
