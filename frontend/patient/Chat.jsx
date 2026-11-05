import { useEffect, useRef, useState } from 'react';
import { Mic, Phone, SendHorizontal } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { formatTime } from '../shared/format.js';
import { ErrorNote, LoadingBlock, useAsync } from '../shared/ui.jsx';

const PROBLEMS = [
  { id: 'cost', label: 'It costs too much' },
  { id: 'transport', label: 'Getting there is hard' },
  { id: 'stock', label: 'The medicine is not in stock' },
  { id: 'understanding', label: 'I do not understand' }
];

export default function ChatScreen({ patient, refreshKey, headingRef, onTalk }) {
  const query = useAsync(() => CareLoopAPI.getMessages(patient.id), [patient.id, refreshKey]);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [escalation, setEscalation] = useState(null);
  const [asked, setAsked] = useState(false);
  const logRef = useRef(null);
  const inputRef = useRef(null);
  // Tomi's welcome sits after the conversation so far, so it is the first thing seen on opening the chat.
  const welcome = query.data?.welcome;
  const welcomeAt = query.data?.messages.length ?? 0;

  useEffect(() => { if (query.data) setMessages(query.data.messages); }, [query.data]);
  useEffect(() => { logRef.current?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }); }, [messages.length, sending]);

  const send = async (payload, { focusLog = false } = {}) => {
    setAsked(true);
    setSending(true);
    setError(null);
    const optimistic = { id: `local-${Date.now()}`, direction: 'patient', original_text: payload.original_text, created_at: new Date().toISOString() };
    setMessages((current) => current.map((message) => (payload.task_id && message.task_id === payload.task_id ? { ...message, answered: true } : message)).concat(optimistic));
    try {
      const response = await CareLoopAPI.sendMessage(patient.id, { language: patient.language, ...payload });
      setMessages((current) => current.concat({ ...response.reply, barrier: response.barrier || null }));
      if (response.escalation) setEscalation({ text: response.reply.original_text, number: response.escalation.call_number });
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setSending(false);
      if (focusLog) logRef.current?.focus({ preventScroll: true });
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    if (await send({ original_text: value })) setText('');
    inputRef.current?.focus();
  };

  return (
    <div className="screen chat-screen">
      <div className="chat-head">
        <h1 ref={headingRef} tabIndex={-1} className="screen-title">Chat with Tomi</h1>
        <button type="button" className="btn btn-secondary" onClick={onTalk}><Mic aria-hidden="true" size={18} />Talk instead</button>
      </div>

      {escalation && (
        <aside className="urgent-banner" role="alert">
          <p>{escalation.text}</p>
          <a className="btn btn-lg urgent-call" href={`tel:${escalation.number}`}><Phone aria-hidden="true" size={20} />Call {escalation.number}</a>
        </aside>
      )}

      {query.loading && !query.data && <LoadingBlock lines={4} />}
      <ErrorNote error={query.error} onRetry={query.reload} />

      <div ref={logRef} className="chat-log" role="log" aria-label="Conversation with Tomi" tabIndex={0}>
        {query.data && !messages.length && !welcome && <p className="soft-note">Ask Tomi about your plan, or tell Tomi how things are going.</p>}
        {messages.slice(0, welcomeAt).map((message) => (
          <ChatMessage key={message.id} message={message} disabled={sending} onQuick={(payload) => send(payload, { focusLog: true })} />
        ))}
        {welcome && (
          <div className="bubble-row is-tomi">
            <span className="tomi-dot" aria-hidden="true" />
            <div className="bubble">
              <span className="sr-only">Tomi said: </span>
              <p className="bubble-text">{welcome.text}</p>
              {!asked && welcome.suggestions.length > 0 && (
                <div className="suggestions" role="group" aria-label="Questions you can tap">
                  {welcome.suggestions.map((suggestion) => (
                    <button key={suggestion} type="button" className="btn suggestion" disabled={sending} onClick={() => send({ original_text: suggestion }, { focusLog: true })}>{suggestion}</button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        {messages.slice(welcomeAt).map((message) => (
          <ChatMessage key={message.id} message={message} disabled={sending} onQuick={(payload) => send(payload, { focusLog: true })} />
        ))}
        {sending && <div className="typing" role="status" aria-label="Tomi is writing"><span /><span /><span /></div>}
      </div>

      {error && <p className="error-text" role="alert">{error}</p>}

      <form className="composer" onSubmit={submit}>
        <label htmlFor="chat-input" className="sr-only">Message to Tomi</label>
        <input id="chat-input" ref={inputRef} className="input" autoComplete="off" enterKeyHint="send" placeholder="Type a message" value={text} onChange={(event) => setText(event.target.value)} />
        <button type="submit" className="btn btn-primary btn-icon composer-send" disabled={sending || !text.trim()} aria-label="Send"><SendHorizontal aria-hidden="true" /></button>
      </form>
    </div>
  );
}

function ChatMessage({ message, disabled, onQuick }) {
  const [picking, setPicking] = useState(false);
  const mine = message.direction === 'patient';
  const awaitingTask = !mine && message.task_id && !message.answered;

  return (
    <div className={`bubble-row ${mine ? 'is-mine' : 'is-tomi'}`}>
      {!mine && <span className="tomi-dot" aria-hidden="true" />}
      <div className="bubble">
        <span className="sr-only">{mine ? 'You said' : 'Tomi said'}: </span>
        <p className="bubble-text">{message.original_text}</p>
        {!mine && message.number_check_passed === false && <p className="bubble-note">Shown in English so the numbers stay exact.</p>}
        <p className="bubble-time">{formatTime(message.created_at)}</p>

        {awaitingTask && !picking && (
          <div className="bubble-actions">
            <button type="button" className="btn btn-primary" disabled={disabled} onClick={() => onQuick({ original_text: 'Done', task_id: message.task_id, quick_reply: 'done' })}>Done</button>
            <button type="button" className="btn btn-secondary" disabled={disabled} onClick={() => onQuick({ original_text: 'Not yet', task_id: message.task_id, quick_reply: 'not_yet' })}>Not yet</button>
            <button type="button" className="btn btn-quiet" disabled={disabled} onClick={() => setPicking(true)}>Problem</button>
          </div>
        )}
        {awaitingTask && picking && (
          <div className="bubble-actions is-stacked" role="group" aria-label="What is the problem?">
            {PROBLEMS.map((problem, index) => (
              <button key={problem.id} type="button" className="btn btn-secondary" disabled={disabled} autoFocus={index === 0} onClick={() => onQuick({ original_text: problem.label, task_id: message.task_id, quick_reply: problem.id })}>{problem.label}</button>
            ))}
          </div>
        )}

        {message.barrier?.options?.length > 0 && (
          <div className="option-card">
            {message.barrier.options.map((option) => (
              <div key={option.name} className="option-item">
                <p className="option-name">{option.name}</p>
                <p className="hint">{option.type}{option.distance ? `, ${option.distance}` : ''}</p>
                {option.note && <p className="hint">{option.note}</p>}
                {option.phone && <a className="btn btn-secondary" href={`tel:${option.phone}`}><Phone aria-hidden="true" size={16} />{option.phone}</a>}
              </div>
            ))}
            {!message.barrierAnswered && (
              <div className="bubble-actions">
                <button type="button" className="btn btn-primary" disabled={disabled} onClick={() => { message.barrierAnswered = true; onQuick({ original_text: 'It worked', quick_reply: 'worked' }); }}>It worked</button>
                <button type="button" className="btn btn-secondary" disabled={disabled} onClick={() => { message.barrierAnswered = true; onQuick({ original_text: 'It did not work', quick_reply: 'did_not_work' }); }}>It did not work</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
