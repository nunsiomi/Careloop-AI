"""Tomi LiveKit worker: persona, turn state, Spitch STT/TTS, Groq replies (owner: Nunsi).

Started from voice.py in github.com/Tech-sis123/agricall (keypad language menu, LiveKit SIP and DTMF
handling), used with Tech-sis123's permission.

One worker handles three kinds of session. There is no PIN on any of them (decided by Nunsi, 5 Nov 2026):
- inbound phone call: a number on file (the patient's, or a caregiver's) is enough. Tomi greets them by name
  in their language and talks freely about their plan. An unknown number chooses a language by keypad and
  hears what CareLoop is and how to join; nothing about anyone's care is said to it;
- outbound phone call: the backend dispatches the worker with the patient and the number on their record;
- browser voice: the patient is already signed in to the app.

Every caller turn goes through the backend's safety check before Tomi replies; a red flag skips the model and
plays the approved emergency line.

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
    caller = context.get("caller") or {"kind": "patient"}
    now = local_now(patient.get("timezone"))
    care = {"plan": context["plan"], "today": context.get("today"), "tasks": context["tasks"], "facility": context.get("facility")}
    talking_to = (f"{caller['first_name']}, who helps {patient['first_name']} ({caller.get('relation') or 'family'}). Talk about "
                  f"{patient['first_name']}'s plan with them" if caller["kind"] == "caregiver" else patient["first_name"])
    return f"""You are Tomi, CareLoop's health assistant, on a phone call with {talking_to}. {patient['first_name']} has gone home
after care at {context.get('facility') or 'their care facility'}, and you are here to help them stay well and keep to
their care plan. You are warm, patient and encouraging, like a kind nurse's helper who has time to talk. You are
not a doctor or nurse and you say so if asked.

Language: speak only {LANGUAGE_NAMES[lang]}, with correct spelling and tone marks. This is a phone call: keep each
reply to one to three short spoken sentences, in plain words for someone who may not read well. No lists.

What you can do:
- Have a real conversation. Ask how they are feeling, listen, and respond kindly to what they say.
- Answer any question about their own plan: what to take today and when, how long a medicine is for, what the
  instructions say, when and where the next visit or test is. Say medicine names, doses, times, places and dates
  exactly as written in the plan below. When you repeat the plan, say "your plan says", never "you should".
- When they ask what a medicine on their plan is for, call look_up_medicine and explain the answer in one or two
  plain sentences, then say their care team chose it for them and can tell them more. Never answer that from memory.
- When they say they did or did not do a task, repeat back what you understood and ask them to confirm. Only after
  they confirm, call record_task_update with their own words.
- If something stops them (cost, transport, distance, medicine out of stock, no one to help), call report_problem.
  Do not promise that a problem will be solved.
- Pass anything else to their care team with ask_care_team and tell them someone will get back to them: side
  effects, whether they can take another medicine, changing or stopping a medicine, what a symptom means, test
  results, or anything the plan does not answer.

Never add, change or guess a medicine, dose, time, place, date, diagnosis or test result. Never tell them to stop,
skip, double or change a medicine, never say what a symptom means or that it is nothing to worry about, and never
say an ambulance or emergency service is coming. When they are done, or ask to stop, say goodbye warmly and call
end_call.

It is {now.strftime('%A %d %B %Y, %H:%M')} where they are.

Their approved care plan, today's tasks and open tasks (JSON):
{json.dumps(care, ensure_ascii=False)}"""


def guide_instructions(lang: str) -> str:
    return f"""You are Tomi, CareLoop's health assistant, answering a phone call from a number that is not linked to
anyone in CareLoop. You know nothing about this caller's health and you must not ask for or guess any.

Language: speak only {LANGUAGE_NAMES[lang]}, with correct spelling and tone marks. One to three short spoken
sentences per reply, plain words, no lists.

What to tell them, warmly and in your own words, answering what they ask:
- CareLoop helps people after they leave a care facility (a hospital, clinic, pharmacy or care home) to keep to the
  care plan their care team made: reminders for medicines, tests and visits, a chat in an app, and calls from
  Tomi in Hausa, Yoruba, Igbo or English.
- To join, they ask their care team. The care facility adds them and gives them an invite code.
- If they already use CareLoop but are calling from another phone, they should call from the phone number their
  care team has on file, or ask their care team to update it.
- You cannot see or discuss anyone's care on this call, and you do not give medical advice.
- If they feel very unwell, they should go to the nearest hospital now.

When they are done, say goodbye warmly and call end_call."""


class CallAgent(Agent):
    """Tomi on a call: every turn goes through the backend's safety check before the model answers."""

    def __init__(self, *, controller: CallController, backend: Backend, voices: Voices, context: dict | None, lang: str, instructions: str) -> None:
        super().__init__(
            instructions=instructions,
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
    def patient_id(self) -> str | None:
        return ((self.context or {}).get("patient") or {}).get("id")

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
            if self.unclear_turns >= 2 and self.patient_id:
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
    async def end_call(self, context: RunContext) -> None:
        """End the call after saying goodbye."""
        await context.wait_for_playout()
        self.controller.to(CallState.COMPLETED)
        await hang_up()


class GuideAgent(CallAgent):
    """A caller whose number is not on file: what CareLoop is and how to join. No patient data, no patient tools."""

    def __init__(self, *, controller: CallController, backend: Backend, voices: Voices, lang: str) -> None:
        super().__init__(controller=controller, backend=backend, voices=voices, context=None, lang=lang, instructions=guide_instructions(lang))

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions="You have already said who you are; do not greet again. In one or two short sentences, say this number "
            "is not linked to CareLoop yet, and ask how you can help or whether they would like to hear what CareLoop is."
        )


class TomiAgent(CallAgent):
    def __init__(self, *, controller: CallController, backend: Backend, voices: Voices, context: dict, lang: str) -> None:
        super().__init__(controller=controller, backend=backend, voices=voices, context=context, lang=lang,
                         instructions=build_instructions(context, lang))

    async def on_enter(self) -> None:
        opening = self.context.get("opening")
        if opening:
            # An approved opening line from the backend, already in the patient's language.
            await self.session.say(opening)
        else:
            self.session.generate_reply(
                instructions="You have already greeted them by name and said who you are; do not greet again. "
                "In one short, warm sentence, ask how they are feeling today and how you can help."
            )

    @function_tool()
    async def look_up_medicine(self, context: RunContext, name: str) -> dict:
        """What a medicine on the patient's plan is generally used for, from MedlinePlus (US National Library of Medicine).

        Args:
            name: The medicine name as written on the plan.
        """
        return await self.backend.medicine_info(call_id=self.controller.call_id, name=name)

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
    patient_id = patient_id or call.get("patient_id")
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

    # Until Tomi knows who is calling, there is no speech recognition and no model: only fixed lines and the keypad.
    await session.start(room=ctx.room, agent=Agent(instructions="", stt=None, llm=None))

    if patient_id and (direction != "inbound" or call.get("known")):
        controller.patient_id = patient_id
        controller.to(CallState.VERIFIED, {"browser": "signed in to the app", "outbound": "number on the record"}.get(direction, "caller's number"))
    else:
        # A number we do not know: choose a language, then hear what CareLoop is. Nothing about anyone's care.
        if not controller.language and not await language_menu(session, voices, keypad, controller):
            controller.to(CallState.UNVERIFIED, "no language chosen")
            await voices.say(session, "en", line("en", "goodbye"))
            await hang_up()
            return
        lang = controller.language or "en"
        if controller.state != CallState.MENU:
            controller.to(CallState.MENU)
        await voices.say(session, lang, line(lang, "greeting"))
        controller.to(CallState.LISTENING, "unknown caller")
        session.update_agent(GuideAgent(controller=controller, backend=backend, voices=voices, lang=lang))
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
    caller = context.get("caller") or {}
    # No menu and no PIN, so this is where Tomi says who she is and that she is automated.
    await voices.say(session, lang, line(lang, "greeting_named", first_name=caller.get("first_name") or first_name))
    controller.to(CallState.LISTENING)
    session.update_agent(TomiAgent(controller=controller, backend=backend, voices=voices, context=context, lang=lang))


if __name__ == "__main__":
    cli.run_app(server)
