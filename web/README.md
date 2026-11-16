# Веб-кабінет «Ліки вчасно» (SCRUM-16, SCRUM-31)

React + Vite. Довірена особа входить за одноразовим посиланням із бота і бачить розклади людей, які її запросили.

## Запуск

Потрібен Node.js 20+.

```bash
cd web
npm install
npm run dev:mock   # без бекенду, тестові дані
npm run dev        # з бекендом на localhost:8000 (docker compose up)
npm test           # Vitest
npm run build      # збірка в web/dist для хостингу
```

Режим `dev:mock` – тестові посилання:

| Посилання | Що побачите |
| --- | --- |
| http://localhost:5173/login?token=demo | успішний вхід |
| http://localhost:5173/login?token=expired | «Посилання застаріло» |
| http://localhost:5173/login?token=used | «Це посилання вже використано» |
| http://localhost:5173/login?token=demo-empty | вхід, але вас ще ніхто не запросив |

## Змінні збірки

| Змінна | Що означає |
| --- | --- |
| `VITE_API_URL` | Адреса бекенду. Локально порожня – Vite проксує `/auth`, `/contacts` на `localhost:8000`. На хостингу – публічна адреса API. |
| `VITE_USE_MOCKS` | `true` – працювати з тестовими даними без бекенду. |

Для хостингу (Катя, SCRUM-37): сторінка `/login` має віддавати `index.html` (SPA-fallback), у бекенді – CORS для домену кабінету і `WEB_URL`, на який веде посилання з бота.

## Контракт веб-входу (пропозиція для SCRUM-53)

Бот (`/web`) надсилає посилання `{WEB_URL}/login?token=<одноразовий токен>`.

`POST /auth/exchange`

```json
// запит
{ "token": "<токен з посилання>" }

// 200
{
  "session": "<токен сесії>",
  "expires_at": "2026-11-24T18:00:00Z",
  "user": { "id": 5, "name": "Олена" }
}

// 401 – прострочений, використаний або невідомий токен
{ "detail": { "code": "token_expired", "message": "Посилання застаріло" } }
// code: token_expired | token_used | token_invalid
```

Кабінет також розуміє `detail` рядком (`"Token expired"`, `"Token already used"`). Подальші запити – із заголовком `Authorization: Bearer <session>`. «Вийти» поки лише забуває сесію в браузері.

## Розклади підопічних (пропозиція для ендпоінта Маші, SCRUM-31)

`GET /contacts/patients` з `Authorization: Bearer <session>` – люди, які запросили цю довірену особу (`trusted_contacts.contact_id` = поточний користувач).

```json
// 200
{
  "patients": [
    {
      "id": 7,
      "name": "Олена",
      "medications": [
        {
          "id": 3,
          "name": "Сертралін",
          "dose": "50 мг",
          "form": "таблетка",
          "times": ["08:00", "20:00"],
          "end_date": "2026-11-30"
        }
      ]
    }
  ]
}
// 401 – немає сесії або вона прострочена
```

`times` – за Києвом, `HH:MM`; `form` і `end_date` можуть бути `null`. Кабінет також прийме просто список без обгортки `patients`. Порожній список – сторінка «Вас ще ніхто не запросив».
