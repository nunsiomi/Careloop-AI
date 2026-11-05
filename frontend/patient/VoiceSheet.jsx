import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Phone, PhoneOff } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { connectLiveVoice } from '../shared/live-voice.js';
import { languageInfo } from '../shared/languages.js';
import { useDialogFocus } from '../shared/ui.jsx';
import { PRESENTER } from '../shared/presenter.js';

// Browser voice (doc v2, flow D). A "livekit" session talks to the real Tomi worker (voice/tomi_agent.py)
// through LiveKit: the patient just speaks, and captions come from the worker. A "mock" session is the scripted
// stand-in: the patient picks what to say from quick phrases, and every Tomi line comes from the API.
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
  const [phrases, setPhrases] = useState([]);
  const [escalation, setEscalation] = useState(null);
  const [error, setError] = useState(null);
  const [needsTap, setNeedsTap] = useState(false);
  const timer = useRef(null);
  const live = useRef(null);
  const language = languageInfo(patient.language);

  const finish = () => {
    window.clearTimeout(timer.current);
    live.current?.disconnect();
    if (session?.id && session.mode === 'mock') CareLoopAPI.endVoiceSession(session.id).catch(() => {});
    onClose();
  };

  const showCaption = ({ key, speaker, transcript }) => {
    setTurns((current) => {
      const index = current.findIndex((turn) => turn.key === key);
      if (index === -1) return current.concat({ key, speaker, transcript, confidence: null });
      const next = current.slice();
      next[index] = { ...next[index], transcript };
      return next;
    });
  };

  const startLive = async (created) => {
    setSession(created);
    try {
      live.current = await connectLiveVoice(created, {
        phase: setPhase,
        caption: showCaption,
        escalation: () => setEscalation({ call_number: support.emergency_number }),
        needsTap: setNeedsTap,
        ended: () => setPhase('ended')
      });
    } catch (connectError) {
      setError(connectError?.name === 'NotAllowedError'
        ? 'Tomi needs your microphone. Allow it in your browser settings, or type instead.'
        : 'Could not connect to Tomi. Check your connection, or type instead.');
      setPhase('unavailable');
    }
  };
  useDialogFocus(sheetRef, finish, '.voice-end');

  const applyResult = (result) => {
    setTurns((current) => current.concat(result.turns.map((turn) => ({ ...turn, key: `${turn.at}-${Math.random()}` }))));
    setPhase('speaking');
    setKeypad([]);
    if (result.escalation) setEscalation(result.escalation);
    const spoken = result.turns.map((turn) => turn.transcript).join(' ');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (result.ended) { setPhase('ended'); return; }
      setPhase('listening');
      setKeypad(result.keypad || []);
    }, speakingTime(spoken));
  };

  useEffect(() => {
    if (started.current) return undefined;
    started.current = true;
    (async () => {
      try {
        const [created, demo] = await Promise.all([CareLoopAPI.createVoiceSession({ patient_id: patient.id, language: patient.language }), CareLoopAPI.getVoiceDemoPhrases().catch(() => ({ phrases: [] }))]);
        if (created.session.mode === 'livekit') {
          await startLive(created.session);
          return;
        }
        if (created.session.mode !== 'mock') {
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
    return () => {
      window.clearTimeout(timer.current);
      live.current?.disconnect();
    };
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

      {session?.mode === 'livekit' && !['ended', 'unavailable'].includes(phase) && (
        <div className="voice-panel">
          {needsTap
            ? <button type="button" className="btn btn-lg voice-light" onClick={() => live.current?.startAudio().then(() => setNeedsTap(false))}>Tap to hear Tomi</button>
            : <p className="voice-hint">Just speak. Tomi can hear you, and stops when you talk.</p>}
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

      {listening && (
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
