import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { MessageSquareText, RotateCcw, X } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { formatTime, dayLabel } from '../../shared/format.js';
import { ErrorNote, LoadingBlock, StatusBadge, useAsync, useInterval, useToast } from '../../shared/ui.jsx';
import { ChannelLabel, SendMessageDialog } from '../components.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

const FILTERS = [
  { id: 'upcoming', label: 'Scheduled', empty: 'Nothing is scheduled. Reminders are added when a patient signs up and their plan is approved.' },
  { id: 'sent', label: 'Sent', empty: 'Nothing has been sent yet.' },
  { id: 'problem', label: 'Not delivered', empty: 'Every message was delivered.' },
  { id: 'cancelled', label: 'Cancelled', empty: 'No cancelled messages.' }
];

export default function Reminders() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.some((item) => item.id === params.get('show')) ? params.get('show') : 'upcoming';
  const query = useAsync(() => CareLoopAPI.listNotifications({ status: filter }), [filter]);
  const [sending, setSending] = useState(false);
  const active = FILTERS.find((item) => item.id === filter);
  useInterval(query.reload, 5000);

  return (
    <div className="page">
      <PageHeader title="Reminders" sub="Text messages and emails to patients. They are short and generic: they never name a medicine or an illness, and replies are not read.">
        <button type="button" className="btn btn-primary" onClick={() => setSending(true)}><MessageSquareText aria-hidden="true" size={18} />Send a message</button>
      </PageHeader>

      <div className="filter-row" role="group" aria-label="Show">
        {FILTERS.map((item) => <button key={item.id} type="button" className="filter-chip" aria-pressed={filter === item.id} onClick={() => setParams(item.id === 'upcoming' ? {} : { show: item.id })}>{item.label}</button>)}
      </div>

      {query.loading && !query.data && <LoadingBlock lines={6} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !query.data.notifications.length && <p className="empty">{active.empty}</p>}
      {query.data?.notifications.length > 0 && (
        <div className="table-wrap" role="region" aria-label={active.label} tabIndex={0}>
          <table className="table message-table">
            <thead><tr><th scope="col">When</th><th scope="col">Patient</th><th scope="col">Message</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {query.data.notifications.map((item) => <MessageRow key={item.id} item={item} onChange={query.reload} />)}
            </tbody>
          </table>
        </div>
      )}
      {sending && <SendMessageDialog onClose={() => { setSending(false); query.reload(); }} />}
    </div>
  );
}

function MessageRow({ item, onChange }) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { user, refreshCounts } = useDashboard();

  const act = async (action) => {
    setBusy(true);
    try {
      if (action === 'cancel') { await CareLoopAPI.cancelNotification(item.id, { by: user.name }); toast('Message cancelled.'); }
      else { await CareLoopAPI.retryNotification(item.id, { by: user.name }); toast(`Sending again to ${item.patient_name}.`); }
      refreshCounts();
      onChange();
    } catch (error) { toast(error.message); setBusy(false); }
  };

  return (
    <tr>
      <td className="nowrap">{dayLabel(item.scheduled_for)}<br /><span className="muted">{formatTime(item.scheduled_for)}</span></td>
      <td><Link className="table-link" to={`/patients/${item.patient_id}?tab=calls`}>{item.patient_name}</Link><br /><span className="muted">{item.to}</span></td>
      <td>
        <p className="message-head"><ChannelLabel channel={item.channel} /><strong>{item.title}</strong><span className="muted">from {item.created_by}</span></p>
        <p className="message-text">{item.body}</p>
        {item.failure_reason && <p className={item.status === 'failed' ? 'field-issue' : 'muted'}>{item.failure_reason}</p>}
      </td>
      <td><StatusBadge kind="message" status={item.status} />{item.delivered_at && <span className="muted nowrap"> {formatTime(item.delivered_at)}</span>}</td>
      <td>
        {item.status === 'scheduled' && <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => act('cancel')}><X aria-hidden="true" size={16} />Cancel<span className="sr-only"> message to {item.patient_name}</span></button>}
        {item.status === 'failed' && !item.retried && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => act('retry')}><RotateCcw aria-hidden="true" size={16} />Send again<span className="sr-only"> to {item.patient_name}</span></button>}
      </td>
    </tr>
  );
}
