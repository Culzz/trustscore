<!-- Title format: [type] short summary, e.g. [fix] policy guardrail state reset -->

## What changed

<!-- One or two sentences. What happens differently now? -->

## Why

<!-- Link the issue, or explain the reasoning. -->

## How it was tested

- [ ] `cd api && python -m pytest` passes
- [ ] `cd web && npm run typecheck` passes
- [ ] `cd web && npm run lint && npm run build` passes
- [ ] Manual verification steps (describe below):
  <!-- e.g. applied sample 01, submitted, checked notice + sandbox -->

Simulation/platform ground rules:

- [ ] No real personal data added anywhere
- [ ] No secrets committed (`.env*` stays ignored)
- [ ] Honest reporting preserved (watermark, breach counts, uncertainty)
