import { useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ClipboardCheck, MessageSquareText, Mic, PhoneOutgoing } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { READING_LEVELS } from '../../shared/languages.js';
import { duration, formatDateTime, formatTime, dayLabel, whenLabel } from '../../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, StatusBadge, useAsync, useInterval, useToast } from '../../shared/ui.jsx';
import { CallPatientDialog, ChannelLabel, ConsentedChannels, SendMessageDialog, Timeline, Transcript, directionIcon } from '../components.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

const TABS = [
  { id: 'timeline', label: 'Timeline' },
  { id: 'plan', label: 'Plan and tasks' },
  { id: 'visits', label: 'Visits' },
  { id: 'calls', label: 'Calls, texts and emails' }
];

async function loadProfile(patientId) {
  const [patient, plan, events, appointments, calls, notifications] = await Promise.all([
    CareLoopAPI.getPatient(patientId),
    CareLoopAPI.getPlan(patientId).catch(() => ({ plan: null, tasks: [] })),
    CareLoopAPI.listEvents({ patient_id: patientId }),
    CareLoopAPI.listAppointments({ patient_id: patientId }),
    CareLoopAPI.listCalls({ patient_id: patientId }),
    CareLoopAPI.listNotifications({ patient_id: patientId })
  ]);
  return { patient: patient.patient, plan: plan.plan, tasks: plan.tasks, events: events.events, appointments: appointments.appointments, calls: calls.calls, notifications: notifications.notifications };
}

export default function PatientProfile() {
  const { patientId } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((item) => item.id === params.get('tab')) ? params.get('tab') : 'timeline';
  const { dataVersion, openAssistant } = useDashboard();
  const query = useAsync(() => loadProfile(patientId), [patientId, dataVersion]);
  const [calling, setCalling] = useState(false);
  const [texting, setTexting] = useState(false);
  const tabRefs = useRef({});
  useInterval(query.reload, 15000);
  const data = query.data;

  const selectTab = (id, focus = false) => {
    setParams(id === 'timeline' ? {} : { tab: id }, { replace: true });
    if (focus) tabRefs.current[id]?.focus();
  };
  const onTabKey = (event) => {
    const index = TABS.findIndex((item) => item.id === tab);
    if (event.key === 'ArrowRight') selectTab(TABS[(index + 1) % TABS.length].id, true);
    if (event.key === 'ArrowLeft') selectTab(TABS[(index - 1 + TABS.length) % TABS.length].id, true);
  };

  const back = <Link className="back-link" to="/patients"><ArrowLeft aria-hidden="true" size={16} />Patients</Link>;

  if (!data) {
    return (
      <div className="page">
        <PageHeader title="Patient" back={back} />
        {query.loading && <LoadingBlock lines={6} />}
        <ErrorNote error={query.error} onRetry={query.reload} />
      </div>
    );
  }

  const { patient, plan } = data;
  const reading = READING_LEVELS.find((level) => level.id === patient.literacy_level)?.title || patient.literacy_level;

  return (
    <div className="page">
      <PageHeader title={patient.name} back={back} sub={patient.age ? `${patient.age} years` : null}>
        <button type="button" className="btn btn-secondary" onClick={openAssistant}><Mic aria-hidden="true" size={18} />Ask Tomi</button>
        {plan?.status === 'needs_review' && <Link className="btn btn-secondary" to={`/patients/${patient.id}/review`}><ClipboardCheck aria-hidden="true" size={18} />Review plan</Link>}
        {patient.channels?.some((channel) => ['sms', 'email'].includes(channel)) && <button type="button" className="btn btn-secondary" onClick={() => setTexting(true)}><MessageSquareText aria-hidden="true" size={18} />Send a message</button>}
        <button type="button" className="btn btn-call" onClick={() => setCalling(true)} disabled={!patient.channels?.includes('voice')} aria-describedby={!patient.channels?.includes('voice') ? 'no-voice' : undefined}>
          <PhoneOutgoing aria-hidden="true" size={18} />Call now
        </button>
      </PageHeader>
      {!patient.channels?.includes('voice') && <p id="no-voice" className="muted page-note">Tomi cannot call {patient.name.split(' ')[0]} because they have not agreed to phone calls.</p>}

      <dl className="profile-facts">
        <div><dt>Language</dt><dd><LanguageTag language={patient.language} /></dd></div>
        <div><dt>Reading</dt><dd>{reading}</dd></div>
        <div><dt>Agreed to</dt><dd><ConsentedChannels channels={patient.channels} /></dd></div>
        <div><dt>Next reminder</dt><dd>{patient.next_message ? `${patient.next_message.channel === 'sms' ? 'Text' : 'Email'} ${whenLabel(patient.next_message.scheduled_for)}` : 'None scheduled'}</dd></div>
        <div><dt>Best time</dt><dd>{patient.contact_window || 'Not set'}</dd></div>
        <div><dt>Phone</dt><dd>{patient.phone_e164}{patient.pin_set ? ' (PIN set)' : ''}</dd></div>
        <div><dt>Family helper</dt><dd>{patient.caregiver ? `${patient.caregiver.name}, ${patient.caregiver.relation.toLowerCase()}. ${patient.caregiver.scope}.` : 'None'}</dd></div>
        <div><dt>Plan</dt><dd><StatusBadge kind="plan" status={patient.plan_status} /></dd></div>
        <div><dt>Lead clinician</dt><dd><LeadPicker patient={patient} onChange={query.reload} /></dd></div>
      </dl>

      <div className="tabs" role="tablist" aria-label="Patient record">
        {TABS.map((item) => (
          <button key={item.id} ref={(node) => { tabRefs.current[item.id] = node; }} type="button" role="tab" id={`tab-${item.id}`} aria-selected={tab === item.id} aria-controls={`panel-${item.id}`} tabIndex={tab === item.id ? 0 : -1} className="tab" onClick={() => selectTab(item.id)} onKeyDown={onTabKey}>
            {item.label}
          </button>
        ))}
      </div>

      <section className="tab-panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === 'timeline' && <Timeline events={data.events} />}
        {tab === 'plan' && <PlanTab plan={plan} tasks={data.tasks} patientId={patient.id} />}
        {tab === 'visits' && <VisitsTab appointments={data.appointments} />}
        {tab === 'calls' && <CallsTab calls={data.calls} notifications={data.notifications} />}
      </section>

      {calling && <CallPatientDialog patient={patient} onClose={() => { setCalling(false); query.reload(); }} />}
      {texting && <SendMessageDialog patient={patient} onClose={() => { setTexting(false); query.reload(); }} />}
    </div>
  );
}

function PlanTab({ plan, tasks, patientId }) {
  if (!plan) return <p className="empty">No plan yet. Add the discharge note to draft one.</p>;
  return (
    <div className="stack-6">
      <div className="split-head">
        <p><StatusBadge kind="plan" status={plan.status} /> {plan.clinician_approved_at && <span className="muted">Approved by {plan.approved_by}, {formatDateTime(plan.clinician_approved_at)}</span>}</p>
        <Link className="btn btn-secondary" to={`/patients/${patientId}/review`}>{plan.status === 'needs_review' ? 'Review plan' : 'Open plan and source note'}</Link>
      </div>
      <h2 className="section-title">Tasks</h2>
      {!tasks.length && <p className="muted">No tasks yet. Tasks are created when the plan is approved.</p>}
      {tasks.length > 0 && (
        <div className="table-wrap" role="region" aria-label="Tasks" tabIndex={0}>
          <table className="table">
            <thead><tr><th scope="col">Due</th><th scope="col">Task</th><th scope="col">Priority</th><th scope="col">Status</th><th scope="col">Last report</th></tr></thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>{dayLabel(task.due_at)}, {formatTime(task.due_at)}</td>
                  <td><strong>{task.title}</strong><span className="muted"> {task.detail}</span></td>
                  <td>{task.criticality === 'high' ? 'High' : 'Normal'}</td>
                  <td><StatusBadge kind="task" status={task.status} /></td>
                  <td>{task.last_reported_at ? formatDateTime(task.last_reported_at) : <span className="muted">None</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="note">"Patient said done" is what the patient told us. It is not proof the task happened.</p>
    </div>
  );
}

function VisitsTab({ appointments }) {
  if (!appointments.length) return <p className="empty">No visits booked.</p>;
  return (
    <ul className="row-list">
      {appointments.map((appointment) => (
        <li key={appointment.id} className={appointment.status === 'cancelled' ? 'is-muted' : ''}>
          <span className="row-when">{dayLabel(appointment.starts_at)}, {formatTime(appointment.starts_at)}</span>
          <span><strong>{appointment.what}</strong><span className="muted"> {appointment.where}</span></span>
          <StatusBadge kind="appointment" status={appointment.status} />
        </li>
      ))}
    </ul>
  );
}

function CallsTab({ calls, notifications }) {
  const [open, setOpen] = useState(calls[0]?.id || null);
  return (
    <div className="stack-6">
      <h2 className="section-title">Calls</h2>
      {!calls.length && <p className="muted">No calls yet.</p>}
      <ul className="call-list">
        {calls.map((call) => {
          const Icon = directionIcon(call.direction);
          const expanded = open === call.id;
          return (
            <li key={call.id} className="call-item">
              <button type="button" className="call-row" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : call.id)}>
                <Icon aria-hidden="true" size={18} />
                <span className="call-when">{formatDateTime(call.started_at)}</span>
                <span className="call-kind">{call.direction === 'browser' ? 'Talked in the app' : call.direction === 'inbound' ? 'Called Tomi' : 'Tomi called'}</span>
                <StatusBadge kind="call" status={call.status} />
                <span className="muted">{call.verification_state === 'verified' ? 'PIN verified' : call.verification_state === 'not_reached' ? 'Not reached' : 'Not verified'}</span>
                <span className="muted">{duration(call.started_at, call.ended_at) || 'Live'}</span>
              </button>
              {expanded && <div className="call-detail">{call.outcome && <p><strong>Outcome:</strong> {call.outcome}</p>}<Transcript call={call} /></div>}
            </li>
          );
        })}
      </ul>
      <h2 className="section-title">Texts and emails</h2>
      {!notifications.length && <p className="muted">Nothing sent or scheduled.</p>}
      <ul className="row-list">
        {notifications.map((notification) => (
          <li key={notification.id} className={notification.status === 'cancelled' ? 'is-muted' : ''}>
            <span className="row-when">{formatDateTime(notification.scheduled_for)}</span>
            <span>
              <span className="message-head"><ChannelLabel channel={notification.channel} /><strong>{notification.title}</strong></span>
              <span className="message-text">{notification.body}</span>
              {notification.failure_reason && <span className={notification.status === 'failed' ? 'field-issue' : 'muted'}>{notification.failure_reason}</span>}
            </span>
            <StatusBadge kind="message" status={notification.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/* Who leads this patient's follow-up. Anyone on the care team can change it; the change is logged on the timeline. */
function LeadPicker({ patient, onChange }) {
  const [editing, setEditing] = useState(false);
  const [staff, setStaff] = useState(null);
  const [choice, setChoice] = useState(patient.assigned_to?.id || '');
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const open = async () => {
    setEditing(true);
    setChoice(patient.assigned_to?.id || '');
    try { setStaff((await CareLoopAPI.listStaff()).staff); } catch (error) { toast(error.message); setEditing(false); }
  };
  const save = async () => {
    setBusy(true);
    try {
      await CareLoopAPI.assignPatient(patient.id, { staff_id: choice || null });
      toast(choice ? 'Lead clinician changed.' : 'Lead clinician removed.');
      setEditing(false);
      onChange();
    } catch (error) { toast(error.message); }
    setBusy(false);
  };

  if (!editing) {
    return (
      <span className="inline-meta">
        {patient.assigned_to ? patient.assigned_to.name : <span className="muted">Not assigned</span>}
        <button type="button" className="link-button" onClick={open}>Change<span className="sr-only"> lead clinician</span></button>
      </span>
    );
  }
  return (
    <span className="lead-picker">
      <label htmlFor="lead-select" className="sr-only">Lead clinician</label>
      <select id="lead-select" className="select" value={choice} onChange={(event) => setChoice(event.target.value)} disabled={!staff || busy}>
        <option value="">Not assigned</option>
        {(staff || []).map((member) => <option key={member.id} value={member.id}>{member.name} ({member.role})</option>)}
      </select>
      <button type="button" className="btn btn-primary" onClick={save} disabled={!staff || busy}>Save</button>
      <button type="button" className="btn btn-quiet" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
    </span>
  );
}
