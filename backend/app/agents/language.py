"""Language & Literacy Agent: meaning-preserving adaptation/translation with uncertainty flags (owner: Nunsi).

Returns structured findings or proposed actions only. Never writes care records
directly; the orchestrator validates and invokes approved tools.
"""


async def run(payload: dict) -> dict:
    raise NotImplementedError
