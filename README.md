# 💸 Expense Tracker

> A FastAPI + Alpine.js single-page app for tracking spending, payment state, and budget pressure.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-DB-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Alpine.js](https://img.shields.io/badge/Alpine.js-Frontend-8BC0D0?style=for-the-badge&logo=alpinedotjs&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-UI-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=for-the-badge&logo=render&logoColor=0B0F19)

## ✨ Features

- Full SPA interactions for create, toggle, and delete actions (no page reload).
- Track expenses by category, payment status, date, and amount tier.
- Live category breakdown and budget pressure meter with adjustable monthly cap.
- Filtering by search, category, status, completion, and high-spend tiers.
- Sorting by newest, highest amount, or nearest expense date.
- SQLite + SQLAlchemy persistence with FastAPI REST endpoints.
- Render Blueprint-ready deployment via `render.yaml`.

## 🔌 API Endpoints

| Method   | Endpoint                      | Description                         |
| -------- | ----------------------------- | ----------------------------------- |
| `GET`    | `/api/items`                  | List expense entries                |
| `POST`   | `/api/items`                  | Create expense entry                |
| `PATCH`  | `/api/items/{item_id}/toggle` | Toggle completion state (`is_done`) |
| `DELETE` | `/api/items/{item_id}`        | Delete expense entry                |
| `GET`    | `/api/stats`                  | Get dashboard stats                 |
| `GET`    | `/health`                     | Health check                        |

## ⚙️ Local Run

```bash
cd python-fastapiTracker
uv init
uv venv
source .venv/bin/activate
pip add -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- UI: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

## ☁️ Deploy on Render

`render.yaml` is included in the repository. You can deploy directly from this config.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
