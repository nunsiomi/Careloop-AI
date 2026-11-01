import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CareLoopAPI } from '../../shared/api.js';
import { dayLabel, formatDateTime, formatTime, groupByDay, relativeTime } from '../../shared/format.js';
import { ErrorNote, LoadingBlock, StatusBadge, useAsync, useToast } from '../../shared/ui.jsx';
import { ChannelLabel } from '../components.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

async function loadAppointments() {
  const [appointments, requests, slots] = await Promise.all([
    CareLoopAPI.listAppointments(),
    CareLoopAPI.listRescheduleRequests({ status: 'pending' }),
    CareLoopAPI.listSlots()
  ]);
  return { appointments: appointments.appointments, requests: requests.requests, slots: slots.slots };
}

export default function Appointments() {
  const { dataVersion } = useDashboard();
  const query = useAsync(loadAppointments, [dataVersion]);
  const data = query.data;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const visible = (data?.appointments || []).filter((appointment) => appointment.status !== 'cancelled' && new Date(appointment.starts_at) >= new Date(startOfToday.getTime() - 86400000));

  return (
    <div className="page">
      <PageHeader title="Appointments" sub="Who is coming in, who came, and who has asked for a new time." />
      {query.loading && !data && <LoadingBlock lines={6} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {data && (
        <div className="appointments-grid">
          <section aria-labelledby="schedule-title" className="stack-4">
            <h2 id="schedule-title" className="section-title">Schedule</h2>
            {!visible.length && <p className="empty">No visits from yesterday onwards.</p>}
            {groupByDay(visible, 'starts_at').map(([label, items]) => (
              <section key={label} className="panel day-panel" aria-label={label}>
                <h3 className="day-title">{label}</h3>
                <ul className="schedule">
                  {items.map((appointment) => <ScheduleRow key={appointment.id} appointment={appointment} onChange={query.reload} />)}
                </ul>
              </section>
            ))}
          </section>

          <section aria-labelledby="requests-title" className="stack-4">
            <h2 id="requests-title" className="section-title">Requests to move a visit</h2>
            <p className="note">The patient keeps their original visit until you pick a new slot. When you do, their old reminder is cancelled and they get a text about the change.</p>
            {!data.requests.length && <p className="empty">No requests waiting.</p>}
            {data.requests.map((request) => <RequestCard key={request.id} request={request} slots={data.slots} onDone={query.reload} />)}
          </section>
        </div>
      )}
    </div>
  );
}

function ScheduleRow({ appointment, onChange }) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const started = new Date(appointment.starts_at) <= new Date();
  const canRecord = started && ['scheduled', 'confirmed', 'rescheduled'].includes(appointment.status);

  const record = async (status) => {
    setBusy(true);
    try {
      await CareLoopAPI.recordAttendance(appointment.id, { status });
      toast(status === 'attended' ? `${appointment.patient_name} marked as attended.` : `${appointment.patient_name} marked as did not attend.`);
      onChange();
    } catch (error) { toast(error.message); setBusy(false); }
  };

  return (
    <li className="schedule-row">
      <time dateTime={appointment.starts_at}>{formatTime(appointment.starts_at)}</time>
      <div className="schedule-main">
        <Link to={`/patients/${appointment.patient_id}`} className="strong-link">{appointment.patient_name}</Link>
        <p className="muted">{appointment.what}, {appointment.where}</p>
      </div>
      <StatusBadge kind="appointment" status={appointment.status} />
      {canRecord && (
        <div className="row-actions">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => record('attended')}>Attended</button>
          <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => record('no_show')}>Did not attend</button>
        </div>
      )}
    </li>
  );
}

function RequestCard({ request, slots, onDone }) {
  const free = slots.filter((slot) => slot.reserved_count < slot.capacity);
  const [slotId, setSlotId] = useState(free[0]?.id || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const { refreshCounts } = useDashboard();

  const decide = async (decision) => {
    setBusy(true);
    setError(null);
    try {
      await CareLoopAPI.decideReschedule(request.id, { decision, slot_id: decision === 'approve' ? slotId : undefined });
      toast(decision === 'approve' ? `Visit moved. ${request.patient_name} has been sent a text about the new time.` : 'Original time kept.');
      refreshCounts();
      onDone();
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  return (
    <article className="panel request-card" aria-labelledby={`req-${request.id}`}>
      <div className="split-head">
        <h3 id={`req-${request.id}`}><Link to={`/patients/${request.patient_id}`}>{request.patient_name}</Link></h3>
        <span className="muted">{relativeTime(request.requested_at)} <ChannelLabel channel={request.channel} /></span>
      </div>
      <dl className="facts">
        <div><dt>Current visit</dt><dd>{request.appointment ? `${request.appointment.what}, ${formatDateTime(request.appointment.starts_at)}` : 'Unknown'}</dd></div>
        <div><dt>Reason</dt><dd>{request.reason}</dd></div>
        {request.original_text && request.original_text !== request.reason && <div><dt>Patient's words</dt><dd lang={request.patient_language === 'Hausa' ? 'ha' : undefined}>{request.original_text}</dd></div>}
      </dl>
      <fieldset className="slot-picker">
        <legend className="label">Free clinic slots</legend>
        {!free.length && <p className="muted">No free slots this week. Call the clinic to arrange one.</p>}
        {free.map((slot) => (
          <label key={slot.id} className="slot">
            <input type="radio" name={`slot-${request.id}`} value={slot.id} checked={slotId === slot.id} onChange={() => setSlotId(slot.id)} />
            <span><strong>{dayLabel(slot.starts_at)}, {formatTime(slot.starts_at)}</strong><span className="muted">{slot.where}, {slot.capacity - slot.reserved_count} free</span></span>
          </label>
        ))}
      </fieldset>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="row-actions">
        <button type="button" className="btn btn-primary" disabled={busy || !slotId} onClick={() => decide('approve')}>Move to this slot</button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => decide('reject')}>Keep original time</button>
      </div>
    </article>
  );
}
