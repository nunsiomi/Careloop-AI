# Tomi voice worker

Tomi's phone and browser voice. It runs as a LiveKit Agents worker with Spitch for speech in Hausa, Yoruba, Igbo
and English, and Groq for replies. It started from [Tech-sis123/agricall](https://github.com/Tech-sis123/agricall)
(used with permission). Owner: Nunsi.

| File | What it does |
|---|---|
| `tomi_agent.py` | The worker: language menu, PIN check, safety check on every turn, check-in conversation |
| `call_controller.py` | Call states (section 7.3 of the project documentation), keypad input, PIN tries |
| `backend_client.py` | Calls to the CareLoop backend, plus a mock with the sample patient Zainab |
| `prompts/lines.json` | Tomi's fixed lines in four languages (Hausa, Yoruba and Igbo still need a native-speaker check) |
| `test_voice.py` | Tests that run without any keys: `python -m pytest voice` |

## How a call goes

1. **Greeting and language menu.** Tomi says who she is, then reads the language options, each in its own
   language: 1 Hausa, 2 Yoruba, 3 Igbo, 4 English. On an outgoing call she already knows the patient's language
   and skips the menu.
2. **PIN.** The patient types their 4-digit CareLoop PIN (the same PIN as the app). An unknown number and a wrong
   PIN get the same answer, and 5 wrong PINs lock it. Nothing about the patient's care is said before this.
   Browser voice skips the PIN, because the patient has already signed in to the app.
3. **Check-in.** Tomi loads the approved plan from the backend and asks how the patient is getting on. She may
   only use what is in the plan; any medical question goes to the care team.
4. **Safety on every turn.** Each thing the patient says goes to the backend's safety check before the model
   sees it. A red flag skips the model: Tomi plays the emergency line, the backend opens an escalation, and Tomi
   repeats that line for the rest of the call.

The worker never touches the database. It only calls the backend routes listed in `docs/api_shapes.md`
("Voice worker").

## Keys you need

Put them in the `.env` file at the repository root (copy `.env.example`). Never commit `.env`.

**LiveKit** (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`)
1. Sign up at [cloud.livekit.io](https://cloud.livekit.io) and create a project (the free plan is enough).
2. In the project, open **Settings → API keys** and create a key.
3. Copy the three values it shows: the URL (starts with `wss://` and ends in `.livekit.cloud`), the API key
   and the secret. The secret is shown once, so paste it into `.env` straight away.

**Groq** (`GROQ_API_KEY`): [console.groq.com](https://console.groq.com) → API Keys → Create API Key.

**Spitch** (`SPITCH_API_KEY`): sign up at [spitch.app](https://spitch.app), open the developer dashboard and
create an API key. Check which voices your account has for each language and set `SPITCH_VOICE_HA`, `_YO`,
`_IG` and `_EN` to match.

**Phone calls** (`LIVEKIT_SIP_TRUNK_ID`): needed only for real phone calls, not for testing. See section 1 of
`docs/launch-checklist.md`.

## Run it

```
cd voice
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python tomi_agent.py console    # talk to Tomi with your computer's microphone (as Zainab, no PIN)
python tomi_agent.py dev        # connect the worker to your LiveKit project, ready for calls
python dial.py +2348031234567   # with dev running: Tomi rings that phone (needs a SIP trunk)
```

The worker registers under the name `tomi`, so LiveKit only sends it rooms that ask for `tomi` by name: phone
calls through a dispatch rule, `dial.py`, and later the app's voice button. Set `VOICE_TEST_PHONE` in `.env` to
your own number so calls to and from it count as Zainab's.

`console` and the Playground use the sample patient Zainab (Hausa) while `VOICE_USE_MOCKS=1`. To test in another
language, set `TOMI_TEST_LANGUAGE` in `.env` to `en`, `yo` or `ig`. Phone calls need a
SIP trunk: dial in, choose a language, and type PIN `1234` from `+2348000000101` (the sample number).

## Talk to Tomi in the app (browser voice, free)

1. Keep `python tomi_agent.py dev` running.
2. In `frontend/`, `npm run dev`, and open the patient app as Zainab (`0800 000 0101`, PIN `1234`).
3. Tap Tomi's voice button and allow the microphone. Tomi greets you; just speak.

The app gets its LiveKit token from `frontend/api/voice/sessions.js`, which reads the LiveKit keys from the root
`.env`. On the Vercel preview, add `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` to the Vercel project's
environment variables; the worker still has to be running somewhere (your laptop, or deployed). Without those keys,
or with `?voice=mock`, the app uses the scripted voice demo instead.

## Phone calls with Telnyx (recommended)

1. In Telnyx: buy a voice number, create an Outbound Voice Profile that allows Nigeria, and create a SIP
   connection (FQDN type) pointing at your LiveKit SIP host, port 5060, with credentials for outbound calls.
   Attach the number and the profile to the connection.
2. In `.env`, fill in `TELNYX_PHONE_NUMBER`, `TELNYX_SIP_USERNAME` and `TELNYX_SIP_PASSWORD`.
3. `python setup_sip.py telnyx` once, and copy the `LIVEKIT_SIP_TRUNK_ID` it prints into `.env`.
4. `python tomi_agent.py dev`, then `python dial.py +234…` in a second terminal.

## Phone calls on a Twilio trial (no SIP trunk)

Twilio's trial blocks SIP trunking and TwiML Bins, but it still fetches call instructions from a web address
you run. `twiml_server.py` is that address: it hands Twilio the instructions to pass the call to LiveKit, only
when Twilio's signature checks out, and opens a free Cloudflare tunnel so Twilio can reach your laptop.

1. Install the tunnel once: `winget install Cloudflare.cloudflared`, then open a new terminal.
2. In `.env`, fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `LIVEKIT_SIP_URI` (from
   LiveKit Cloud → Settings), and make up `LIVEKIT_SIP_USERNAME` and a long `LIVEKIT_SIP_PASSWORD`. Leave
   `LIVEKIT_SIP_TRUNK_ID` empty.
3. `python setup_sip.py twilio` once.
4. Three terminals, each with `.venv` active: `python twiml_server.py`, `python tomi_agent.py dev`, and
   `python dial.py +234…`.
5. Optional, for people ringing your Twilio number: set the number's Voice webhook (HTTP POST) to the
   `/twiml/inbound` address `twiml_server.py` prints. The tunnel address changes every time it starts.

Trial limits: Twilio only rings verified caller IDs, plays a trial message, and asks for a key press before
connecting. Calling the US trial number from a Nigerian phone costs international airtime.

## Before real patients

- A native speaker checks every Hausa, Yoruba and Igbo line in `prompts/lines.json`, and sets `checked` to true.
- The clinical mentor approves the emergency line and `backend/app/safety/red_flags.json`. The mock's red-flag
  check is a short English-only placeholder and will not catch a red flag said in Hausa, Yoruba or Igbo.
- Olamide's backend provides the "Voice worker" routes, then set `VOICE_USE_MOCKS=0`.
- Test how well the Groq model speaks Hausa, Yoruba and Igbo; change `GROQ_MODEL` if needed.
