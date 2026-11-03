"""Tomi LiveKit worker: persona, turn state, Spitch STT/TTS, Groq replies (owner: Nunsi).

Started from voice.py in github.com/Tech-sis123/agricall (keypad language menu, LiveKit SIP and DTMF
handling), used with Tech-sis123's permission.

One worker handles three kinds of session:
- inbound phone call: language menu by keypad, then the CareLoop PIN, then the check-in;
- outbound phone call: the backend dispatches the worker with the patient and the number to ring;
- browser voice: the patient is already signed in to the app, so there is no PIN.

Nothing about a patient's care is said before the PIN check. Every patient turn goes through the backend's
safety check before Tomi replies; a red flag skips the model and plays the approved emergency line.

Run:  python tomi_agent.py console   (talk to Tomi in this terminal, mock patient Zainab)
      python tomi_agent.py dev       (joins your LiveKit Cloud project; then `python dial.py +234...` rings a phone)
      python tomi_agent.py start     (production)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    StopResponse,
    cli,
    function_tool,
    get_job_context,
    llm,
)
from livekit.plugins import groq, silero, spitch

from backend_client import Backend, make_backend
from call_controller import (
    LANGUAGE_DIGITS,
    LANGUAGE_NAMES,
    MAX_MENU_REPEATS,
    PIN_LENGTH,
    CallController,
    CallState,
    Keypad,
    language_code,
    transcript_unclear,
)

load_dotenv()
logger = logging.getLogger("tomi")

AGENT_NAME = "tomi"
LINES = json.loads((Path(__file__).parent / "prompts" / "lines.json").read_text(encoding="utf-8"))

# Spitch voices. Section 7.2 of the project documentation: check these on the team account and override
# them with SPITCH_VOICE_HA and so on, rather than trusting the defaults.
VOICES = {
    "ha": os.getenv("SPITCH_VOICE_HA", "amina"),
    "yo": os.getenv("SPITCH_VOICE_YO", "sade"),
    "ig": os.getenv("SPITCH_VOICE_IG", "ngozi"),
    "en": os.getenv("SPITCH_VOICE_EN", "lucy"),
}
# Groq retires models; check console.groq.com/docs/models. gpt-oss-120b answered in correct Hausa in under 1 s
# (2 Nov 2026). It is a reasoning model, so Tomi asks for low reasoning effort to keep replies quick.
GROQ_MODEL = os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"

MENU_WAIT = 10  # seconds to wait for a key after the menu, before repeating it
PIN_WAIT = 15


def line(lang: str, key: str, **values: str) -> str:
    text = LINES.get(lang, {}).get(key) or LINES["en"][key]
    return text.format(**values) if values else text


def local_now(tz_name: str | None) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name or "Africa/Lagos"))
    except ZoneInfoNotFoundError:
        return datetime.now()


class Voices:
    """One Spitch TTS per language for the call, so fixed lines can be spoken in any language."""

    def __init__(self) -> None:
        self._tts: dict[str, spitch.TTS] = {}

    def tts(self, lang: str) -> spitch.TTS:
        if lang not in self._tts:
            self._tts[lang] = spitch.TTS(language=lang, voice=VOICES[lang])
        return self._tts[lang]

    def say(self, session: AgentSession, lang: str, text: str, *, interruptible: bool = True):
        """Speak a fixed line in `lang`, whatever language the session is in."""
        tts = self.tts(lang)

        async def frames():
            async for chunk in tts.synthesize(text):
                yield chunk.frame

        return session.say(text, audio=frames(), allow_interruptions=interruptible)


async def wait_for_key(keypad: Keypad, speeches: list, timeout: float) -> str | None:
    """Wait for one key while the prompts play. A key press cuts the prompts short."""
    key_task = asyncio.ensure_future(keypad.digit(None))
    playout = asyncio.ensure_future(asyncio.gather(*(s.wait_for_playout() for s in speeches)))
    done, _ = await asyncio.wait({key_task, playout}, return_when=asyncio.FIRST_COMPLETED)
    if key_task in done:
        for speech in speeches:
            if not speech.done():
                speech.interrupt()
        playout.cancel()
        return key_task.result()
    try:
        return await asyncio.wait_for(key_task, timeout)
    except asyncio.TimeoutError:
        return None


def build_instructions(context: dict, lang: str) -> str:
    patient = context["patient"]
    now = local_now(patient.get("timezone"))
    care = {"plan": context["plan"], "tasks": context["tasks"], "facility": context.get("facility")}
    return f"""You are Tomi, CareLoop's automated follow-up assistant, on a call with {patient['first_name']}, who has
gone home after care at {context.get('facility') or 'their care facility'}. You are not a doctor or nurse and you
say so if asked.

Language: speak only {LANGUAGE_NAMES[lang]}, with correct spelling and tone marks. Keep each reply to one or two
short sentences, in plain words for someone who may not read well. Ask one question at a time.

What you may talk about is limited to the approved care plan and tasks below. Say medicine names, doses, times,
places and dates exactly as they are written there. Never add, change or guess a medicine, dose, time, place,
date, diagnosis or test result, and never say what a symptom means. If the patient asks anything the plan does
not answer, including any medical question, say you will pass it to their care team and call ask_care_team.

Your job on this call: check how the patient is getting on with today's tasks and upcoming visits and tests.
- When the patient says they did or did not do a task, repeat back what you understood and ask them to confirm.
  Only after they confirm, call record_task_update with their own words.
- If something stops them (cost, transport, distance, medicine out of stock, no one to help), call report_problem.
  Do not promise that a problem will be solved.
- Never tell the patient an ambulance or emergency service is coming.
- When the patient is done, or asks to stop, say goodbye briefly and call end_call.

It is {now.strftime('%A %d %B %Y, %H:%M')} where the patient is.

Approved care plan and tasks (JSON):
{json.dumps(care, ensure_ascii=False)}"""


class TomiAgent(Agent):
    def __init__(self, *, controller: CallController, backend: Backend, voices: Voices, context: dict, lang: str) -> None:
        super().__init__(
            instructions=build_instructions(context, lang),
            stt=spitch.STT(language=lang),
            tts=voices.tts(lang),
            llm=groq.LLM(
                model=GROQ_MODEL,
                temperature=0.2,
                # Includes the model's hidden reasoning, so leave room beyond the one or two spoken sentences.
                max_completion_tokens=500,
                **({"reasoning_effort": "low"} if GROQ_MODEL.startswith("openai/gpt-oss") else {}),
            ),
        )
        self.controller = controller
        self.backend = backend
        self.voices = voices
        self.context = context
        self.lang = lang
        self.unclear_turns = 0

    @property
    def patient_id(self) -> str:
        return self.context["patient"]["id"]

    async def on_enter(self) -> None:
        opening = self.context.get("opening")
        if opening:
            # An approved opening line from the backend, already in the patient's language.
            await self.session.say(opening)
        else:
            self.session.generate_reply(
                instructions="You have already greeted the patient and said who you are; do not greet again. "
                "Ask, in one short sentence, how they are getting on with today's plan."
            )

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        text = (new_message.text_content or "").strip()
        if not text:
            raise StopResponse()

        # Speech started in this hook is not awaited here: it only plays once the hook returns.
        if self.controller.escalated:
            # After a red flag Tomi does not go back to the check-in. It repeats the emergency line.
            self.voices.say(self.session, self.lang, line(self.lang, "emergency"), interruptible=False)
            raise StopResponse()

        self.controller.to(CallState.LISTENING)
        self.controller.to(CallState.SAFETY_AND_ACTION)
        try:
            verdict = await self.backend.check_turn(
                call_id=self.controller.call_id, patient_id=self.patient_id, text=text, language=self.lang,
                # Spitch gives no confidence score; an unclear transcript is sent as low confidence so a danger
                # word in it still escalates (the backend's safe path).
                confidence=0.4 if transcript_unclear(text) else None,
            )
        except Exception:
            logger.exception("safety check failed")
            # If the safety check cannot run, the model must not answer. Hand over to people.
            self.controller.to(CallState.PROVIDER_ERROR, "safety check unavailable")
            speech = self.voices.say(self.session, self.lang, line(self.lang, "unavailable"), interruptible=False)
            asyncio.ensure_future(hang_up(after=speech))
            raise StopResponse()

        if verdict.get("action") == "escalate":
            self.controller.to(CallState.ESCALATED, (verdict.get("escalation") or {}).get("rule_id"))
            self.voices.say(self.session, self.lang, line(self.lang, "emergency"), interruptible=False)
            # The app's voice screen shows the emergency-number button when it sees this.
            try:
                room = get_job_context().room
                asyncio.ensure_future(room.local_participant.set_attributes({"careloop.escalation": "open"}))
            except RuntimeError:
                pass  # no room outside a real job (tests)
            raise StopResponse()

        if verdict.get("action") == "clarify":
            # Never guess at unclear speech: ask again, and after two unclear turns hand over to people.
            self.unclear_turns += 1
            if self.unclear_turns >= 2:
                self.unclear_turns = 0
                asyncio.ensure_future(self.backend.ask_care_team(
                    call_id=self.controller.call_id, patient_id=self.patient_id,
                    question="Tomi could not understand the patient twice on this call. Please contact them."))
                self.voices.say(self.session, self.lang, line(self.lang, "handover"), interruptible=False)
            else:
                self.voices.say(self.session, self.lang, line(self.lang, "not_clear"))
            raise StopResponse()
        self.unclear_turns = 0

        self.controller.to(CallState.SPEAKING)

    @function_tool()
    async def record_task_update(
        self,
        context: RunContext,
        task_id: str,
        status: Literal["done", "not_done", "unable"],
        patient_words: str,
    ) -> str:
        """Record what the patient said about one task, after they confirmed it.

        Args:
            task_id: The id of the task from the care plan JSON.
            status: done, not_done (they have not done it yet) or unable (something stopped them).
            patient_words: What the patient said, in their own words and language.
        """
        await self.backend.record_task_update(
            call_id=self.controller.call_id, patient_id=self.patient_id, task_id=task_id, status=status, patient_words=patient_words
        )
        return "Recorded as reported by the patient."

    @function_tool()
    async def report_problem(
        self,
        context: RunContext,
        kind: Literal["cost", "transport", "distance", "stock", "no_helper", "other"],
        patient_words: str,
        task_id: str | None = None,
    ) -> str:
        """Tell the care team about something that stops the patient following the plan.

        Args:
            kind: The kind of problem.
            patient_words: What the patient said, in their own words and language.
            task_id: The task it affects, if there is one.
        """
        await self.backend.report_problem(
            call_id=self.controller.call_id, patient_id=self.patient_id, kind=kind, patient_words=patient_words, task_id=task_id
        )
        return "The care team has been told. Do not promise a solution."

    @function_tool()
    async def ask_care_team(self, context: RunContext, question: str) -> str:
        """Pass a question to the care team that the plan does not answer, including any medical question.

        Args:
            question: The patient's question, in their own words and language.
        """
        await self.backend.ask_care_team(call_id=self.controller.call_id, patient_id=self.patient_id, question=question)
        return "Passed to the care team. Tell the patient someone from their care team will follow up."

    @function_tool()
    async def end_call(self, context: RunContext) -> None:
        """End the call after saying goodbye."""
        await context.wait_for_playout()
        self.controller.to(CallState.COMPLETED)
        await hang_up()


async def hang_up(after=None) -> None:
    """End the call for everyone, once `after` (a speech) has finished playing."""
    if after is not None:
        await after.wait_for_playout()
    ctx = get_job_context()
    if ctx.is_fake_job():
        ctx.shutdown("call ended")
        return
    await ctx.api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))


async def language_menu(session: AgentSession, voices: Voices, keypad: Keypad, controller: CallController) -> str | None:
    """Play the greeting and the language options, each in its own language. Returns the chosen language."""
    controller.to(CallState.MENU)
    while True:
        speeches = [voices.say(session, "en", line("en", "greeting"))]
        speeches += [voices.say(session, code, line(code, "language_option")) for code in LANGUAGE_DIGITS.values()]
        key = await wait_for_key(keypad, speeches, MENU_WAIT)
        if key and controller.choose_language(key):
            return controller.language
        give_up = controller.menu_timed_out() if key is None else controller.menu_repeats >= MAX_MENU_REPEATS
        if give_up:
            return None
        if key is None:
            await voices.say(session, "en", line("en", "no_key"))
        controller.to(CallState.UNCLEAR_INPUT, f"key {key!r}")
        controller.to(CallState.MENU)


async def pin_gate(session, voices, keypad, controller, backend, phone: str | None) -> bool:
    lang = controller.language or "en"
    controller.to(CallState.VERIFICATION_GATE)
    while True:
        keypad.clear()
        prompt = voices.say(session, lang, line(lang, "pin_prompt"))
        first = await wait_for_key(keypad, [prompt], PIN_WAIT)
        pin = None
        if first is not None and first.isdigit():
            rest = await keypad.digits(PIN_LENGTH - 1, first_timeout=8)
            pin = first + (rest or "")
        if pin is None or len(pin) != PIN_LENGTH:
            if controller.menu_timed_out():
                controller.to(CallState.UNVERIFIED, "no PIN entered")
                return False
            await voices.say(session, lang, line(lang, "no_key"))
            continue
        result = await backend.verify_pin(call_id=controller.call_id, phone_e164=phone, pin=pin)
        outcome = controller.pin_result(bool(result.get("ok")), result.get("patient_id"), result.get("tries_left"))
        if outcome == "verified":
            return True
        if outcome == "locked":
            return False
        await voices.say(session, lang, line(lang, "pin_wrong"))


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(sample_rate=8000 if os.getenv("TOMI_PHONE_ONLY") else 16000)


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    backend = make_backend()
    voices = Voices()
    keypad = Keypad()
    # Outbound calls and browser sessions carry JSON metadata from the backend: patient_id, phone_e164, call_id.
    meta = json.loads(ctx.job.metadata or "{}")
    await ctx.connect()

    if ctx.is_fake_job():
        direction, phone, participant = "browser", None, None
    elif meta.get("phone_e164"):
        direction, phone = "outbound", meta["phone_e164"]
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=os.environ["LIVEKIT_SIP_TRUNK_ID"],
                    sip_call_to=phone,
                    participant_identity="patient",
                    wait_until_answered=True,
                )
            )
        except api.TwirpError as err:
            # Not answered, busy or failed. The backend logs it; a missed call never counts as a missed task.
            logger.info("outbound call not answered: %s %s", err.message, (err.metadata or {}).get("sip_status_code"))
            call_id = meta.get("call_id") or "unknown"
            await backend.end_call(call_id=call_id, outcome="not_reached", log=[])
            ctx.shutdown("not answered")
            return
        participant = await ctx.wait_for_participant(identity="patient")
    else:
        participant = await ctx.wait_for_participant()
        is_phone = participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        direction = "inbound" if is_phone else "browser"
        # Calls Twilio connects for us (dial.py, setup_sip.py) carry the patient's number in a header,
        # because the caller LiveKit sees is then Twilio's own number.
        phone = (participant.attributes.get("careloop.phone") or participant.attributes.get("sip.phoneNumber")) if is_phone else None

    patient_id = meta.get("patient_id")
    if direction == "browser" and not patient_id and participant is not None:
        patient_id = participant.attributes.get("careloop.patient_id")
    if direction == "browser" and not patient_id and os.getenv("VOICE_USE_MOCKS", "1") != "0":
        patient_id = "p-zainab"  # console and Playground tests use the sample patient

    call = await backend.start_call(direction=direction, phone_e164=phone, patient_id=patient_id)
    controller = CallController(call_id=meta.get("call_id") or call["id"], direction=direction)
    controller.language = language_code(call.get("language"), default="") or None
    if direction == "browser" and meta.get("language"):
        controller.language = language_code(meta["language"])  # the language the patient chose in the app
    test_language = os.getenv("TOMI_TEST_LANGUAGE")
    if direction == "browser" and test_language and os.getenv("VOICE_USE_MOCKS", "1") != "0":
        controller.language = language_code(test_language)  # console tests in a language other than Zainab's Hausa
    controller.to(CallState.ANSWERED)

    @ctx.room.on("sip_dtmf_received")
    def on_dtmf(dtmf: rtc.SipDTMF) -> None:
        keypad.press(dtmf.digit)

    async def finish(reason: str) -> None:
        await backend.end_call(call_id=controller.call_id, outcome=controller.outcome(), log=controller.log)

    ctx.add_shutdown_callback(finish)

    session = AgentSession(vad=ctx.proc.userdata["vad"], tts=voices.tts(controller.language or "en"))

    @session.on("conversation_item_added")
    def on_item(event) -> None:
        item = event.item
        if isinstance(item, llm.ChatMessage) and item.role in ("user", "assistant") and item.text_content:
            speaker = "patient" if item.role == "user" else "tomi"
            asyncio.ensure_future(
                backend.log_turn(call_id=controller.call_id, speaker=speaker, text=item.text_content, language=controller.language or "en")
            )

    # Until the PIN is checked, Tomi has no speech recognition and no model: only fixed lines and the keypad.
    await session.start(room=ctx.room, agent=Agent(instructions="", stt=None, llm=None))

    if direction == "browser":
        controller.patient_id = patient_id
        controller.to(CallState.VERIFIED, "signed in to the app")
    else:
        if not controller.language:
            if not await language_menu(session, voices, keypad, controller):
                controller.to(CallState.UNVERIFIED, "no language chosen")
                await voices.say(session, "en", line("en", "goodbye"))
                await hang_up()
                return
        else:
            await voices.say(session, controller.language, line(controller.language, "greeting"))
        if not await pin_gate(session, voices, keypad, controller, backend, phone):
            lang = controller.language or "en"
            await voices.say(session, lang, line(lang, "pin_failed"), interruptible=False)
            await hang_up()
            return

    try:
        context = await backend.call_context(call_id=controller.call_id, patient_id=controller.patient_id)
    except Exception:
        logger.exception("could not load the care plan")
        lang = controller.language or "en"
        controller.to(CallState.PROVIDER_ERROR, "context unavailable")
        await voices.say(session, lang, line(lang, "unavailable"), interruptible=False)
        await hang_up()
        return

    if not context.get("consent", {}).get("voice"):
        lang = controller.language or language_code(context["patient"].get("language"))
        controller.to(CallState.OPT_OUT, "no voice consent")
        await voices.say(session, lang, line(lang, "goodbye"))
        await hang_up()
        return

    lang = controller.language or language_code(context["patient"].get("language"))
    controller.language = lang
    first_name = context["patient"]["first_name"]
    if direction == "browser":
        # The app has no menu or PIN, so this is where Tomi says who she is and that she is automated.
        await voices.say(session, lang, line(lang, "greeting_named", first_name=first_name))
    else:
        await voices.say(session, lang, line(lang, "verified", first_name=first_name))
    controller.to(CallState.LISTENING)
    session.update_agent(TomiAgent(controller=controller, backend=backend, voices=voices, context=context, lang=lang))


if __name__ == "__main__":
    cli.run_app(server)
