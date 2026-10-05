# ColdCraft v2.1 → v2.2

Roadmap items 3–9 on top of your v2.1 code (your own extraction changes are preserved).

| # | Area | Summary |
|---|------|---------|
| 3 | Email generation | Prompt `email_generation/v2` uses the real job description and forbids invented facts. `ai/email_checks.py` enforces greeting, sign-off, 50–200 words (120 for "concise"), no filler, no figures absent from JD/research/resume. Failures are repaired once (with the reason), then fall back to the next provider. Saved only via a guarded UPDATE, so failed or raced generation can't corrupt the draft. `generate_email` works straight from `DRAFT` (researches first). |
| 4 | Gmail | New `SENDING` state: atomic `READY → SENDING` claim gives duplicate-send protection. Typed errors (`GmailAuthError`, `GmailSendError` with `ambiguous`), header-injection-safe messages, guessed `careers@` recipients need explicit confirmation (`recipient_source`), stuck sends recover to `READY` with a warning. |
| 5 | Tracking | State machine updated (`READY → SENDING → SENT`); exhaustive transition-matrix test. |
| 6 | Follow-ups | DB-enforced one live follow-up per application, atomic claim when sending, cancelled ones don't count toward the cap of 3, `run_scheduler_tick` (auto-send stays OFF unless `FOLLOWUP_AUTO_SEND=true`), stuck-send recovery. |
| 7 | End-to-end | `tests/integration/test_e2e.py` — URL/screenshot → … → SENT → follow-up → reply. |
| 8 | Duplicates | `services/dedupe.py` (URL canonicalisation incl. LinkedIn ids, company+role normalisation). Checked before any fetch/AI call; `force=true` overrides; rejected/withdrawn don't block. |
| 9 | Frontend | Capture → **Extraction preview/edit** (`ExtractionPreview`) → research & write → review → **confirm dialog** (`ConfirmSendDialog`) → send. Duplicate banner, recipient trust hints, History grouped by lifecycle with filters, Withdraw/Delete. |

Also: `validate_extracted_job` now returns HTTP 422 (was an unhandled `ValueError` → 500; still a `ValueError` subclass). Migration `0003` adds `recipient_source` and the follow-up guard (auto-run on startup; back up your DB first).

Run: `cd backend && pip install -r requirements-dev.txt && pytest` · `cd frontend && npx tsc --noEmit`

Not verified: live Groq/Gemini/Gmail calls; the UI in a real browser/Electron (typecheck + build only).
