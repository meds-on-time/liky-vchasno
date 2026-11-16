import { useCallback, useEffect, useState } from "react";

import { fetchPatients } from "../api.js";

/** "2026-11-30" -> "30.11.2026" without time-zone shifts. */
export function formatDate(isoDate) {
  const [year, month, day] = isoDate.split("-");
  return `${day}.${month}.${year}`;
}

function Medication({ medication }) {
  const { name, dose, form, times, endDate } = medication;
  return (
    <li className="med">
      <div className="med-head">
        <span className="med-name">{name}</span>
        <span className="muted">{[dose, form].filter(Boolean).join(", ")}</span>
      </div>
      {times.length > 0 ? (
        <ul className="times" aria-label={`Час прийому: ${name}`}>
          {times.map((time) => (
            <li key={time} className="time">
              {time}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">Час прийому не задано</p>
      )}
      <p className="muted med-course">
        {endDate ? `Курс до ${formatDate(endDate)}` : "Без кінцевої дати"}
      </p>
    </li>
  );
}

/** SCRUM-31: read-only schedules of the people who invited this trusted contact. */
export default function PatientsPage({ session, onUnauthorized }) {
  const [state, setState] = useState({ status: "loading", patients: [] });

  const load = useCallback(async () => {
    setState({ status: "loading", patients: [] });
    try {
      const patients = await fetchPatients(session);
      setState({ status: "ready", patients });
    } catch (e) {
      if (e.code === "unauthorized") {
        onUnauthorized();
        return;
      }
      setState({ status: e.code === "network" ? "network" : "error", patients: [] });
    }
  }, [session, onUnauthorized]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.status === "loading") {
    return (
      <section className="card" aria-live="polite">
        <div className="spinner" aria-hidden="true" />
        <p>Завантажуємо розклади…</p>
      </section>
    );
  }

  if (state.status === "network" || state.status === "error") {
    return (
      <section className="card card-error" role="alert">
        <h1>
          {state.status === "network"
            ? "Не вдалося з'єднатися з сервером"
            : "Не вдалося завантажити розклади"}
        </h1>
        <p>Спробуйте ще раз за хвилину.</p>
        <button type="button" className="button" onClick={load}>
          Спробувати ще раз
        </button>
      </section>
    );
  }

  if (state.patients.length === 0) {
    return (
      <section className="card">
        <h1>Вас ще ніхто не запросив</h1>
        <p className="muted">
          Коли людина надішле вам запрошення з бота (команда /invite) і ви його відкриєте, її
          розклад з'явиться тут.
        </p>
      </section>
    );
  }

  return (
    <div className="patients">
      <h1 className="page-title">Розклади прийому ліків</h1>
      {state.patients.map((patient) => (
        <section key={patient.id} className="card patient" aria-label={patient.name}>
          <h2>{patient.name}</h2>
          {patient.medications.length > 0 ? (
            <ul className="meds">
              {patient.medications.map((m) => (
                <Medication key={m.id} medication={m} />
              ))}
            </ul>
          ) : (
            <p className="muted">Препаратів ще не додано</p>
          )}
        </section>
      ))}
      <p className="muted small">Сторінка лише для перегляду. Змінити розклад можна в боті.</p>
    </div>
  );
}
