# AgriConnect

Local hackathon MVP for direct farmer-to-buyer produce sales.

## Run locally

From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m backend.seed_data
python -m uvicorn backend.main:app --reload
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend uses `http://localhost:8000/api` by default. Copy
`backend\.env.example` to `.env` and set `GROQ_API_KEY` to enable Groq-powered
listing extraction and advisory responses. Without a key, advisory requests
use the built-in demo response; natural-language extraction reports a clear
configuration error.

Demo accounts:

- Farmer: `ravi@agri.demo` / `ravi123`
- Buyer: `freshmart@agri.demo` / `fresh123`

Passwords are intentionally plaintext because this is a local demo only.

## Delivery regression tests

With the Python virtual environment active, run from the repository root:

```sh
pip install -r backend/requirements-dev.txt
python -m unittest backend.test_order_delivery
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

Backend tests use an isolated SQLite database and simulate route claiming,
pickup, and delivery through the API. Frontend tests check farmer and transporter
actions with mocked API responses.
