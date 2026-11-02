import re

def care_plan_agent(note, profile):
    plan = {
        "status": "draft",
        "language": profile["language"],
        "patient": profile["name"],
        "medications": [],
        "appointments": [],
        "tests": [],
        "unresolved_fields": [],

    }
    for line in note.split("\n"): 
        low = line.lower()
        if low.startswith("take"):
            dose = re.search(r"\d+\s?(mg|ml|g)", low)
            plan["medications"].append({"text": line, "dose": dose.group(0) if dose else None})
            if not dose:
                plan["unresolved_fields"].append("missing dose: " + line)
        elif "appointment" in low:
            plan["appointments"].append(line)
        elif "test" in low:
            plan["tests"].append(line)
    return plan
