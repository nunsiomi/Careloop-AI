# Plan review criteria

What a clinician checks on the dashboard's plan review screen before approving a care plan. The Care Plan Agent
drafts the plan from the discharge note, and the Plan Verifier compares the two; neither approves anything.
Nothing reaches the patient until a clinician approves. Owner: Mary.

## What the checks flag

Each finding names the plan field and highlights the words in the note it is about.

| Severity | Meaning | Examples |
|---|---|---|
| **High** | Blocks the plan from being sent until it is fixed | No strength ("Bisoprolol tablet"), no amount, "take as directed", two different strengths for one medicine, a date or time not in the note, a date that does not exist, a medicine in the note but not in the plan |
| **Medium** | Needs a look, but does not block on its own | "Next week" or "within 7 days" instead of a date, a visit with no time, an instruction or warning sign not in the note |

Anything the note does not support is left out of the draft rather than guessed: the agent removes invented
medicines, visits, tests, doses, dates and times, and lists the gap instead.

## Before you approve

1. **Right patient.** The note names this patient.
2. **Every medicine.** Name, strength, amount, how often, times and how long all match the note. Fix the note
   first if the note itself is wrong or incomplete, then draft again.
3. **Every visit and test.** Exact date and time, and the right place. Turn "next week" into a real date with the
   patient's agreement.
4. **Warning signs.** They match the note's return-to-hospital advice.
5. **No high findings left.** Each one is fixed in the plan (or the note), not dismissed.
6. **Medium findings read.** Either fixed or knowingly accepted.

## What approval means

- Approval is recorded under the clinician's name and time; later changes create a new version, not an edit.
- A "clean" verdict means the checks found nothing. It does not replace reading the plan against the note.
- If the model check did not run (the verifier returns `model_checked: false`), only the rule checks were
  applied: read the plan with extra care.
