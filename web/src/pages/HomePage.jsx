/** After login. The schedules of the people you care for arrive in SCRUM-31. */
export default function HomePage({ user }) {
  return (
    <section className="card">
      <h1>Вітаємо{user?.name ? `, ${user.name}` : ""}!</h1>
      <p>Ви увійшли до веб-кабінету «Ліки вчасно».</p>
      <p className="muted">
        Тут з'являться розклади прийому ліків людей, які запросили вас довіреною особою.
      </p>
    </section>
  );
}
