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
| Trouble breathing | can't breathe, short of breath, not breathing, choking | numfashi yana min wuya · mi o le mi · enweghi m ike iku ume |
| Fainting | fainted, passed out, unconscious, collapsed | suma · daku · dara mba |
| Signs of a stroke | face drooping, slurred speech, can't move my arm | shanyewar jiki · roparose · otu akuku aru anaghi aga |
| Heavy bleeding | bleeding heavily, vomiting blood, coughing blood | zubar jini · eje n san · obara na-agbapu |
| Seizure | seizure, having a fit, convulsion | farfadiya · giri, warapa · (none yet) |
| Serious allergic reaction | throat swelling, tongue is swelling | makogwaro ya kumbura · ofun mi wu · akpiri m zara |
| Thoughts of self-harm | kill myself, end my life, don't want to live | kashe kaina · pa ara mi · igbu onwe m |

The full term lists are in `red_flags.json`. Terms match in any language, whatever language the patient chose.
Tone marks and Hausa hooked letters are ignored, so "Ƙirjina yana ciwo" and "kirjina yana ciwo" both match.

**For the mentor:** Which rules are missing (for example high fever with confusion, or very low or high blood sugar
for diabetic patients)? Should any be amber rather than red? Is "any mention of chest" too broad?

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

## 6. Sign-off

| Item | Reviewed by | Date | Decision |
|---|---|---|---|
| Emergency line and number | | | |
| Red-flag rules (section 2) | | | |
| Uncertain and negated mentions (section 3) | | | |
| Amber policies (section 4) | | | |
| Agent guardrails (section 5) | | | |
| Hausa terms (native speaker) | | | |
| Yoruba terms (native speaker) | | | |
| Igbo terms (native speaker) | | | |

When every row is signed, set `approved_by` and `approved_at` in `red_flags.json` and `checked` for each language.
