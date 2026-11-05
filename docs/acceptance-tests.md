# Acceptance tests (section 17)

The acceptance tests from section 17 of the project documentation, where each one lives, and what still needs people.
Run them from `backend/` with `python -m pytest` (the voice worker's from `voice/` with `python -m pytest test_voice.py`).

Last run: 3 Nov 2026. 160 backend tests and 14 voice tests passing.

| Area | Expected result | Automated test | Status |
|---|---|---|---|
| Care plan integrity | Five synthetic discharge notes with seeded dose and date errors; no unapproved instruction is sent | `test_plan_verifier.py`, `test_care_plan.py`, `test_end_to_end.py` step 1 | Passing. Six notes, including one in shorthand |
| Voice languages | Native-speaker evaluation in Hausa, Igbo and Yoruba | `test_acceptance.py`: each language reaches the emergency path on a call; `test_voice.py`: every Tomi line exists in all four languages | Automated part passing. **Native-speaker sessions still to do** (below) |
| Red flags | Positive, negative, negated and indirect phrases per language; uncertain dangerous speech goes to a person | `test_safety.py`, `test_acceptance.py` | Passing. Rules signed by Nunsi as acting reviewer (3 Nov 2026); **the clinical mentor still has to sign** before real patients |
| Verification | A shared phone or wrong PIN never reveals care details | `test_api.py` | Passing |
| Event provenance | Every report says whether the patient reported it or a clinician verified it; corrections add a new event | `test_acceptance.py` | Passing (a second report about a task now points at the one it replaces) |
| Appointment integrity | No double booking; a move waits for a clinician; the old reminder is cancelled only after the move succeeds | `test_acceptance.py` | Passing |
| Reminder reliability | Timeouts, retries and repeated runs never send twice or corrupt the status | `test_acceptance.py`, `test_notifications.py` | Passing (a failed message can now be sent again only once) |
| Escalation delivery | Not acknowledged until a reviewer acts; the backup contact is tested | `test_acceptance.py` | Passing |
| Channel fallback | Phone failure: say so and keep chat working. Unclear speech: ask again or use the keypad. A message that fails: logged and shown to the care team | `test_acceptance.py` | Passing. SMS is off, so "SMS fails, use email" waits for an SMS provider |
| Security | Signed webhooks; access checks; no real patient data or secrets in the repo | `test_acceptance.py`, `test_api.py` | Access checks and the repo scan pass. **No provider webhooks exist yet**: add signature checks with the first delivery-report webhook |

The full run from the launch checklist (discharge note, approved plan, reminder email, Tomi call, escalation on the
dashboard) is `test_end_to_end.py`.

## Found while writing these tests (fixed 3 Nov 2026)

- A corrected task report did not point at the report it replaced. It now sets `supersedes_event_id`.
- A message that was not delivered could be sent again twice, which sent two emails. The second press is now refused.
- Acknowledging a resolved escalation moved it back to "acknowledged". It now stays resolved.
- Indirect English phrases did not escalate: "gasping for air", "she is not responding", "blood in my vomit",
  "weak on one side", "cannot talk properly", "shaking all over", "my lips are swelling", "giving up on life".
  They were added to the draft rules for the clinical mentor to review (`docs/clinical-safety-review.md`).
  "Fitting" was tried and dropped because it matched "the dress is fitting well".

## Still to do by people

### Native-speaker sessions (voice languages)

One session per language, with at least one native speaker who was not involved in writing the lines. Record every
failure, not only the successes. Use a phone on a real call once there is a number; until then use the browser voice
sheet in the patient app.

| Check | Hausa | Yoruba | Igbo |
|---|---|---|---|
| Tomi's lines (`voice/prompts/lines.json`) read naturally and correctly | | | |
| Medicine names said in English are understood | | | |
| Dates and times are heard correctly ("Tuesday at 9:30") | | | |
| Symptom words are recognised, including the red-flag terms in `red_flags.json` | | | |
| Different accents (at least two speakers) | | | |
| Background noise (market, street, television) | | | |
| A red-flag phrase said indirectly or mixed with English | | | |
| Missing terms: Igbo has no seizure phrase yet | | | |

After each session, set `checked` for that language in `voice/prompts/lines.json` and `red_flags.json`, and sign its
row in `docs/clinical-safety-review.md`.

### Provider tests (section 20)

Speech quality on real Nigerian lines, call routing to Nigerian numbers, and SMS sender approval. These need a paid
phone number and an SMS provider.
