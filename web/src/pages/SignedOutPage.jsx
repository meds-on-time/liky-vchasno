import { NEW_LINK_HINT } from "../messages.js";

/** Shown without a session: right after "Вийти" or when the page is opened directly. */
export default function SignedOutPage({ justLoggedOut }) {
  return (
    <section className="card">
      <h1>{justLoggedOut ? "Ви вийшли з кабінету" : "Вхід до веб-кабінету"}</h1>
      <p>{NEW_LINK_HINT.replace("нове посилання", "посилання для входу")}</p>
    </section>
  );
}
