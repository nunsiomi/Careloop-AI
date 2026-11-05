import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, CalendarPlus, Check, FlaskConical, Mic, MicOff, NotebookPen, Pill, PhoneOutgoing, SendHorizontal, Trash2, X, MessageSquareText } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { useDashboard } from './shell.jsx';

const KIND = {
  medicine: { icon: Pill, label: 'Medicine reminders' },
  test: { icon: FlaskConical, label: 'Test' },
  visit: { icon: CalendarPlus, label: 'Visit' },
  send_text: { icon: MessageSquareText, label: 'Text message' },
  call_patient: { icon: PhoneOutgoing, label: 'Tomi call' },
  note: { icon: NotebookPen, label: 'Note for the care team' }
};

const STARTERS = [
  'Book Grace a diabetes review next Tuesday at 9:30 in the Diabetes Clinic',
  'Add a kidney function test for Zainab by Friday',
  'Note that Tola’s son will bring her to clinic from now on'
];

// ISO time to the value a datetime-local input expects, in local time.
const toLocalInput = (iso) => {
  if (!iso) return '';
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null);

/* Voice typing with the browser's own speech recognition. Chrome and Edge support it; elsewhere the mic is hidden. */
function useDictation(onText) {
  const Recognition = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;
  const [listening, setListening] = useState(false);
  const [error, setError] = useState(null);
  const recognition = useRef(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const stop = useCallback(() => { recognition.current?.stop(); }, []);
  const start = useCallback(() => {
    if (!Recognition) return;
    setError(null);
    const rec = new Recognition();
    rec.lang = 'en-NG';
    rec.interimResults = true;
    rec.continuous = true;
    rec.onresult = (event) => {
      let text = '';
      for (let index = 0; index < event.results.length; index += 1) text += event.results[index][0].transcript;
      onTextRef.current(text.trim());
    };
    rec.onerror = (event) => setError(event.error === 'not-allowed' || event.error === 'service-not-allowed'
      ? 'The microphone is blocked. Allow it from the icon in the address bar, or type instead.'
      : event.error === 'no-speech' ? 'I did not hear anything. Try again, closer to the microphone.' : 'Voice typing stopped. Try again, or type instead.');
    rec.onend = () => setListening(false);
    recognition.current = rec;
    rec.start();
    setListening(true);
  }, [Recognition]);

  useEffect(() => () => recognition.current?.abort(), []);
  return { supported: Boolean(Recognition), listening, error, start, stop };
}

export function AssistantPanel({ onClose, routePatientId }) {
  const { user, refreshCounts, dataChanged } = useDashboard();
  const [patients, setPatients] = useState([]);
  const [patientId, setPatientId] = useState(routePatientId || '');
  const [text, setText] = useState('');
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const logRef = useRef(null);
  const baseText = useRef('');
  const dictation = useDictation((spoken) => setText(`${baseText.current}${baseText.current && spoken ? ' ' : ''}${spoken}`));

  useEffect(() => { CareLoopAPI.listPatients().then((response) => setPatients(response.patients)).catch(() => {}); }, []);
  useEffect(() => { if (routePatientId) setPatientId(routePatientId); }, [routePatientId]);
  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' }); }, [turns, busy]);
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape' && !event.defaultPrevented && !document.querySelector('.modal-backdrop')) onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const updateTurn = (id, change) => setTurns((current) => current.map((turn) => (turn.id === id ? { ...turn, ...(typeof change === 'function' ? change(turn) : change) } : turn)));

  const draft = async (instruction, forPatient = patientId) => {
    if (!instruction.trim() || busy) return;
    if (dictation.listening) dictation.stop();
    setBusy(true);
    setError(null);
    const id = `${Date.now()}`;
    setTurns((current) => [...current, { id, instruction: instruction.trim(), status: 'drafting' }]);
    setText('');
    try {
      const response = await CareLoopAPI.draftAssistantActions({ text: instruction, patient_id: forPatient || undefined });
      updateTurn(id, { status: 'draft', draft: response.draft });
      if (response.draft.patient && !patientId) setPatientId(response.draft.patient.id);
    } catch (requestError) {
      updateTurn(id, { status: 'failed', message: requestError.message });
    }
    setBusy(false);
  };

  const choosePatient = (turn, id) => {
    setPatientId(id);
    setTurns((current) => current.filter((item) => item.id !== turn.id));
    draft(turn.instruction, id);
  };

  const confirm = async (turn) => {
    updateTurn(turn.id, { status: 'saving' });
    try {
      const response = await CareLoopAPI.applyAssistantActions({ patient_id: turn.draft.patient.id, actions: turn.draft.actions, by: user.name });
      updateTurn(turn.id, { status: 'applied', results: response.results });
      refreshCounts();
      dataChanged();
    } catch (requestError) {
      updateTurn(turn.id, { status: 'draft', message: requestError.message });
    }
  };

  const editAction = (turn, actionId, change) => updateTurn(turn.id, (current) => ({
    draft: { ...current.draft, actions: current.draft.actions.map((action) => (action.id === actionId ? { ...action, ...change } : action)) }
  }));
  const removeAction = (turn, actionId) => updateTurn(turn.id, (current) => ({
    draft: { ...current.draft, actions: current.draft.actions.filter((action) => action.id !== actionId) }
  }));

  const toggleMic = () => {
    if (dictation.listening) { dictation.stop(); return; }
    baseText.current = text.trim();
    dictation.start();
  };

  const selected = patients.find((patient) => patient.id === patientId);

  return (
    <aside className="assistant" aria-labelledby="assistant-title">
      <header className="assistant-head">
        <div>
          <h2 id="assistant-title">Assistant</h2>
          <p>Type or say what you want done for a patient. Nothing is saved until you confirm.</p>
        </div>
        <button type="button" className="btn btn-quiet btn-icon" onClick={onClose} aria-label="Close the assistant"><X aria-hidden="true" size={20} /></button>
      </header>

      <div className="field assistant-patient">
        <label htmlFor="assistant-patient">Patient</label>
        <select id="assistant-patient" className="select" value={patientId} onChange={(event) => setPatientId(event.target.value)}>
          <option value="">Work it out from what I say</option>
          {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.name}</option>)}
        </select>
      </div>

      <div className="assistant-log" ref={logRef} role="log" aria-live="polite" aria-label="Assistant conversation">
        {!turns.length && (
          <div className="assistant-empty">
            <p>You could say:</p>
            <ul>
              {STARTERS.map((starter) => <li key={starter}><button type="button" className="assistant-starter" onClick={() => { setText(starter); inputRef.current?.focus(); }}>{starter}</button></li>)}
            </ul>
            <p className="hint">It can add medicine and test reminders, book visits, send an email reminder, ask Tomi to call, or write a note on the timeline.</p>
          </div>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className="assistant-turn">
            <p className="assistant-said"><span className="sr-only">You: </span>{turn.instruction}</p>
            {turn.status === 'drafting' && <p className="assistant-reply is-thinking">Working out the changes…</p>}
            {turn.status === 'failed' && <p className="assistant-reply"><AlertCircle aria-hidden="true" size={16} />{turn.message}</p>}
            {turn.draft && <DraftCard turn={turn} onChoosePatient={choosePatient} onEdit={editAction} onRemove={removeAction} onConfirm={confirm} onDiscard={() => updateTurn(turn.id, { status: 'discarded' })} />}
          </div>
        ))}
      </div>

      <form className="assistant-compose" onSubmit={(event) => { event.preventDefault(); draft(text); }}>
        <label htmlFor="assistant-input" className="sr-only">Instruction{selected ? ` for ${selected.name}` : ''}</label>
        <textarea
          id="assistant-input"
          ref={inputRef}
          className="textarea"
          rows={3}
          value={text}
          placeholder={selected ? `What should change for ${selected.name.split(' ')[0]}?` : 'Book Grace a review next Tuesday at 9:30'}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); draft(text); } }}
          aria-describedby="assistant-compose-hint"
        />
        <div className="assistant-compose-row">
          <p id="assistant-compose-hint" className="hint" aria-live="polite">
            {dictation.listening ? 'Listening. Speak, then press the microphone again to stop.' : dictation.error || 'Enter sends. Shift and Enter adds a new line.'}
          </p>
          {dictation.supported && (
            <button type="button" className={`btn btn-secondary btn-icon assistant-mic${dictation.listening ? ' is-listening' : ''}`} onClick={toggleMic} aria-pressed={dictation.listening} aria-label={dictation.listening ? 'Stop voice typing' : 'Speak instead of typing'}>
              {dictation.listening ? <MicOff aria-hidden="true" size={20} /> : <Mic aria-hidden="true" size={20} />}
            </button>
          )}
          <button type="submit" className="btn btn-primary btn-icon" disabled={busy || !text.trim()} aria-label="Send to the assistant"><SendHorizontal aria-hidden="true" size={20} /></button>
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
      </form>
    </aside>
  );
}

function DraftCard({ turn, onChoosePatient, onEdit, onRemove, onConfirm, onDiscard }) {
  const { draft, status, results } = turn;
  if (draft.needs_patient) {
    return (
      <div className="assistant-reply">
        <p>{draft.reply}</p>
        {status === 'draft' && <div className="assistant-choices">{draft.choices.map((choice) => <button key={choice.id} type="button" className="btn btn-secondary" onClick={() => onChoosePatient(turn, choice.id)}>{choice.name}</button>)}</div>}
      </div>
    );
  }

  if (status === 'applied') {
    return (
      <div className="assistant-reply">
        <ul className="assistant-results">
          {results.map((result) => (
            <li key={result.id} className={result.ok ? 'is-ok' : 'is-failed'}>
              {result.ok ? <Check aria-hidden="true" size={16} /> : <AlertCircle aria-hidden="true" size={16} />}
              <span><span className="sr-only">{result.ok ? 'Done: ' : 'Not done: '}</span>{result.summary}</span>
            </li>
          ))}
        </ul>
        <Link className="assistant-link" to={`/patients/${draft.patient.id}`}>Open {draft.patient.name}’s record</Link>
      </div>
    );
  }

  if (status === 'discarded') return <p className="assistant-reply muted">Discarded. Nothing was changed.</p>;

  const usable = draft.actions.filter((action) => !action.blocked);
  return (
    <div className="assistant-reply">
      <p>{draft.reply}</p>
      <ul className="assistant-actions">
        {draft.actions.map((action) => <ActionCard key={action.id} action={action} draft={draft} onEdit={(change) => onEdit(turn, action.id, change)} onRemove={() => onRemove(turn, action.id)} />)}
      </ul>
      {turn.message && <p className="field-error" role="alert">{turn.message}</p>}
      <div className="assistant-confirm">
        <button type="button" className="btn btn-primary" disabled={!usable.length || status === 'saving'} onClick={() => onConfirm(turn)}>
          {status === 'saving' ? 'Saving…' : usable.length === 1 ? 'Confirm change' : `Confirm ${usable.length} changes`}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onDiscard} disabled={status === 'saving'}>Discard</button>
      </div>
    </div>
  );
}

function ActionCard({ action, draft, onEdit, onRemove }) {
  const meta = KIND[action.kind];
  const Icon = meta.icon;
  const field = (name) => `act-${action.id}-${name}`;
  const first = draft.patient.name.split(' ')[0];

  return (
    <li className={`assistant-action${action.blocked ? ' is-blocked' : ''}`}>
      <div className="assistant-action-head">
        <span className="assistant-action-kind"><Icon aria-hidden="true" size={16} />{meta.label}</span>
        <button type="button" className="btn btn-quiet btn-icon" onClick={onRemove} aria-label={`Remove ${meta.label.toLowerCase()}`}><Trash2 aria-hidden="true" size={16} /></button>
      </div>

      {!action.blocked && action.kind === 'medicine' && (
        <div className="assistant-fields">
          <div className="field span-2"><label htmlFor={field('title')}>Medicine and dose</label><input id={field('title')} className="input" value={action.title} onChange={(event) => onEdit({ title: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor={field('detail')}>How much each time</label><input id={field('detail')} className="input" value={action.detail} onChange={(event) => onEdit({ detail: event.target.value })} /></div>
          <div className="field"><label htmlFor={field('times')}>Times</label><input id={field('times')} className="input" value={action.times.join(', ')} onChange={(event) => onEdit({ times: event.target.value.split(/[,\s]+/).filter(Boolean) })} aria-describedby={field('times-hint')} /><p id={field('times-hint')} className="hint">24-hour, such as 08:00, 20:00</p></div>
          <div className="field"><label htmlFor={field('days')}>For how many days</label><input id={field('days')} className="input" type="number" min="1" max="90" value={action.days} onChange={(event) => onEdit({ days: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor={field('start')}>Starting</label><input id={field('start')} className="input" type="date" value={action.starts_on} onChange={(event) => onEdit({ starts_on: event.target.value })} /></div>
        </div>
      )}
      {!action.blocked && action.kind === 'test' && (
        <div className="assistant-fields">
          <div className="field span-2"><label htmlFor={field('title')}>Test</label><input id={field('title')} className="input" value={action.title} onChange={(event) => onEdit({ title: event.target.value })} /></div>
          <div className="field"><label htmlFor={field('detail')}>Where</label><input id={field('detail')} className="input" value={action.detail} onChange={(event) => onEdit({ detail: event.target.value })} /></div>
          <div className="field"><label htmlFor={field('due')}>Due</label><input id={field('due')} className="input" type="datetime-local" value={toLocalInput(action.due_at)} onChange={(event) => onEdit({ due_at: fromLocalInput(event.target.value) })} /></div>
        </div>
      )}
      {!action.blocked && action.kind === 'visit' && (
        <div className="assistant-fields">
          <div className="field"><label htmlFor={field('what')}>Visit</label><input id={field('what')} className="input" value={action.what} onChange={(event) => onEdit({ what: event.target.value })} /></div>
          <div className="field"><label htmlFor={field('where')}>Where</label><input id={field('where')} className="input" value={action.where} onChange={(event) => onEdit({ where: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor={field('when')}>When</label><input id={field('when')} className="input" type="datetime-local" value={toLocalInput(action.starts_at)} onChange={(event) => onEdit({ starts_at: fromLocalInput(event.target.value) })} /></div>
        </div>
      )}
      {!action.blocked && action.kind === 'send_text' && (
        <div className="assistant-fields">
          <div className="field span-2">
            <label htmlFor={field('template')}>Which message</label>
            <select id={field('template')} className="select" value={action.template} onChange={(event) => onEdit({ template: event.target.value })}>
              {draft.templates.map((template) => <option key={template.id} value={template.id}>{template.title}</option>)}
            </select>
          </div>
          <p className="assistant-preview span-2">{draft.templates.find((template) => template.id === action.template)?.body}</p>
        </div>
      )}
      {!action.blocked && action.kind === 'call_patient' && <p className="assistant-plain">Tomi calls {first} now, in the language on their record.</p>}
      {!action.blocked && action.kind === 'note' && (
        <div className="field">
          <label htmlFor={field('note')} className="sr-only">Note</label>
          <textarea id={field('note')} className="textarea" rows={2} value={action.text} onChange={(event) => onEdit({ text: event.target.value })} />
        </div>
      )}

      {action.issues.length > 0 && (
        <ul className={`assistant-issues${action.blocked ? ' is-blocked' : ''}`}>
          {action.issues.map((issue) => <li key={issue}><AlertCircle aria-hidden="true" size={15} />{issue}</li>)}
        </ul>
      )}
    </li>
  );
}
