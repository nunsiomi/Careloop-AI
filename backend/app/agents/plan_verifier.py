
def plan_verifier(note, plan):
  issues = []
  for med in plan["medications"]:
    if med["dose"] is None:
      issues.append("dose missing for: " + med["text"])
  if len(plan["appointments"]) == 0  and "appointment" in note.lower():
    issues.append("appointment in note but not in plan")
  return {"verdict": "flagged" if issues else "clean", "issues": issues}
