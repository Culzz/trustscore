# Contributing to TrustScore

Thanks for your interest. TrustScore is a portfolio-grade demonstration of
responsible-AI credit decisioning: an explainable, fairness-aware **simulation**
— not a lending product. Contributions to the engineering and the audit tooling
are welcome.

## Getting started

```bash
# API (Python 3.11+)
cd api
python -m venv .venv && .venv\Scripts\activate   # or: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Web (Node 20+)
cd web
npm install
npm run dev      # http://localhost:3000
```

`python -m pytest` (from `api/`) runs the test suite. The runtime stack
deliberately stays light — no scikit-learn, SciPy, SHAP or matplotlib at serving
time — so keep it that way in new code.

## Making a change

1. Create a feature branch from `main`.
2. Keep the change small and explainable; the codebase favours plain Python,
   explicit configuration and honest failure messages over framework magic.
3. Run the checks before pushing:
   - `cd api && python -m pytest`
   - `cd web && npm run typecheck && npm run lint && npm run build`
4. Open a pull request using the template. CI runs the same commands.

## Ground rules

* **No real personal data.** Raw datasets live in `data/` (git-ignored) and are
  never committed. Use the public Kaggle Credit Risk Dataset for anything
  model-related.
* **No secrets.** Configuration goes through `.env` (never committed) and
  `.env.example` documents every variable with a placeholder.
* **Honesty first.** Features must report what they did — including breaches,
  costs and uncertainty — rather than asserting success. The watermark and
  simulation banners are compliance features; leave them in place.
* **Keep the audit trail.** Changes to scoring, policy or fairness logic should
  be reflected in the tests, and where relevant in `docs/EVALUATION.md`.

## Reporting issues

Open a [GitHub issue](https://github.com/Culzz/trustscore/issues) with the
checklist filled in (steps to reproduce + expected vs actual). Security
vulnerabilities follow the private process in
[SECURITY.md](SECURITY.md) instead.
