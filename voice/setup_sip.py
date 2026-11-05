"""One-off setup that connects a phone number to Tomi through LiveKit.

    python setup_sip.py telnyx    Telnyx SIP connection (recommended). Creates in your LiveKit project:
                                  - an outbound trunk, so Tomi can ring patients (prints its ST_ id for .env);
                                  - an inbound trunk and a dispatch rule, so calls to the number reach `tomi`.
    python setup_sip.py twilio    Twilio without SIP trunking: an inbound trunk with a password, for calls that
                                  twiml_server.py passes on (works on a Twilio trial).

Safe to run again: anything that already exists is left as it is.
"""

import asyncio
import os
import sys
from xml.sax.saxutils import escape, quoteattr

from dotenv import load_dotenv
from livekit import api

from tomi_agent import AGENT_NAME

# Twilio sends the number it is ringing in this header; Tomi reads it as the caller's phone.
PHONE_HEADER = "X-CareLoop-Phone"
PHONE_ATTRIBUTE = "careloop.phone"

NEEDS = {
    "telnyx": ("TELNYX_PHONE_NUMBER", "TELNYX_SIP_USERNAME", "TELNYX_SIP_PASSWORD"),
    "twilio": ("LIVEKIT_SIP_URI", "LIVEKIT_SIP_USERNAME", "LIVEKIT_SIP_PASSWORD", "TWILIO_PHONE_NUMBER"),
}


def env_number(key: str) -> str:
    return os.environ[key].replace(" ", "")


def sip_host() -> str:
    return os.environ["LIVEKIT_SIP_URI"].strip().removeprefix("sip:").split(";")[0]


def twiml(phone_for_tomi: str | None = None) -> str:
    """TwiML that connects a Twilio call to Tomi. `phone_for_tomi` is the patient's number on outgoing calls.

    Pass "{{To}}" to get a TwiML Bin template: Twilio fills in the number it rang.
    """
    uri = f"sip:{env_number('TWILIO_PHONE_NUMBER')}@{sip_host()};transport=tcp"
    if phone_for_tomi:
        value = phone_for_tomi if phone_for_tomi.startswith("{{") else phone_for_tomi.replace("+", "%2B")
        uri += f"?{PHONE_HEADER}={value}"
    user = quoteattr(os.environ["LIVEKIT_SIP_USERNAME"])
    password = quoteattr(os.environ["LIVEKIT_SIP_PASSWORD"])
    return f'<Response><Dial answerOnBridge="true"><Sip username={user} password={password}>{escape(uri)}</Sip></Dial></Response>'


async def inbound_trunk(lk: api.LiveKitAPI, number: str, **auth) -> str:
    existing = await lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest(numbers=[number]))
    if existing.items:
        print(f"Inbound trunk already exists: {existing.items[0].sip_trunk_id}")
        return existing.items[0].sip_trunk_id
    trunk = await lk.sip.create_inbound_trunk(
        api.CreateSIPInboundTrunkRequest(trunk=api.SIPInboundTrunkInfo(name="careloop-in", numbers=[number], **auth))
    )
    print(f"Created inbound trunk: {trunk.sip_trunk_id}")
    return trunk.sip_trunk_id


async def dispatch_rule(lk: api.LiveKitAPI, trunk_id: str) -> None:
    rules = await lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest(trunk_ids=[trunk_id]))
    if rules.items:
        print(f"Dispatch rule already exists: {rules.items[0].sip_dispatch_rule_id}")
        return
    rule = await lk.sip.create_dispatch_rule(
        api.CreateSIPDispatchRuleRequest(
            name="careloop-tomi",
            trunk_ids=[trunk_id],
            rule=api.SIPDispatchRule(dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-")),
            room_config=api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]),
        )
    )
    print(f"Created dispatch rule: {rule.sip_dispatch_rule_id}")


async def setup_telnyx() -> None:
    number = env_number("TELNYX_PHONE_NUMBER")
    async with api.LiveKitAPI() as lk:
        existing = await lk.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest(numbers=[number]))
        if existing.items:
            outbound_id = existing.items[0].sip_trunk_id
            print(f"Outbound trunk already exists: {outbound_id}")
        else:
            trunk = await lk.sip.create_outbound_trunk(
                api.CreateSIPOutboundTrunkRequest(
                    trunk=api.SIPOutboundTrunkInfo(
                        name="telnyx-out",
                        address="sip.telnyx.com",
                        numbers=[number],
                        auth_username=os.environ["TELNYX_SIP_USERNAME"],
                        auth_password=os.environ["TELNYX_SIP_PASSWORD"],
                    )
                )
            )
            outbound_id = trunk.sip_trunk_id
            print(f"Created outbound trunk: {outbound_id}")
        # Telnyx sends incoming calls to LiveKit without a password, so the trunk only accepts this number.
        await dispatch_rule(lk, await inbound_trunk(lk, number))

    print(f"\nPut this in .env, then restart the worker:\nLIVEKIT_SIP_TRUNK_ID={outbound_id}")


async def setup_twilio() -> None:
    async with api.LiveKitAPI() as lk:
        trunk_id = await inbound_trunk(
            lk,
            env_number("TWILIO_PHONE_NUMBER"),
            auth_username=os.environ["LIVEKIT_SIP_USERNAME"],
            auth_password=os.environ["LIVEKIT_SIP_PASSWORD"],
            headers_to_attributes={PHONE_HEADER: PHONE_ATTRIBUTE},
        )
        await dispatch_rule(lk, trunk_id)

    print("\nLiveKit is ready. Next: python twiml_server.py (leave it running), python tomi_agent.py dev,")
    print("then python dial.py +234...")


if __name__ == "__main__":
    load_dotenv()
    provider = sys.argv[1] if len(sys.argv) > 1 else ""
    if provider not in NEEDS:
        sys.exit("Usage: python setup_sip.py telnyx   (or: twilio)")
    missing = [key for key in NEEDS[provider] if not os.getenv(key)]
    if missing:
        sys.exit(f"Fill these in .env first: {', '.join(missing)}")
    asyncio.run(setup_telnyx() if provider == "telnyx" else setup_twilio())
