# Care plan format

The one shape for a care plan, used by the Care Plan Agent, the Plan Verifier, the backend, the dashboard's plan
review screen and Tomi. For **Mary and Olamide** to confirm (section 22.2 of the project documentation:
"Mary → Olamide: validated care-plan JSON, verifier verdict, unresolved-field list"). The code that enforces it is
`backend/app/models.py`; the API shape is in `docs/api_shapes.md` ("Plan").

## The plan

```json
{
  "id": "plan-…", "patient_id": "p-…", "status": "needs_review | approved",
  "source_note": "the discharge note, exactly as pasted",
  "medications":  [{ "name": "Amlodipine 5 mg tablet", "dose": "1 tablet", "frequency": "Every morning",
                     "times": ["08:00"], "duration": "30 days", "instructions": "" }],
  "appointments": [{ "what": "Follow-up", "where": "Heart Clinic, room 3", "date": "2026-11-06", "time": "10:00" }],
  "tests":        [{ "name": "Kidney function blood test", "where": "Hospital laboratory", "date": "" }],
  "symptoms_to_watch": ["Chest pain"], "reminder_times": ["08:00"],
  "verifier_issues": [{ "field": "tests[0].date", "issue": "…", "severity": "high | medium", "source_text": "within 7 days" }],
  "deliverable": false, "model_checked": true,
  "clinician_approved_at": null, "approved_by": null, "created_by": "Dr. Ada Okafor"
}
```

| Field | Rule |
|---|---|
| `name` | Medicine, strength and form ("Amlodipine 5 mg tablet"). No strength in the note means none in the name, and a high issue. |
| `dose` | Amount each time, with digits ("1 tablet", "1/2 tablet"). Empty if the note does not say. |
| `frequency` | Plain words for patients ("Twice daily"). Standard shorthand (od, bd, tds, qds, nocte, mane) may be written out; "as directed" and "prn" leave it empty and raise a high issue. |
| `times` | `HH:MM`, only times written in the note ("8am" counts as 08:00). |
| `duration` | As written ("30 days"). May be empty for ongoing medicines. |
| `date` | `YYYY-MM-DD` or empty. Only an exact date, or a fixed number of days or weeks after the discharge date. "Next week" or "within 7 days" stays empty with a medium issue. |
| `time` | `HH:MM` or empty. |
| `source_text` | Exact words from the note, so the dashboard can highlight them. |
| `reminder_times` | The medicine times, without repeats. |

**Empty means "not in the note".** Nothing is guessed or filled with a usual value; the verifier flags the gap and
the clinician fills it in.

## Severity and delivery

- **High** blocks delivery: anything about which medicine, its strength, amount, how often or how long, and any date
  or time not in the note (`docs/plan-review-criteria.md`).
- `deliverable` is false while a high issue is open. A clinician can still approve after confirming they checked each
  one (the dashboard sends `override_issues: true`); that is recorded on the timeline.
- `model_checked` is false when only the rule checks ran (no Groq key, or the model call failed).

## What approval does

1. Status becomes `approved`, with the clinician's name and time.
2. One pending task per medicine time per day, for the plan's `duration`. **No duration: 7 days**, recorded on the
   timeline so the care team can extend it.
3. One task per dated test, **due at 09:00** that day.
4. One appointment per visit that has both a date and a time.
5. If the patient has not joined yet, an invite code (emailed if there is an address). Reminders start after consent.

## Decisions

Decided by Nunsi on 3 Nov 2026, covering for Mary and Olamide (section 22.2 of the project documentation).

| Question | Decision |
|---|---|
| The plan fields and rules above | Agreed as written |
| Length when a medicine has no duration | 7 days, flagged on the timeline so the care team can extend it |
| Time for a dated test | 09:00 |
| Visits with a date but no time | No appointment created; stays on the plan for the clinician |
| Shorthand written out for patients (bd → "Twice daily") | Allowed; the verifier reads both |
| A plan with a high issue | Approvable only with explicit acknowledgement, recorded on the timeline |

## Review notes (3 Nov 2026)

The agents were run on the six notes in `data/sample_discharges/` with Groq, and the rule checks on the same notes
with tests (`backend/tests/test_plan_verifier.py`, `test_care_plan.py`). Found and fixed in this review:

- Notes written in prescription shorthand ("Tab. Amlodipine 5mg, 1 tab bd at 8am", "half a tablet", "10th
  November") were flagged wrongly, and the Care Plan Agent would have blanked correct values. The checks now read
  dosage-form prefixes, od/bd/tds/qds/nocte/mane, am/pm times, halves and dates without a year. A sixth sample note
  (`musa-bello.txt`) keeps this tested.
- A plan saying "Once daily" when the note says "bd" passed as a wording difference; a different number of times
  a day is now a high issue.
- Still known: when a note names a medicine twice with different strengths ("Continue lisinopril 5 mg"), the model
  may list it twice; the verifier flags the conflict, and the clinician removes the duplicate.
