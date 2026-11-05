import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Globe, Mail, MessageCircle, MessageSquareText, Mic, Monitor, Phone, PhoneIncoming, PhoneOutgoing, Stethoscope, User } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { LANGUAGES, READING_LEVELS } from '../shared/languages.js';
import { formatTime, groupByDay } from '../shared/format.js';
import { BetaChip, Modal, StatusBadge, useAsync, useInterval, useToast } from '../shared/ui.jsx';
import { PRESENTER } from '../shared/presenter.js';
import { useDashboard } from './shell.jsx';

/* ---------- channel and actor icons ---------- */

const CHANNEL_META = {
  voice: { icon: Phone, label: 'Phone call' }, phone: { icon: Phone, label: 'Phone call' }, browser_voice: { icon: Mic, label: 'Voice in the app' },
  web: { icon: MessageCircle, label: 'Chat' }, sms: { icon: MessageSquareText, label: 'Text message' }, email: { icon: Mail, label: 'Email' },
  dashboard: { icon: Monitor, label: 'Dashboard' }, clinic: { icon: Stethoscope, label: 'At clinic' }, system: { icon: Globe, label: 'System' }
};

export function ChannelLabel({ channel, iconOnly = false }) {
  const meta = CHANNEL_META[channel] || { icon: Globe, label: channel };
  const Icon = meta.icon;
  return iconOnly
    ? <span className="channel-icon" title={meta.label}><Icon aria-hidden="true" size={16} /><span className="sr-only">{meta.label}</span></span>
    : <span className="channel-label"><Icon aria-hidden="true" size={15} />{meta.label}</span>;
}

export function ConsentedChannels({ channels }) {
  if (!channels?.length) return <span className="muted">Not agreed yet</span>;
  return <span className="channel-set">{channels.map((channel) => <ChannelLabel key={channel} channel={channel} />)}</span>;
}

export const directionIcon = (direction) => (direction === 'inbound' ? PhoneIncoming : direction === 'browser' ? Mic : PhoneOutgoing);

/* ---------- timeline: provenance is the point ---------- */

const ACTOR_ICON = { patient: User, caregiver: User, clinician: Stethoscope, agent: Bot, system: Globe, provider: Globe };
const FILTERS = [
  { id: 'all', label: 'Everything' },
  { id: 'patient', label: 'Patient reports', match: (event) => ['patient', 'caregiver'].includes(event.actor_type) },
  { id: 'clinician', label: 'Clinician actions', match: (event) => event.actor_type === 'clinician' },
  { id: 'notes', label: 'Care-team notes', match: (event) => event.event_type === 'care_team_note' },
  { id: 'system', label: 'Agents, system and providers', match: (event) => ['agent', 'system', 'provider'].includes(event.actor_type) }
];

export function Timeline({ events, showPatient = false, compact = false, filterable = true }) {
  const [filter, setFilter] = useState('all');
  const active = FILTERS.find((item) => item.id === filter);
  const visible = active.match ? events.filter(active.match) : events;
  const groups = groupByDay(visible, 'reported_at');

  return (
    <div className={`timeline${compact ? ' is-compact' : ''}`}>
      {filterable && (
        <div className="filter-row" role="group" aria-label="Filter activity">
          {FILTERS.map((item) => (
            <button key={item.id} type="button" className="filter-chip" aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>
          ))}
        </div>
      )}
      {!visible.length && <p className="muted">Nothing here yet.</p>}
      {groups.map(([label, items]) => (
        <section key={label} className="timeline-day" aria-label={label}>
          <h3 className="timeline-day-title">{label}</h3>
          <ol className="timeline-list">
            {items.map((event) => {
              const ActorIcon = ACTOR_ICON[event.actor_type] || Globe;
              return (
                <li key={event.id} className={`timeline-item mark-${event.verification_status}`}>
                  <span className="timeline-mark" aria-hidden="true" />
                  <time className="timeline-time" dateTime={event.reported_at}>{formatTime(event.reported_at)}</time>
                  <div className="timeline-body">
                    <p className="timeline-summary">{showPatient && <strong>{event.patient_name}: </strong>}{event.summary}</p>
                    <p className="timeline-meta">
                      <span className="timeline-actor"><ActorIcon aria-hidden="true" size={14} />{event.actor_id}</span>
                      <ChannelLabel channel={event.source_channel} />
                      <StatusBadge kind="verification" status={event.verification_status} />
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}

/* ---------- call transcript ---------- */

export function Transcript({ call }) {
  if (!call.turns?.length) return <p className="muted">{call.status === 'failed' ? 'The call was not answered. Nothing was said.' : 'No transcript yet.'}</p>;
  return (
    <ol className="transcript">
      {call.turns.map((turn, index) => (
        <li key={index} className={`turn turn-${turn.speaker}`}>
          <p className="turn-speaker">{turn.speaker === 'tomi' ? 'Tomi' : 'Patient'}{turn.keypad ? ' (keypad)' : ''}</p>
          <p className="turn-text">{turn.transcript}</p>
          {turn.english && <p className="turn-english"><span>English: </span>{turn.english}</p>}
          {(turn.confidence != null || turn.confirmed) && (
            <p className="turn-meta">
              {turn.confidence != null && <span className={turn.confidence < 0.75 ? 'confidence-low' : ''}>Speech confidence {Math.round(turn.confidence * 100)}%</span>}
              {turn.confirmed && <span>Confirmed by patient</span>}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

/* ---------- call patient now (doc flow B, started by a clinician) ---------- */

const CALL_STEPS = ['initiated', 'ringing', 'answered', 'verified', 'completed'];

export function CallPatientDialog({ patient, onClose }) {
  const [call, setCall] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const { refreshCounts } = useDashboard();
  const live = call && !['completed', 'failed', 'disconnected'].includes(call.status);

  useInterval(async () => {
    try { const response = await CareLoopAPI.getCall(call.id); setCall(response.call); if (!['initiated', 'ringing', 'answered', 'verified'].includes(response.call.status)) refreshCounts(); } catch (requestError) { setError(requestError.message); }
  }, 1000, Boolean(live));

  const start = async () => {
    setBusy(true);
    setError(null);
    try { setCall((await CareLoopAPI.requestOutboundCall({ patient_id: patient.id, reason: 'clinician_check_in' })).call); } catch (requestError) { setError(requestError.message); }
    setBusy(false);
  };

  const [startHour, endHour] = (patient.contact_window || '').split('-');
  const nowTime = new Date().toTimeString().slice(0, 5);
  const outsideWindow = startHour && (nowTime < startHour || nowTime > endHour);
  const reached = call ? CALL_STEPS.indexOf(call.status === 'failed' ? 'ringing' : call.status) : -1;

  return (
    <Modal title={call ? `Calling ${patient.name}` : `Call ${patient.name} now`} onClose={onClose} wide>
      {!call && (
        <div className="stack-4">
          <dl className="facts">
            <div><dt>Phone</dt><dd>{patient.phone_e164}</dd></div>
            <div><dt>Language</dt><dd>{patient.language}</dd></div>
            <div><dt>Consent</dt><dd>{patient.channels?.includes('voice') ? 'Agreed to phone calls' : 'Has not agreed to phone calls'}</dd></div>
            <div><dt>Best time</dt><dd>{patient.contact_window || 'Not set'}</dd></div>
          </dl>
          <p className="note">Tomi says it is an automated assistant and asks for the patient's PIN before sharing anything. If someone else answers, or it reaches voicemail, Tomi gives no details.</p>
          {outsideWindow && <p className="note note-amber">This is outside the time {patient.name.split(' ')[0]} chose for calls ({patient.contact_window}).</p>}
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
            <button type="button" className="btn btn-call" onClick={start} disabled={busy || !patient.channels?.includes('voice')}><PhoneOutgoing aria-hidden="true" size={18} />{busy ? 'Starting…' : 'Start call'}</button>
          </div>
        </div>
      )}
      {call && (
        <div className="stack-4">
          <ol className="call-steps" aria-label="Call progress">
            {CALL_STEPS.map((step, index) => (
              <li key={step} className={index <= reached ? 'is-done' : ''} aria-current={index === reached ? 'step' : undefined}>{step === 'verified' ? 'PIN verified' : step[0].toUpperCase() + step.slice(1)}</li>
            ))}
          </ol>
          <p role="status"><StatusBadge kind="call" status={call.status} /> {call.outcome && <span className="muted">{call.outcome}</span>}</p>
          <div className="transcript-box" aria-live="polite"><Transcript call={call} /></div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>{live ? 'Close (call continues)' : 'Close'}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ---------- add patient ---------- */

export function AddPatientDialog({ onClose }) {
  const [form, setForm] = useState({ name: '', phone_e164: '+234', email: '', language: 'Hausa', literacy_level: 'basic', caregiver_mode: false, note: '' });
  const [notes, setNotes] = useState([]);
  const [stage, setStage] = useState('form');
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const toast = useToast();
  const { refreshCounts } = useDashboard();
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }));
  const languageBeta = useMemo(() => LANGUAGES.find((item) => item.name === form.language)?.beta, [form.language]);

  useEffect(() => { CareLoopAPI.listSampleNotes().then((response) => setNotes(response.notes)).catch(() => {}); }, []);

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.note.trim()) { setError('Add a name, an email address and the discharge note.'); return; }
    setError(null);
    setStage('drafting');
    try {
      const { patient } = await CareLoopAPI.createPatient({ name: form.name.trim(), phone_e164: form.phone_e164.trim(), email: form.email.trim(), language: form.language, literacy_level: form.literacy_level, caregiver_mode: form.caregiver_mode });
      await CareLoopAPI.createPlan({ patient_id: patient.id, source_note: form.note.trim() });
      toast('Patient added. The draft plan is ready for you to check.');
      refreshCounts();
      onClose();
      navigate(`/patients/${patient.id}/review`);
    } catch (requestError) { setError(requestError.message); setStage('form'); }
  };

  return (
    <Modal title="Add patient" onClose={onClose} wide initialFocus="#new-name">
      {stage === 'drafting' ? (
        <div className="drafting" role="status">
          <span className="drafting-mark" aria-hidden="true" />
          <p><strong>Reading the discharge note…</strong></p>
          <p className="muted">The Care Plan agent drafts the plan, then the Plan Verifier checks every field against the note. Nothing reaches the patient until you approve it.</p>
        </div>
      ) : (
        <form className="form-grid" onSubmit={submit} noValidate>
          <div className="field"><label htmlFor="new-name">Full name</label><input id="new-name" className="input" value={form.name} onChange={set('name')} autoComplete="off" /></div>
          <div className="field"><label htmlFor="new-phone">Mobile number</label><input id="new-phone" className="input" type="tel" value={form.phone_e164} onChange={set('phone_e164')} /></div>
          <div className="field"><label htmlFor="new-email">Email</label><input id="new-email" className="input" type="email" value={form.email} onChange={set('email')} aria-describedby="new-email-hint" autoComplete="off" required /><p id="new-email-hint" className="hint">The patient signs in with this.</p></div>
          <div className="field">
            <label htmlFor="new-language">Language</label>
            <select id="new-language" className="select" value={form.language} onChange={set('language')}>
              {LANGUAGES.map((language) => <option key={language.name} value={language.name}>{language.name}{language.beta ? ' (Beta)' : ''}</option>)}
            </select>
            {languageBeta && <span className="field-chip"><BetaChip /> Still being checked by native speakers</span>}
          </div>
          <div className="field">
            <label htmlFor="new-reading">Reading level</label>
            <select id="new-reading" className="select" value={form.literacy_level} onChange={set('literacy_level')}>
              {READING_LEVELS.map((level) => <option key={level.id} value={level.id}>{level.title}</option>)}
            </select>
          </div>
          <label className="check field-span"><input type="checkbox" checked={form.caregiver_mode} onChange={set('caregiver_mode')} />A family member will help (the patient must agree)</label>
          {PRESENTER && <div className="field field-span">
            <label htmlFor="new-sample">Presenter: paste a sample note</label>
            <select id="new-sample" className="select" defaultValue="" onChange={(event) => { const note = notes.find((item) => item.id === event.target.value); if (note) setForm((current) => ({ ...current, note: note.text })); }}>
              <option value="">Choose a note</option>
              {notes.map((note) => <option key={note.id} value={note.id}>{note.title}</option>)}
            </select>
          </div>}
          <div className="field field-span"><label htmlFor="new-note">Discharge note</label><span className="hint">Paste it exactly as written. Tomi only ever repeats what you approve.</span><textarea id="new-note" className="textarea" rows={7} value={form.note} onChange={set('note')} /></div>
          <p className="hint field-span">After you approve the plan, we email the patient an invite. With no email address, give them the invite code in person. They choose how to be contacted and agree to it themselves.</p>
          {error && <p className="error-text field-span" role="alert">{error}</p>}
          <div className="modal-actions field-span">
            <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Add patient and draft plan</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/* ---------- send a text or email (generic templates only) ---------- */

export function SendMessageDialog({ patient: fixedPatient = null, onClose }) {
  const patientsQuery = useAsync(() => (fixedPatient ? Promise.resolve({ patients: [fixedPatient] }) : CareLoopAPI.listPatients()), []);
  const reachable = (patientsQuery.data?.patients || []).filter((item) => item.channels?.some((channel) => ['sms', 'email'].includes(channel)));
  const [patientId, setPatientId] = useState(fixedPatient?.id || '');
  const patient = reachable.find((item) => item.id === patientId) || null;
  const channels = (patient?.channels || []).filter((channel) => ['sms', 'email'].includes(channel));
  const [channel, setChannel] = useState('email');
  const templatesQuery = useAsync(() => (patientId ? CareLoopAPI.listMessageTemplates({ patient_id: patientId }) : Promise.resolve({ templates: [] })), [patientId]);
  const templates = templatesQuery.data?.templates || [];
  const [templateId, setTemplateId] = useState('medicine');
  const template = templates.find((item) => item.id === templateId) || templates[0];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const { user, refreshCounts } = useDashboard();

  useEffect(() => { if (!patientId && reachable[0]) setPatientId(reachable[0].id); }, [reachable, patientId]);
  useEffect(() => { if (channels.length && !channels.includes(channel)) setChannel(channels[0]); }, [channels, channel]);

  const send = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await CareLoopAPI.sendPatientMessage({ patient_id: patientId, channel, template: template.id, by: user.name });
      toast(`${channel === 'sms' ? 'Text' : 'Email'} sent to ${patient.name}.`);
      refreshCounts();
      onClose();
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  return (
    <Modal title={fixedPatient ? `Send ${fixedPatient.name} a message` : 'Send a message'} onClose={onClose} wide>
      {patientsQuery.data && !reachable.length ? (
        <p className="empty">No patient has agreed to email reminders yet.</p>
      ) : (
        <form className="stack-4" onSubmit={send}>
          {!fixedPatient && (
            <div className="field">
              <label htmlFor="msg-patient">Patient</label>
              <select id="msg-patient" className="select" value={patientId} onChange={(event) => setPatientId(event.target.value)}>
                {reachable.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <p className="hint">Only patients who agreed to email reminders are listed.</p>
            </div>
          )}
          {patient && (
            <fieldset className="slot-picker">
              <legend className="label">Send by</legend>
              {channels.map((item) => (
                <label key={item} className="slot">
                  <input type="radio" name="msg-channel" checked={channel === item} onChange={() => setChannel(item)} />
                  <span><strong>{item === 'sms' ? 'Text message' : 'Email'}</strong><span className="muted">{item === 'sms' ? patient.phone_e164 : patient.email}</span></span>
                </label>
              ))}
            </fieldset>
          )}
          {templates.length > 0 && (
            <fieldset className="slot-picker">
              <legend className="label">Message</legend>
              {templates.map((item) => (
                <label key={item.id} className="slot">
                  <input type="radio" name="msg-template" checked={template?.id === item.id} onChange={() => setTemplateId(item.id)} />
                  <span><strong>{item.title}</strong></span>
                </label>
              ))}
            </fieldset>
          )}
          {template && (
            <div className="message-preview">
              <p className="label">{patient?.name.split(' ')[0]} will receive</p>
              <p className="message-text">{template.body}</p>
              <p className="hint">Messages are fixed so they never reveal health details. To say something specific, call the patient.</p>
            </div>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={busy || !template || !channels.length}>{busy ? 'Sending…' : `Send ${channel === 'email' ? 'email' : 'text'}`}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
