"""Make Tomi ring a phone, as the backend will for scheduled check-ins (POST /calls/outbound).

Needs the worker running (`python tomi_agent.py dev`).
Usage:  python dial.py +2348031234567

Two ways to place the call:
- LIVEKIT_SIP_TRUNK_ID set (a paid SIP trunk): LiveKit dials out and Tomi joins as on any outgoing call.
- Otherwise, Twilio (works on a trial): Twilio rings the phone and, once it is answered, fetches its
  instructions from twiml_server.py and connects the call to Tomi through LiveKit. Run `python setup_sip.py
  twilio` once and keep `python twiml_server.py` running. On a trial, the number must be a verified caller ID,
  and Twilio asks you to press a key before it connects.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from livekit import api

from tomi_agent import AGENT_NAME


async def dial_with_livekit(phone: str) -> None:
    room = f"call-{uuid.uuid4().hex[:8]}"
    metadata = {"phone_e164": phone, "patient_id": "p-zainab"}
    async with api.LiveKitAPI() as lk:
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room, metadata=json.dumps(metadata))
        )
    print(f"Tomi is calling {phone} (room {room}). Answer and talk to Tomi.")


async def dial_with_twilio(phone: str) -> None:
    sid, token = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    # Trial accounts can't send TwiML with the call, so Twilio fetches it from twiml_server.py.
    url_file = Path(__file__).parent / ".tunnel-url"
    base = os.getenv("TWILIO_WEBHOOK_BASE") or (url_file.read_text(encoding="utf-8").strip() if url_file.exists() else "")
    if TWILIO_DEMO:
        # Twilio's own sample instructions: if this call plays a message, Twilio can fetch instructions from the
        # internet on this account, and any problem is with reaching our tunnel.
        url = "https://demo.twilio.com/docs/voice.xml"
    else:
        if not base:
            sys.exit("Start the TwiML server first, in another terminal: python twiml_server.py (wait for 'Ready')")
        try:
            reachable = httpx.get(base.rstrip("/") + "/", timeout=8).status_code == 200
        except httpx.HTTPError:
            reachable = False
        if not reachable:
            sys.exit(f"Twilio would not reach the TwiML server at {base}. Restart python twiml_server.py, wait for 'Ready'.")
        url = base.rstrip("/") + ("/twiml/stream-test" if STREAM_TEST else "/twiml/outbound")
    data = {"To": phone, "From": os.environ["TWILIO_PHONE_NUMBER"].replace(" ", ""), "Url": url}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", auth=(sid, token), data=data)
    if resp.status_code >= 300:
        sys.exit(f"Twilio said no ({resp.status_code}): {resp.json().get('message', resp.text)}")
    print(f"Twilio is calling {phone} (call {resp.json()['sid']}). Answer, press a key if Twilio asks,")
    print("then talk to Tomi (a number not on file chooses a language first).")


TWILIO_DEMO = "--twilio-demo" in sys.argv
STREAM_TEST = "--stream-test" in sys.argv  # does this Twilio account allow Media Streams? (see twiml_server.py)

if __name__ == "__main__":
    sys.argv = [arg for arg in sys.argv if arg not in ("--twilio-demo", "--stream-test")]
    if len(sys.argv) != 2 or not sys.argv[1].startswith("+"):
        sys.exit("Usage: python dial.py +2348031234567   (add --twilio-demo to test Twilio with its sample message)")
    load_dotenv()
    number = sys.argv[1].replace(" ", "")
    asyncio.run(dial_with_livekit(number) if os.getenv("LIVEKIT_SIP_TRUNK_ID") else dial_with_twilio(number))
