"""Escalation Summary Agent: logged escalation + events -> fact-only brief (owner: Dorcas).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.
"""


async def run(payload: dict) -> dict:
    raise NotImplementedError
