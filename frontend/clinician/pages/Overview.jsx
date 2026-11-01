import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, ClipboardCheck, MessageSquareWarning, PackageX, Siren, TimerOff, UserPlus } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { formatDateLong, formatTime, isSameDay, relativeTime, whenLabel } from '../../shared/format.js';
import { ErrorNote, LoadingBlock, StatusBadge, useAsync, useInterval } from '../../shared/ui.jsx';
import { AddPatientDialog, ChannelLabel, Timeline, directionIcon } from '../components.jsx';
import { PageHeader, PatientLoop, useDashboard } from '../shell.jsx';

async function loadOverview() {
  const [escalations, patients, requests, barriers, appointments, events, calls, failed, upcoming] = await Promise.all([
    CareLoopAPI.listEscalations({ status: 'open' }),
    CareLoopAPI.listPatients(),
    CareLoopAPI.listRescheduleRequests({ status: 'pending' }),
    CareLoopAPI.listBarriers({ status: 'open' }),
    CareLoopAPI.listAppointments(),
    CareLoopAPI.listEvents({ limit: 8 }),
    CareLoopAPI.listCalls(),
    CareLoopAPI.listNotifications({ status: 'problem' }),
    CareLoopAPI.listNotifications({ status: 'upcoming' })
  ]);
  return { escalations: escalations.escalations, patients: patients.patients, requests: requests.requests, barriers: barriers.barriers, appointments: appointments.appointments, events: events.events, calls: calls.calls, failed: failed.notifications.filter((item) => !item.retried), upcoming: upcoming.notifications };
}

function buildQueue(data) {
  const items = [];
  data.escalations.forEach((escalation) => {
    const unacked = !['acknowledged', 'acted_on'].includes(escalation.status);
    items.push({
      id: escalation.id, rank: unacked ? (escalation.severity === 'red' ? 0 : 1) : 4, tone: unacked ? 'red' : 'amber', icon: Siren,
      title: `${escalation.rule_label}: ${escalation.patient_name}`,
      detail: unacked ? `Not acknowledged, raised ${relativeTime(escalation.created_at)}` : `Acknowledged, still open`,
      to: '/escalations', action: unacked ? 'Acknowledge' : 'Open'
    });
  });
  data.patients.filter((patient) => patient.overdue_critical > 0).forEach((patient) => items.push({
    id: `overdue-${patient.id}`, rank: 2, tone: 'amber', icon: TimerOff, title: `Critical task overdue: ${patient.name}`, detail: `${patient.overdue_critical} high-priority task with no report`, to: `/patients/${patient.id}`, action: 'View patient'
  }));
  data.patients.filter((patient) => patient.plan_status === 'needs_review').forEach((patient) => items.push({
    id: `plan-${patient.id}`, rank: 3, tone: 'amber', icon: ClipboardCheck, title: `Plan to review: ${patient.name}`, detail: 'Nothing is sent to the patient until you approve', to: `/patients/${patient.id}/review`, action: 'Review plan'
  }));
  data.requests.forEach((request) => items.push({
    id: request.id, rank: 3, tone: 'amber', icon: CalendarClock, title: `New time requested: ${request.patient_name}`, detail: request.reason, to: '/appointments', action: 'Choose a slot'
  }));
  data.barriers.forEach((barrier) => items.push({
    id: barrier.id, rank: 5, tone: 'neutral', icon: PackageX, title: `Barrier (${barrier.type}): ${barrier.patient_name}`, detail: `Opened ${relativeTime(barrier.opened_at)}, ${barrier.attempts} option${barrier.attempts === 1 ? '' : 's'} offered`, to: `/patients/${barrier.patient_id}`, action: 'View patient'
  }));
  data.failed.forEach((message) => items.push({
    id: message.id, rank: 4, tone: 'amber', icon: MessageSquareWarning, title: `Text not delivered: ${message.patient_name}`, detail: message.failure_reason || 'The provider could not deliver it.', to: '/reminders?show=problem', action: 'Send again'
  }));
  return items.sort((first, second) => first.rank - second.rank);
}

function loopSummary(patient) {
  if (patient.open_escalations) return `${patient.open_escalations} open escalation${patient.open_escalations === 1 ? '' : 's'}`;
  if (patient.plan_status === 'needs_review') return 'Plan waiting for review';
  if (patient.plan_status === 'not_created') return 'No plan yet';
  if (!patient.consent_at) return 'Invited, not joined yet';
  const { done = 0, due = 0, missed = 0 } = patient.task_counts || {};
  return `${done} done, ${due} due, ${missed} missed`;
}

export default function Overview() {
  const { user, dataVersion } = useDashboard();
  const query = useAsync(loadOverview, [dataVersion]);
  const [adding, setAdding] = useState(false);
  useInterval(query.reload, 20000);
  const data = query.data;
  const queue = data ? buildQueue(data) : [];
  const today = data ? data.appointments.filter((appointment) => isSameDay(appointment.starts_at) && appointment.status !== 'cancelled') : [];
  const liveCalls = data ? data.calls.filter((call) => isSameDay(call.started_at)) : [];

  return (
    <div className="page">
      <PageHeader title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${user.name}`} sub={`${formatDateLong(new Date().toISOString())}. ${user.facility}.`}>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}><UserPlus aria-hidden="true" size={18} />Add patient</button>
      </PageHeader>

      {query.loading && !data && <LoadingBlock lines={6} />}
      <ErrorNote error={query.error} onRetry={query.reload} />

      {data && (
        <section className="loop-strip" aria-labelledby="loops-title">
          <div className="loop-strip-head">
            <h2 id="loops-title">Your patients</h2>
            <p className="loop-legend" aria-hidden="true"><span className="lg-done">Done</span><span className="lg-due">Due</span><span className="lg-missed">Missed</span></p>
          </div>
          <ul className="loop-strip-list">
            {data.patients.map((patient) => (
              <li key={patient.id}>
                <Link to={patient.plan_status === 'needs_review' ? `/patients/${patient.id}/review` : `/patients/${patient.id}`} className="loop-card">
                  <PatientLoop counts={patient.task_counts} escalated={patient.open_escalations > 0} size={52} />
                  <span className="loop-card-text">
                    <strong>{patient.name}</strong>
                    <span>{loopSummary(patient)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data && (
        <div className="overview-grid">
          <section className="panel queue-panel" aria-labelledby="queue-title">
            <div className="panel-head">
              <h2 id="queue-title">Needs you now</h2>
              <p className="muted">{queue.length ? `${queue.length} item${queue.length === 1 ? '' : 's'}, most urgent first` : 'All clear'}</p>
            </div>
            {!queue.length && <p className="empty">You are all caught up. New escalations, plans to check and patient requests will show up here.</p>}
            <ul className="queue">
              {queue.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.id} className={`queue-item tone-${item.tone}`}>
                    <span className="queue-icon" aria-hidden="true"><Icon size={20} /></span>
                    <div className="queue-text"><p className="queue-title">{item.title}</p><p className="muted">{item.detail}</p></div>
                    <Link className="btn btn-secondary" to={item.to}>{item.action}</Link>
                  </li>
                );
              })}
            </ul>
          </section>

          <div className="overview-side">
            <section className="panel" aria-labelledby="today-title">
              <div className="panel-head"><h2 id="today-title">Today's clinic</h2><Link to="/appointments" className="panel-link">All appointments</Link></div>
              {!today.length && <p className="muted">No visits booked today.</p>}
              <ol className="rail">
                {today.map((appointment) => (
                  <li key={appointment.id}>
                    <time dateTime={appointment.starts_at}>{formatTime(appointment.starts_at)}</time>
                    <div><Link to={`/patients/${appointment.patient_id}`}>{appointment.patient_name}</Link><p className="muted">{appointment.what}</p></div>
                    <StatusBadge kind="appointment" status={appointment.status} />
                  </li>
                ))}
              </ol>
            </section>

            <section className="panel" aria-labelledby="texts-title">
              <div className="panel-head"><h2 id="texts-title">Next texts and emails</h2><Link to="/reminders" className="panel-link">All reminders</Link></div>
              {!data.upcoming.length && <p className="muted">Nothing scheduled.</p>}
              <ul className="mini-list">
                {data.upcoming.slice(0, 4).map((message) => (
                  <li key={message.id}>
                    <ChannelLabel channel={message.channel} iconOnly />
                    <span><Link to={`/patients/${message.patient_id}?tab=calls`}>{message.patient_name}</Link> <span className="muted">{message.title.toLowerCase()}, {whenLabel(message.scheduled_for)}</span></span>
                    <StatusBadge kind="message" status={message.status} />
                  </li>
                ))}
              </ul>
            </section>

            <section className="panel" aria-labelledby="calls-title">
              <div className="panel-head"><h2 id="calls-title">Tomi calls today</h2><Link to="/calls" className="panel-link">All calls</Link></div>
              {!liveCalls.length && <p className="muted">No calls yet today.</p>}
              <ul className="mini-list">
                {liveCalls.map((call) => {
                  const Icon = directionIcon(call.direction);
                  return (
                    <li key={call.id}>
                      <Icon aria-hidden="true" size={16} />
                      <span><Link to={`/calls?call=${call.id}`}>{call.patient_name}</Link> <span className="muted">{formatTime(call.started_at)}</span></span>
                      <StatusBadge kind="call" status={call.status} />
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>

          <section className="panel activity-panel" aria-labelledby="activity-title">
            <div className="panel-head"><h2 id="activity-title">Latest activity</h2><p className="muted">What patients tell Tomi is marked "Patient said" until someone on the team confirms it.</p></div>
            <Timeline events={data.events} showPatient compact filterable={false} />
          </section>
        </div>
      )}
      {adding && <AddPatientDialog onClose={() => setAdding(false)} />}
    </div>
  );
}
