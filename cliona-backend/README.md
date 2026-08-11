# Cliona Backend

See `/CLAUDE.md` at the repo root for the full specification. This tree is
the Phase 1 scaffold: correct file layout, imports, and function/class
signatures, with unimplemented bodies (`NotImplementedError("Phase 1")`).

## Local dev

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill DATABASE_URL, SUPABASE_*, OPENROUTER_API_KEY, CLERK_*
alembic upgrade head
uvicorn app.main:app --reload
```
