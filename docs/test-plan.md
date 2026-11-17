# Тест-план MVP «Ліки вчасно»

_SCRUM-38, SCRUM-71 · Максим Безверхий (QA) · етапи 4–5 · оновлено 18.11.2026_

## 1. Мета і обсяг

Мета – перевірити, що прототип виконує затверджене правило нагадувань і основні сценарії бота: реєстрацію, додавання препарату, розклад, нагадування з кнопками, захист від подвійної дози і сигнал довіреній особі. Поза обсягом етапу 4: веб-кабінет, тривалість курсу через бота і деплой (перенесено на етап 5).

## 2. Рівні тестування

| Рівень | Інструменти | Що перевіряємо | Коли запускається |
|---|---|---|---|
| Модульні | pytest, SQLite у пам'яті (aiosqlite), фейковий Telegram | Сервіси (реєстрація, препарати, розклад, правило нагадувань, довірені особи); поточний час передається параметром now, тому кожну гілку правила (T, T+30, T+50, T+60) перевіряємо миттєво; тексти й кнопки бота; діалог /add через aiogram Dispatcher | Локально перед PR і в CI на кожен PR та push у main |
| Інтеграційні | pytest, PostgreSQL 16, FastAPI TestClient | Повний цикл прийому T → T+30 → T+60 на справжній БД; ендпоінти take, snooze і schedule з усіма відповідями контракту; 404 і 422; бот: планувальник → повідомлення → кнопки | Якщо задано TEST_DATABASE_URL: у CI (сервіс postgres) і локально (контейнер test-pg) |
| Ручні | Telegram, Swagger (/docs) | Сценарій демо: /start, /add, /times, нагадування, «Прийняв», «Нагадати за 10 хв», /invite, /consent_on, сигнал про пропуск | Перед кожним демо (10.11, 17.11) |

## 3. Середовище

- Python 3.12, pytest 8; модульні тести не потребують Docker.
- Інтеграційні: docker run -d --name test-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 5433:5432 postgres:16-alpine; змінна TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/test. Без цієї змінної інтеграційні тести пропускаються.
- CI: GitHub Actions, сервіс postgres:16-alpine, ruff check app tests і pytest з TEST_DATABASE_URL; звіти JUnit зберігаються як артефакт.
- Ручна перевірка: застосунок через docker compose up --build -d, власний тестовий бот у .env (BOT_TOKEN).

## 4. Критерії «тест пройдено»

- Тест пройдено, якщо фактичний результат збігається з очікуваним у таблиці нижче і тест завершився без помилок.
- Задача готова до злиття, якщо ruff і всі тести (модульні та інтеграційні) у CI зелені, а для нової логіки є модульні тести.
- Дефект, знайдений вручну, фіксується тестом, який спершу падає, а після виправлення проходить.

## 5. Тест-кейси за правилом нагадувань

T – час прийому (у прикладах 20:00 за Києвом). T+30 – повтор, T+50 – межа відкладення, T+60 – «пропущено».

| ID | Сценарій (дано / коли) | Очікуваний результат | Рівень | Автотест |
|---|---|---|---|---|
| TC-01 | Прийом о 20:00; «Прийняв» о 20:03 | Статус taken, «Записано о 20:03»; повтору на T+30 і сигналу на T+60 немає | М, І | test_take_cancels_repeat_and_alert, test_cycle_take_on_time_cancels_repeat_and_missed |
| TC-02 | Прийом уже відмічено; «Прийняв» ще раз | already_taken і час першої відмітки; у журналі рівно одна подія taken | М, І | test_second_take_creates_only_one_taken_event, test_api_take_ok_then_already_taken |
| TC-03 | «Нагадати за 10 хв» о 20:05 | ok і remind_at 20:15; о 20:15 нагадування типу snooze; T+30 і T+60 не зсуваються | М, І | test_snooze_does_not_move_missed_time, test_cycle_snooze_then_take |
| TC-04 | Відкласти о 20:55 (після T+50) | too_late, відкладення не записується | М, І | test_snooze_after_t_plus_50_is_too_late, test_api_snooze_after_t_plus_50_is_too_late |
| TC-05 | Немає відповіді до 21:00 | 20:30 – повторне нагадування; 21:00 – статус missed | М, І | test_repeat_at_t_plus_30, test_cycle_no_answer_repeat_then_missed_alert |
| TC-06 | «Прийняв» о 21:05 (після T+60) | missed, статус не змінюється, у журналі taken_after_missed | М, І | test_cycle_take_after_t_plus_60_is_logged_only |
| TC-07 | Прийом пропущено; у довіреної особи є згода | Сигнал довіреній особі: ім'я, препарат, доза, час; надсилається один раз | М, І | test_missed_alert_reaches_trusted_contact |
| TC-08 | Згоду вимкнено (/consent_off); прийом пропущено | Статус missed, сигналу немає | М, І | test_no_alert_after_consent_off, test_cycle_consent_off_sends_no_alert |
| TC-09 | Курс завершився (end_date минула) | Нагадувань більше немає (логіка є; задання тривалості в боті – етап 5) | М | test_course_end_date_stops_reminders |
| TC-10 | POST /intakes/999/take і /snooze | 404 intake not found | М, І | test_api_take_and_snooze_and_404, test_api_unknown_intake_is_404 |
| TC-11 | /times 08:00 08:59; 23:30 і 00:10 | Відмова: «Між прийомами має бути щонайменше 60 хв: …»; рівно 60 хв і 23:00/00:30 – ok | М | test_midnight_gap_40_minutes_is_rejected, test_api_put_schedule_with_close_times_returns_422 (+4) |
| TC-12 | /add з назвою «А», дозою 51 символ, формою «пігулка» | Пояснення помилки і те саме питання ще раз; нічого не збережено | М | test_add_dialog_repeats_question_on_bad_input (+6) |
| TC-13 | /add → «Скасувати» або /cancel | «Додавання препарату скасовано.», препарат не збережено | М | test_add_dialog_cancel_button_and_command |
| TC-14 | Чужий користувач натискає «Прийняв» під моїм нагадуванням | «Це не ваше нагадування», прийом не змінено | М, І | test_other_user_cannot_press_patients_button |
| TC-15 | /add з назвою, яка вже є; /meds | Попередження про дублікат і вибір «Так, додати» / «Скасувати»; /meds – список з дозою, формою і часом | М | test_add_dialog_warns_about_duplicate_name, test_meds_command_shows_my_medications |

_М – модульний, І – інтеграційний; «+N» – ще N тестів на цей кейс (див. журнал). Усі кейси також проходимо вручну на демо._

## 6. Журнал результатів

Журнал результатів формується автоматично з JUnit-звіту pytest:

```bash
pytest --ignore=tests/integration --junitxml=reports/junit-unit.xml
pytest tests/integration --junitxml=reports/junit-integration.xml
python scripts/junit_to_table.py reports/junit-unit.xml --title "Журнал модульних тестів"
```

Скрипт створює таблиці Markdown і CSV з колонками «№ | Тест | Що перевіряє | Результат | Дата». «Що перевіряє» береться з docstring тесту, а якщо його немає – з назви.

## 7. Ручна перевірка на демо

1. /start – реєстрація; повторний /start – «З поверненням».
2. /add – назва, доза, форма кнопкою; перевірити «Скасувати» і некоректну назву.
3. /times з часом через 2 хв – нагадування з кнопками «Прийняв» і «Нагадати за 10 хв».
4. «Нагадати за 10 хв» – «Нагадаю о …»; «Прийняв» – «Записано о …».
5. Повторне «Прийняв» – через Swagger: POST /intakes/{id}/take двічі (ok, потім already_taken), бо після «Прийняв» кнопки зникають.
6. /times 08:00 08:30 – відмова з поясненням про 60 хв.
7. /invite з другого акаунта, /consent_on; заздалегідь пропущений прийом – сигнал довіреній особі.

## 8. Етап 5: нові тест-кейси

Sprint 3 (етап 5) додав вхід у веб-кабінет (SCRUM-16, 53), розклади підопічного (SCRUM-31, 69) і тривалість курсу (SCRUM-19). Модульні тести до них пишуть автори задач; QA додає інтеграційні тести на PostgreSQL там, де важлива справжня БД (одночасні запити, UNIQUE, timestamptz, межа доби за Києвом), і наскрізний сценарій через Dispatcher бота.

| ID | Сценарій (дано / коли) | Очікуваний результат | Рівень | Автотест |
|---|---|---|---|---|
| TC-16 | /web → посилання → POST /auth/exchange → GET /auth/me | Сесія на 7 днів, /auth/me повертає користувача | І | test_api_full_login_flow, test_bot_web_command_link_logs_in |
| TC-17 | Те саме посилання вдруге | 401 token_used і підказка «візьміть нове через /web» | М, І | test_second_exchange_is_rejected, test_api_second_exchange_is_401_token_used |
| TC-18 | Посилання старше 10 хв; вигаданий токен | 401 token_expired / token_invalid | М, І | test_api_expired_and_unknown_tokens_are_401, test_token_lifetime_boundary_in_postgres |
| TC-19 | Два одночасні обміни одного токена (подвійне натискання) | Рівно одна сесія, другий запит – token_used | І | test_two_simultaneous_exchanges_give_one_session |
| TC-20 | GET /auth/me без сесії, з вигаданою або простроченою | 401 | М, І | test_api_me_without_valid_session_is_401 |
| TC-21 | У БД після /web | Лише SHA-256 хеш, дубль хешу відхиляє UNIQUE | М, І | test_only_hash_is_stored, test_only_hashes_stored_and_hash_is_unique |
| TC-22 | GET /contacts/patients довіреною особою | Видно лише своїх підопічних зі згодою: препарати, час, end_date; чужих – ні; без сесії – 401 | М, І | tests/test_patients.py (Маша); інтеграційні – після злиття SCRUM-69 |
| TC-23 | /course 7, /course 1, /course 365, /course 0 / off | «Курс до ДД.ММ» (сьогодні – день 1); off – без кінця | М, І | test_parse_valid_days, test_course_off_clears_end, test_course_errors_in_bot |
| TC-24 | /course 400, /course abc, /course без препарату або без /times | Пояснення помилки, end_date не змінюється | М, І | test_course_errors_in_bot (+3) |
| TC-25 | Останній день курсу і наступний, прийом о 00:30 і 23:45 за Києвом | Останній день нагадує, наступний – ні (дата за Києвом, не UTC) | М, І | test_course_end_after_midnight_uses_kyiv_date, test_course_end_late_evening_last_day |
| TC-26 | /times після /course; /meds | Кінець курсу зберігається; /meds показує «курс до …» | М, І | test_new_times_keep_course_and_off_clears_it |
| TC-27 | Повний шлях: /start → /add → /times → /course → /meds → /web → кабінет | Усі кроки відповідають очікуваними текстами, вхід у кабінет працює | І | test_user_journey_from_start_to_web_cabinet |

## 9. Чек-лист розгорнутої версії

| № | Що перевірити на розгорнутій версії | Очікувано | Результат |
|---|---|---|---|
| 1 | GET {API}/health | status ok, database connected, bot_enabled true | ☐ |
| 2 | {API}/docs відкривається ззовні по HTTPS | Swagger з розділами intakes, schedules, auth | ☐ |
| 3 | /start і /add у продакшн-боті | Реєстрація, препарат збережено | ☐ |
| 4 | /times на час через 2 хв | Нагадування з двома кнопками в межах 30 с | ☐ |
| 5 | «Нагадати за 10 хв», потім «Прийняв» | «Нагадаю о …», «Записано о …» | ☐ |
| 6 | Прийом без відповіді (за годину до перевірки) | Повтор на T+30, сигнал довіреній особі на T+60 | ☐ |
| 7 | /course 3 і /meds | «Курс до …» у відповіді та в /meds | ☐ |
| 8 | /web → посилання → кабінет | Вхід без помилок, сторінка розкладів | ☐ |
| 9 | Те саме посилання вдруге | Текст «Посилання вже використано…» | ☐ |
| 10 | Перезапуск контейнера | Дані на місці, нагадування йдуть далі | ☐ |

_Заповнюється після деплою (SCRUM-37). Результат: ✓ / ✗ і примітка; підсумок іде в журнал SCRUM-71._
