# Contribution workflow — Ліки вчасно

- Jira: move assigned task to «В роботі» when work begins; to «На перевірці» after opening a PR; to «Готово» only after DoD is met.
- Every branch name, commit message and PR title contains `SCRUM-<number>`.
- Example branch: `feature/SCRUM-35-docker-environment`.
- Example commit: `SCRUM-35: add Docker Compose starter`.
- Example PR: `SCRUM-35: Docker environment and local README`.
- Changes to main only through PR with **one other team member's approval**.
- No force push to `main`. CI becomes mandatory only when it exists.
- Never commit `.env`, production credentials or real Telegram tokens.
