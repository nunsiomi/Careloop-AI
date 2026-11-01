import { useState } from 'react';
import { CalendarClock, Check, MapPin, MessageCircle, MessageSquareText, Phone, Pill, TestTube, TriangleAlert } from 'lucide-react';
import DayLoop from './DayLoop.jsx';
import { CareLoopAPI } from '../shared/api.js';
import { languageInfo } from '../shared/languages.js';
import { dayLabel, firstName, formatDateLong, formatTime, isSameDay, whenLabel } from '../shared/format.js';
import { ErrorNote, LoadingBlock, Modal, StatusBadge, useAsync, useToast } from '../shared/ui.jsx';

const PROBLEMS = [
  { id: 'cost', label: 'It costs too much' },
  { id: 'transport', label: 'Getting there is hard' },
  { id: 'stock', label: 'The medicine is not in stock' },
  { id: 'understanding', label: 'I do not understand' }
];

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
}

/* ---------- Today ---------- */

const PARTS_OF_DAY = [['Morning', 0, 12], ['Afternoon', 12, 17], ['Evening', 17, 21], ['Night', 21, 24]];

export function TodayScreen({ session, patient, support, refreshKey, refresh, headingRef, onTalk }) {
  const planQuery = useAsync(() => CareLoopAPI.getPlan(patient.id), [patient.id, refreshKey]);
  const visitsQuery = useAsync(() => CareLoopAPI.listAppointments({ patient_id: patient.id }), [patient.id, refreshKey]);
  const language = languageInfo(patient.language);
  const helper = session.kind === 'caregiver';

  const allTasks = planQuery.data?.tasks || [];
  const today = allTasks.filter((task) => isSameDay(task.due_at)).sort((a, b) => a.due_at.localeCompare(b.due_at));
  const carried = allTasks.filter((task) => !isSameDay(task.due_at) && task.due_at < new Date().toISOString() && ['overdue', 'unable'].includes(task.status));
  const groups = [
    ['From before', carried],
    ...PARTS_OF_DAY.map(([label, from, to]) => [label, today.filter((task) => { const hour = new Date(task.due_at).getHours(); return hour >= from && hour < to; })])
  ].filter(([, items]) => items.length);
  const nextVisit = (visitsQuery.data?.appointments || []).find((visit) => visit.starts_at > new Date().toISOString() && visit.status !== 'cancelled');
  const waiting = planQuery.data?.plan.status === 'needs_review';

  return (
    <div className="screen today">
      <section className="today-hero" aria-labelledby="today-title">
        <h1 id="today-title" ref={headingRef} tabIndex={-1} className="today-title">{greeting()}, {firstName(session.user_name)}</h1>
        <p className="today-date">{formatDateLong(new Date().toISOString())}{helper ? `. Helping ${firstName(patient.name)}.` : ''}</p>
        <DayLoop tasks={today} onTalk={onTalk} describedBy="tomi-hero-copy" />
        <p id="tomi-hero-copy" className="today-hint">Tomi speaks {language.native}{language.beta ? ' (beta)' : ''}. Tell Tomi how {helper ? `${firstName(patient.name)} is` : 'you are'} doing; it is noted for the care team.</p>
        <div className="today-alt">
          <a className="btn hero-btn" href={`tel:${support.tomi_number}`}><Phone aria-hidden="true" size={18} />Call Tomi</a>
          <a className="btn hero-btn" href="#/chat"><MessageCircle aria-hidden="true" size={18} />Type instead</a>
        </div>
      </section>

      <section className="day-sheet" aria-labelledby="tasks-title">
        <h2 id="tasks-title" className="sheet-title">Today's list</h2>
        {patient.next_message && (
          <p className="sheet-note"><MessageSquareText aria-hidden="true" size={16} />Next {patient.next_message.channel === 'sms' ? 'text' : 'email'} reminder {whenLabel(patient.next_message.scheduled_for)}</p>
        )}
        {planQuery.loading && !planQuery.data && <LoadingBlock />}
        <ErrorNote error={planQuery.error} onRetry={planQuery.reload} />
        {waiting && <p className="soft-note">The care team is still checking the plan. Tasks will appear here when it is ready.</p>}
        {!waiting && planQuery.data && !groups.length && <p className="soft-note">Nothing is due today.</p>}
        {groups.map(([label, items]) => (
          <div key={label} className={`day-part${label === 'From before' ? ' is-carried' : ''}`}>
            <h3 className="day-part-title">{label}</h3>
            <ul className="task-list">
              {items.map((task) => <TaskRow key={task.id} task={task} patient={patient} onReported={refresh} />)}
            </ul>
          </div>
        ))}
      </section>

      {nextVisit && (
        <section className="block" aria-labelledby="next-visit-title">
          <h2 id="next-visit-title" className="sheet-title">Next visit</h2>
          <a className="visit-tile" href="#/visits">
            <span className="visit-date"><span>{dayLabel(nextVisit.starts_at)}</span><strong>{formatTime(nextVisit.starts_at)}</strong></span>
            <span className="visit-body">
              <strong>{nextVisit.what}</strong>
              <span>{nextVisit.where}</span>
              <StatusBadge kind="appointment" status={nextVisit.status} />
            </span>
          </a>
        </section>
      )}
    </div>
  );
}

function TaskRow({ task, patient, onReported }) {
  const [mode, setMode] = useState('idle');
  const [reply, setReply] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const actionable = ['pending', 'overdue'].includes(task.status) && !reply;
  const Icon = task.type === 'medication' ? Pill : task.type === 'test' ? TestTube : CalendarClock;

  const send = async (quick, text) => {
    setBusy(true);
    try {
      const response = await CareLoopAPI.sendMessage(patient.id, { original_text: text, task_id: task.id, quick_reply: quick, language: patient.language });
      setReply(response.reply.original_text);
      setMode('idle');
      if (response.barrier || quick === 'done') window.setTimeout(onReported, 2400);
    } catch (error) { toast(error.message); }
    setBusy(false);
  };

  return (
    <li className={`task-row task-${task.status}`}>
      <p className="task-time">
        <span className="task-clock">{formatTime(task.due_at)}</span>
        {!isSameDay(task.due_at) && <span className="task-day">{dayLabel(task.due_at)}</span>}
      </p>
      <div className="task-main">
        <h4 className="task-title"><Icon aria-hidden="true" size={18} />{task.title}</h4>
        <p className="task-detail">{task.detail}</p>
        {!actionable && !reply && <StatusBadge kind="task" status={task.status} />}
        {reply && <p className="task-reply" role="status"><span className="tomi-dot" aria-hidden="true" />{reply}</p>}
        {actionable && mode === 'idle' && (
          <div className="task-actions">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => send('done', 'Done')}><Check aria-hidden="true" size={18} />Done</button>
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => send('not_yet', 'Not yet')}>Not yet</button>
            <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => setMode('problem')}>I have a problem</button>
          </div>
        )}
        {actionable && mode === 'problem' && (
          <fieldset className="problem-picker">
            <legend className="label">What is the problem?</legend>
            {PROBLEMS.map((problem) => (
              <button key={problem.id} type="button" className="btn btn-secondary btn-block problem-option" disabled={busy} onClick={() => send(problem.id, problem.label)}>{problem.label}</button>
            ))}
            <button type="button" className="btn btn-quiet" onClick={() => setMode('idle')}>Back</button>
          </fieldset>
        )}
      </div>
    </li>
  );
}

/* ---------- Plan ---------- */

export function PlanScreen({ patient, refreshKey, headingRef }) {
  const query = useAsync(() => CareLoopAPI.getPlan(patient.id), [patient.id, refreshKey]);
  const plan = query.data?.plan;

  return (
    <div className="screen">
      <h1 ref={headingRef} tabIndex={-1} className="screen-title">My plan</h1>
      {query.loading && !plan && <LoadingBlock lines={5} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {plan && plan.status !== 'approved' && <p className="soft-note">Your care team is still checking your plan. You will see it here as soon as it is ready.</p>}
      {plan && plan.status === 'approved' && (
        <>
          <p className="screen-sub">Checked and approved by {plan.approved_by || 'your care team'}. Tomi only ever repeats what is written here.</p>

          {plan.medications?.length > 0 && (
            <section className="block" aria-labelledby="plan-meds">
              <h2 id="plan-meds" className="block-title">Medicines</h2>
              <ul className="plan-list">
                {plan.medications.map((medicine) => (
                  <li key={medicine.name} className="plan-entry">
                    <h3>{medicine.name}</h3>
                    <dl className="plan-facts">
                      {medicine.dose && <div><dt>How much</dt><dd>{medicine.dose}</dd></div>}
                      {medicine.frequency && <div><dt>When</dt><dd>{medicine.frequency}</dd></div>}
                      {medicine.duration && <div><dt>For how long</dt><dd>{medicine.duration}</dd></div>}
                      {medicine.instructions && <div><dt>How</dt><dd>{medicine.instructions}</dd></div>}
                    </dl>
                    {medicine.times?.length > 0 && <p className="time-chips">{medicine.times.map((time) => <span key={time} className="time-chip">{time}</span>)}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {(plan.appointments?.length > 0 || plan.tests?.length > 0) && (
            <section className="block" aria-labelledby="plan-visits">
              <h2 id="plan-visits" className="block-title">Visits and tests</h2>
              <ul className="plan-list">
                {plan.appointments.map((visit) => (
                  <li key={visit.what} className="plan-entry">
                    <h3>{visit.what}</h3>
                    <p className="plan-line"><MapPin aria-hidden="true" size={16} />{visit.where}</p>
                    {visit.date && <p className="plan-line"><CalendarClock aria-hidden="true" size={16} />{formatDateLong(`${visit.date}T12:00:00`)}{visit.time ? `, ${visit.time}` : ''}</p>}
                  </li>
                ))}
                {plan.tests.map((test) => (
                  <li key={test.name} className="plan-entry">
                    <h3>{test.name}</h3>
                    <p className="plan-line"><MapPin aria-hidden="true" size={16} />{test.where}</p>
                    {test.date && <p className="plan-line"><CalendarClock aria-hidden="true" size={16} />By {formatDateLong(`${test.date}T12:00:00`)}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {plan.symptoms_to_watch?.length > 0 && (
            <section className="block warning-block" aria-labelledby="plan-warning">
              <h2 id="plan-warning" className="block-title"><TriangleAlert aria-hidden="true" size={20} />Warning signs</h2>
              <ul className="warning-list">
                {plan.symptoms_to_watch.map((sign) => <li key={sign}>{sign}</li>)}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

/* ---------- Visits ---------- */

const MOVE_REASONS = ['Travel cost', 'Transport is hard', 'I am not well enough to travel', 'It clashes with something else'];

export function VisitsScreen({ patient, refreshKey, refresh, headingRef }) {
  const query = useAsync(() => CareLoopAPI.listAppointments({ patient_id: patient.id }), [patient.id, refreshKey]);
  const [moving, setMoving] = useState(null);
  const visits = (query.data?.appointments || []).filter((visit) => visit.status !== 'cancelled');
  const upcoming = visits.filter((visit) => visit.starts_at >= new Date().toISOString());
  const past = visits.filter((visit) => visit.starts_at < new Date().toISOString());

  return (
    <div className="screen">
      <h1 ref={headingRef} tabIndex={-1} className="screen-title">Visits</h1>
      {query.loading && !query.data && <LoadingBlock />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !upcoming.length && <p className="soft-note">No visits booked right now.</p>}
      <ul className="visit-list">
        {upcoming.map((visit) => (
          <li key={visit.id} className="visit-card">
            <div className="visit-date"><span>{dayLabel(visit.starts_at)}</span><strong>{formatTime(visit.starts_at)}</strong></div>
            <div className="visit-body">
              <h2 className="visit-title">{visit.what}</h2>
              <p className="plan-line"><MapPin aria-hidden="true" size={16} />{visit.where}</p>
              <StatusBadge kind="appointment" status={visit.status} />
              {visit.status === 'reschedule_requested'
                ? <p className="hint">You asked for a new time. Keep this one until the clinic confirms the new time; we will text you when it does.</p>
                : <button type="button" className="btn btn-secondary" onClick={() => setMoving(visit)}>Ask for a new time</button>}
            </div>
          </li>
        ))}
      </ul>
      {past.length > 0 && (
        <section className="block" aria-labelledby="past-visits">
          <h2 id="past-visits" className="block-title">Earlier</h2>
          <ul className="visit-list is-past">
            {past.map((visit) => (
              <li key={visit.id} className="visit-card">
                <div className="visit-date"><span>{dayLabel(visit.starts_at)}</span><strong>{formatTime(visit.starts_at)}</strong></div>
                <div className="visit-body"><h3 className="visit-title">{visit.what}</h3><StatusBadge kind="appointment" status={visit.status} /></div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {moving && <MoveVisitDialog visit={moving} onClose={() => setMoving(null)} onDone={() => { setMoving(null); refresh(); }} />}
    </div>
  );
}

function MoveVisitDialog({ visit, onClose, onDone }) {
  const [reason, setReason] = useState(MOVE_REASONS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await CareLoopAPI.createRescheduleRequest(visit.id, { reason });
      toast('Sent. The clinic will let you know the new time.');
      onDone();
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  return (
    <Modal title="Ask for a new time" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="hint">{visit.what}, {dayLabel(visit.starts_at)} at {formatTime(visit.starts_at)}. The clinic will find a free time and let you know. Your current visit stays booked until then.</p>
        <fieldset className="choice-group">
          <legend className="label">Why do you need a new time?</legend>
          <div className="choice-list">
            {MOVE_REASONS.map((option) => (
              <label key={option} className="choice-card choice-row compact">
                <input type="radio" name="reason" checked={reason === option} onChange={() => setReason(option)} />
                <span className="choice-title">{option}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Sending…' : 'Send request'}</button>
        </div>
      </form>
    </Modal>
  );
}
