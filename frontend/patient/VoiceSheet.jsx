import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Delete, Phone, PhoneOff } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { languageInfo } from '../shared/languages.js';
import { useDialogFocus } from '../shared/ui.jsx';
import { PRESENTER } from '../shared/presenter.js';

// Browser voice (doc v2, flow D). With mocks, a scripted session stands in for LiveKit + Spitch:
// the patient picks what to say from quick phrases, and every Tomi line comes from the API.
const STATE_LABEL = {
  connecting: 'Connecting to Tomi…',
  speaking: 'Tomi is speaking',
  listening: 'Tomi is listening',
  thinking: 'Tomi is thinking…',
  ended: 'Conversation ended',
  unavailable: 'Voice is not available right now'
};

const speakingTime = (text) => Math.min(4200, 900 + text.length * 22);

export default function VoiceSheet({ patient, support, onClose }) {
  const sheetRef = useRef(null);
  const started = useRef(false);
  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState('connecting');
  const [turns, setTurns] = useState([]);
  const [keypad, setKeypad] = useState([]);
  const [pinMode, setPinMode] = useState(false);
  const [pin, setPin] = useState('');
  const [phrases, setPhrases] = useState([]);
  const [escalation, setEscalation] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);
  const language = languageInfo(patient.language);

  const finish = () => {
    window.clearTimeout(timer.current);
    if (session?.id) CareLoopAPI.endVoiceSession(session.id).catch(() => {});
    onClose();
  };
  useDialogFocus(sheetRef, finish, '.voice-end');

  const applyResult = (result) => {
    setTurns((current) => current.concat(result.turns.map((turn) => ({ ...turn, key: `${turn.at}-${Math.random()}` }))));
    setPhase('speaking');
    setKeypad([]);
    setPinMode(false);
    if (result.escalation) setEscalation(result.escalation);
    const spoken = result.turns.map((turn) => turn.transcript).join(' ');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (result.ended) { setPhase('ended'); return; }
      setPhase('listening');
      setKeypad(result.keypad || []);
      setPinMode(Boolean(result.pin_required));
    }, speakingTime(spoken));
  };

  useEffect(() => {
    if (started.current) return undefined;
    started.current = true;
    (async () => {
      try {
        const [created, demo] = await Promise.all([CareLoopAPI.createVoiceSession({ patient_id: patient.id }), CareLoopAPI.getVoiceDemoPhrases().catch(() => ({ phrases: [] }))]);
        if (created.session.mode !== 'mock') {
          // TODO(Nunsi): connect livekit-client with created.session.url and created.session.token once the Tomi worker is live.
          setPhase('unavailable');
          return;
        }
        setSession(created.session);
        setPhrases(demo.phrases.filter((phrase) => PRESENTER || !phrase.presenter_only));
        applyResult(await CareLoopAPI.sendVoiceInput(created.session.id, null));
      } catch (requestError) {
        setError(requestError.message);
        setPhase('unavailable');
      }
    })();
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendInput = async (input, shown) => {
    if (!session || phase !== 'listening') return;
    setTurns((current) => current.concat({ speaker: 'patient', transcript: shown, confidence: input.confidence ?? null, key: `p-${Date.now()}` }));
    setPhase('thinking');
    setKeypad([]);
    try {
      applyResult(await CareLoopAPI.sendVoiceInput(session.id, input));
    } catch (requestError) {
      setError(requestError.message);
      setPhase('listening');
    }
  };

  const pressPinDigit = (digit) => {
    if (pin.length >= 4) return;
    const next = pin + digit;
    setPin(next);
    if (next.length === 4) { setPin(''); sendInput({ pin: next, digit: null }, 'PIN entered'); }
  };

  const latestTomi = [...turns].reverse().find((turn) => turn.speaker === 'tomi');
  const listening = phase === 'listening';

  return createPortal(
    <div className="voice-sheet" ref={sheetRef} role="dialog" aria-modal="true" aria-labelledby="voice-title">
      <header className="voice-top">
        <div>
          <h2 id="voice-title" className="voice-title">Tomi</h2>
          <p className="voice-meta">Speaking {language.native}{language.beta ? ' (beta)' : ''}</p>
        </div>
        <button type="button" className="btn voice-end" onClick={finish}><PhoneOff aria-hidden="true" size={18} />End</button>
      </header>

      <div className={`voice-stage phase-${phase}`}>
        <div className="voice-orb" aria-hidden="true"><span className="voice-orb-ring" /><span className="voice-orb-ring" /><span className="voice-orb-core" /></div>
        <p className="voice-state" role="status">{STATE_LABEL[phase]}</p>
        {latestTomi && <p className="voice-caption" aria-live="polite">{latestTomi.transcript}</p>}
      </div>

      {escalation && (
        <div className="voice-urgent" role="alert">
          <a className="btn btn-lg urgent-call" href={`tel:${escalation.call_number}`}><Phone aria-hidden="true" size={20} />Call {escalation.call_number}</a>
        </div>
      )}

      {phase === 'unavailable' && (
        <div className="voice-panel">
          <p>{error || 'Tomi cannot talk in the app right now. You can call Tomi on the phone or type instead.'}</p>
          <div className="voice-row">
            <a className="btn btn-lg voice-light" href={`tel:${support.tomi_number}`}><Phone aria-hidden="true" size={18} />Call Tomi</a>
            <a className="btn btn-lg voice-ghost" href="#/chat" onClick={finish}>Type instead</a>
          </div>
        </div>
      )}

      {pinMode && listening && (
        <div className="voice-panel">
          <p className="voice-panel-title">Enter your PIN</p>
          <p className="pin-dots" aria-label={`${pin.length} of 4 digits entered`}>{[0, 1, 2, 3].map((index) => <span key={index} className={index < pin.length ? 'is-filled' : ''} />)}</p>
          <div className="keypad" role="group" aria-label="Keypad">
            {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((digit) => <button key={digit} type="button" className="key" onClick={() => pressPinDigit(digit)}>{digit}</button>)}
            <span />
            <button type="button" className="key" onClick={() => pressPinDigit('0')}>0</button>
            <button type="button" className="key" aria-label="Delete last digit" onClick={() => setPin(pin.slice(0, -1))}><Delete aria-hidden="true" /></button>
          </div>
          {PRESENTER && session?.demo_pin && <p className="voice-hint">Presenter note: the PIN is {session.demo_pin}</p>}
        </div>
      )}

      {!pinMode && listening && (
        <div className="voice-panel">
          {keypad.length > 0 && (
            <div className="voice-options" role="group" aria-label="Press a number">
              {keypad.map((option) => (
                <button key={option.key} type="button" className="voice-option" onClick={() => sendInput({ digit: option.key }, `Pressed ${option.key}: ${option.label}`)}>
                  <span className="voice-option-key">{option.key}</span>{option.label}
                </button>
              ))}
            </div>
          )}
          {session?.mode === 'mock' && phrases.length > 0 && (
            <details className="voice-demo">
              <summary>Cannot talk right now? Tap what you want to say</summary>
              <div className="voice-phrases">
                {phrases.map((phrase) => (
                  <button key={phrase.label} type="button" className="voice-phrase" onClick={() => sendInput({ transcript: phrase.transcript, confidence: phrase.confidence }, phrase.transcript)}>
                    {phrase.label}{PRESENTER && <span>Heard with {Math.round(phrase.confidence * 100)}% confidence</span>}
                  </button>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {phase === 'ended' && (
        <div className="voice-panel">
          <p>Your care team can see what you told Tomi.</p>
          <button type="button" className="btn btn-lg voice-light" onClick={finish}>Close</button>
        </div>
      )}

      <details className="voice-transcript">
        <summary>Show what was said ({turns.length})</summary>
        <ol>
          {turns.map((turn) => (
            <li key={turn.key} className={`is-${turn.speaker}`}>
              <strong>{turn.speaker === 'tomi' ? 'Tomi' : 'You'}</strong> {turn.transcript}
              {turn.speaker === 'patient' && turn.confidence != null && turn.confidence < 0.6 && <em> (not clear)</em>}
            </li>
          ))}
        </ol>
      </details>
    </div>,
    document.body
  );
}
