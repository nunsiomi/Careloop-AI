# Clinical safety review

For the clinical mentor, with Dorcas (owner) and Mary. Everything below is a **draft** written for the MVP. None of
it may be used with real patients until the mentor has reviewed it and signed the table at the end. Native speakers
must also check the Hausa, Yoruba and Igbo terms.

The rules live in `backend/app/safety/red_flags.json`; the code that applies them is `backend/app/safety/rules.py`.
Keyword lists are not a guarantee of safety, especially with speech recognition and mixed languages. They are
written to err towards escalating.

## 1. What happens when a rule fires

1. Every patient message (app chat) and every voice turn is checked **before** any agent or reply.
2. On a match, routine conversation stops. The patient hears or reads the emergency line:
   > This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team.
3. An escalation opens on the dashboard with the patient's exact words, the rule, and a factual brief.
4. The facility's care team is emailed at once. The email has no patient name or clinical detail, only a link.
5. If nobody acknowledges within **15 minutes**, the backup contact is emailed again and the history records it.
6. An escalation is never treated as acknowledged until a reviewer acts, and CareLoop never says that emergency
   services have been called.

**For the mentor:** Is the emergency line right? Is 112 the right number for every facility? Is 15 minutes right,
and who should the backup contact be?

## 2. Red-flag rules (all severity red)

| Rule | Example English phrases | Hausa, Yoruba, Igbo (drafts, not yet checked) |
|---|---|---|
| Chest pain | chest pain, chest hurts, pressure in my chest, any mention of "chest" | ciwon kirji · aya mi n dun · obi na-afu m ufu |
| Trouble breathing | can't breathe, short of breath, not breathing, choking, gasping for air | numfashi yana min wuya · mi o le mi · enweghi m ike iku ume |
| Fainting | fainted, passed out, unconscious, collapsed, not responding, could not wake up | suma · daku · dara mba |
| Signs of a stroke | face drooping, slurred speech, can't move my arm, weak on one side, cannot talk properly | shanyewar jiki · roparose · otu akuku aru anaghi aga |
| Heavy bleeding | bleeding heavily, vomiting blood, coughing blood, blood in my vomit | zubar jini · eje n san · obara na-agbapu |
| Seizure | seizure, having a fit, convulsion, shaking all over | farfadiya · giri, warapa · (none yet) |
| Serious allergic reaction | throat swelling, tongue is swelling, lips are swelling | makogwaro ya kumbura · ofun mi wu · akpiri m zara |
| Thoughts of self-harm | kill myself, end my life, don't want to live, giving up on life, want to die | kashe kaina · pa ara mi · igbu onwe m |

The full term lists are in `red_flags.json`. Terms match in any language, whatever language the patient chose.
Tone marks and Hausa hooked letters are ignored, so "Ƙirjina yana ciwo" and "kirjina yana ciwo" both match.

The English phrases added on 3 Nov 2026 (gasping for air, not responding, weak on one side and the others in the last
column above) came from testing indirect wording for section 17 of the project documentation. Phrases that still do
**not** escalate, by design until you decide: "my heart is beating very fast", "I am feeling dizzy". A test also
showed "I do not want to die" is treated as a negated mention (Tomi asks once, see section 3).

**For the mentor:** Which rules are missing (for example high fever with confusion, very low or high blood sugar for
diabetic patients, a racing heart or dizziness)? Should any be amber rather than red? Is "any mention of chest" too
broad?

## 3. Uncertain and negated mentions

- **Negated** ("I have no chest pain", "Ba ni da ciwon kirji"): Tomi does not ignore it and does not escalate at
  once. She asks once: "Just to be safe: are you having chest pain now? If you feel very unwell, go to the nearest
  hospital now." A "yes" escalates.
- **Unclear speech** (confidence below 0.6) containing any word from a red-flag phrase escalates (the safe path).
  Unclear speech without one is asked again or answered with the keypad.

**For the mentor:** Is asking again right for negated mentions, or should they escalate as well?

## 4. Other policies (severity amber)

| Policy | What it does |
|---|---|
| Critical medicine overdue | A high-criticality task with no report 2 hours after it was due opens one escalation. It is never recorded as a missed dose. |
| Barrier not resolved | After 2 offered options that did not work, one escalation opens for the care team. |

**For the mentor:** Are 2 hours and 2 attempts right? Should overdue tests or visits also escalate?

## 5. What the agents may and may not say

- **Check-in Agent:** proposes an intent only. Marking a task done waits for the patient's own "yes". Its reply is
  sent only if it adds no number that is not in the approved plan (`safety/number_check.py`) and contains no advice
  that would change treatment (stop, increase, skip, "it is safe"…). Otherwise a fixed, approved line is sent.
- **Barrier Resolution Agent:** offers only contacts the facility listed in `data/resources.json`, each with its
  "not guaranteed" note.
- **Escalation Summary Agent:** quotes the patient's words and lists open items. A model-written brief is kept only
  if it quotes the patient, adds no new number, and names no diagnosis, urgency or help on the way.

## 6. Reminder wording

Reminders go by email (SMS once there is a provider). They are fixed templates in
`backend/app/services/notifications.py` and never name a medicine, condition or test, so they are safe if someone else
reads the patient's inbox. Nothing is sent between 21:00 and 07:00 in the patient's time zone.

| Template | Text (`{first}` is the patient's first name) |
|---|---|
| Medicine or test | CareLoop: Hello {first}, you have a reminder from {facility}. Open the CareLoop app or call Tomi on {tomi_line}. Do not reply. |
| Visit | CareLoop: Hello {first}, you have a care visit soon. Open the CareLoop app for the time and place, or call Tomi on {tomi_line}. Do not reply. |
| Visit moved | CareLoop: Hello {first}, your visit time has changed. Open the CareLoop app to see the new time, or call Tomi on {tomi_line}. Do not reply. |
| Support contact | CareLoop: Hello {first}, your care team shared a contact that may help. Open the CareLoop app to see it, or call Tomi on {tomi_line}. Do not reply. |
| Missed call | CareLoop: Hello {first}, Tomi tried to call you. Call Tomi back on {tomi_line} when you can, or open the CareLoop app. Do not reply. |
| Please contact us | CareLoop: Hello {first}, your care team at {facility} would like to hear from you. Call Tomi on {tomi_line} or open the CareLoop app. Do not reply. |

Emails add: "This email never says what your medicine is for. You can turn email reminders off in the app."

**For the mentor:** Is one reminder 30 minutes before each medicine right? Is the evening-before visit reminder
(18:00) right? Should a reminder ever say "medicine" rather than just "a reminder"?

## 7. Tested on 3 Nov 2026

`backend/tests/test_acceptance.py` and `backend/tests/test_end_to_end.py` check every step in sections 1 to 6 with the
current draft rules: each language reaches the emergency path on a call, unclear speech with a danger word goes to a
person, the care-team email carries no patient details, the backup email goes after 15 minutes, and acknowledging stops
it. Passing tests show that the code follows these rules; they do not show that the rules are clinically right. That
is what this review is for.

## 8. Sign-off

| Item | Reviewed by | Date | Decision |
|---|---|---|---|
| Emergency line and number | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP |
| Red-flag rules (section 2) | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP, including the phrases added on 3 Nov |
| Uncertain and negated mentions (section 3) | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP |
| Amber policies (section 4) | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP |
| Agent guardrails (section 5) | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP |
| Reminder wording (section 6) | Nunsi (acting reviewer) | 3 Nov 2026 | Accepted for the MVP |
| Hausa terms (native speaker) | | | |
| Yoruba terms (native speaker) | | | |
| Igbo terms (native speaker) | | | |

Nunsi signed the first six rows on 3 Nov 2026 as acting reviewer for the MVP. A clinician has not reviewed them yet:
the clinical mentor must review and sign them before real patients use CareLoop. When every row is signed, set `approved_by` and `approved_at` in `red_flags.json` and `checked` for each language.
