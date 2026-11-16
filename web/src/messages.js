// All user-facing texts of the login flow in one place.
export const NEW_LINK_HINT =
  "Відкрийте бота «Ліки вчасно» в Telegram і натисніть «Веб-кабінет» " +
  "(або надішліть команду /web), щоб отримати нове посилання.";

export const LOGIN_ERRORS = {
  missing_token: { title: "У посиланні немає коду входу", hint: NEW_LINK_HINT },
  token_expired: { title: "Посилання застаріло", hint: NEW_LINK_HINT },
  token_used: { title: "Це посилання вже використано", hint: NEW_LINK_HINT },
  token_invalid: { title: "Посилання недійсне", hint: NEW_LINK_HINT },
  network: {
    title: "Не вдалося з'єднатися з сервером",
    hint: "Перевірте інтернет і спробуйте ще раз.",
    retry: true,
  },
  server_error: {
    title: "Сталася помилка на сервері",
    hint: "Спробуйте ще раз за кілька хвилин.",
    retry: true,
  },
};
