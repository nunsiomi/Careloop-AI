import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CareLoopAPI } from '../../shared/api.js';
import { formatTime, relativeTime, dayLabel } from '../../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, StatusBadge, useAsync, useInterval, useToast } from '../../shared/ui.jsx';
import { ChannelLabel } from '../components.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

const FILTERS = [{ id: 'open', label: 'Open' }, { id: 'resolved', label: 'Resolved' }, { id: 'all', label: 'All' }];
const needsAck = (escalation) => Number(!['acknowledged', 'acted_on', 'resolved'].includes(escalation.status));
const DELIVERY_STEPS = [['created', 'Created'], ['notification_attempted', 'Notification sent'], ['delivered', 'Delivered'], ['acknowledged', 'Acknowledged'], ['resolved', 'Resolved']];

export default function Escalations() {
  const [filter, setFilter] = useState('open');
  const query = useAsync(() => CareLoopAPI.listEscalations(filter === 'all' ? {} : { status: filter }), [filter]);
  const waitingForBrief = (query.data?.escalations || []).some((escalation) => !escalation.brief_ready);
  useInterval(query.reload, waitingForBrief ? 3000 : 15000);

  return (
    <div className="page">
      <PageHeader title="Escalations" sub="Raised automatically by safety rules when a patient may need help. Acknowledge each one so the team knows someone is on it." />
      <div className="filter-row" role="group" aria-label="Filter escalations">
        {FILTERS.map((item) => <button key={item.id} type="button" className="filter-chip" aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}
      </div>
      {query.loading && !query.data && <LoadingBlock lines={6} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !query.data.escalations.length && <p className="empty">{filter === 'open' ? 'No open escalations.' : 'Nothing to show.'}</p>}
      <div className="escalation-list">
        {[...(query.data?.escalations || [])].sort((first, second) => needsAck(second) - needsAck(first) || second.created_at.localeCompare(first.created_at)).map((escalation) => <EscalationCard key={escalation.id} escalation={escalation} onChange={query.reload} />)}
      </div>
    </div>
  );
}

function EscalationCard({ escalation, onChange }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { refreshCounts, user } = useDashboard();
  const reached = new Set(escalation.history.map((entry) => entry.status));
  const acknowledged = reached.has('acknowledged');
  const resolved = escalation.status === 'resolved';
  const at = (status) => escalation.history.find((entry) => entry.status === status);

  const act = async (action) => {
    setBusy(true);
    try {
      if (action === 'acknowledge') await CareLoopAPI.acknowledgeEscalation(escalation.id, { by: user.name });
      else await CareLoopAPI.resolveEscalation(escalation.id, { note: note.trim(), by: user.name });
      toast(action === 'acknowledge' ? 'Acknowledged. You are now following this up.' : 'Escalation resolved.');
      refreshCounts();
      onChange();
    } catch (error) { toast(error.message); }
    setBusy(false);
  };

  return (
    <article className={`escalation severity-${escalation.severity}${resolved ? ' is-resolved' : ''}`} aria-labelledby={`esc-${escalation.id}`}>
      <header className="escalation-head">
        <div>
          <h2 id={`esc-${escalation.id}`}><Link to={`/patients/${escalation.patient_id}`}>{escalation.patient_name}</Link></h2>
          <p className="inline-meta"><LanguageTag language={escalation.patient_language} /> <ChannelLabel channel={escalation.channel} /> <span className="muted">{relativeTime(escalation.created_at)}</span></p>
        </div>
        <StatusBadge kind="escalation" status={escalation.status} />
      </header>

      <p className="escalation-rule"><strong>{escalation.rule_label}</strong> <code>{escalation.rule_id}</code> <span className="muted">{escalation.severity === 'red' ? 'Red flag' : 'Amber'}, set by the hospital's safety rules</span></p>

      <div className="escalation-words">
        <div><h3>Patient's words</h3><p className="quote">{escalation.original_text}</p>{escalation.confidence != null && <p className={`muted ${escalation.confidence < 0.75 ? 'confidence-low' : ''}`}>Speech confidence {Math.round(escalation.confidence * 100)}%</p>}</div>
        <div><h3>Meaning in English</h3><p className="quote">{escalation.english_text}</p></div>
      </div>

      <div className="escalation-brief">
        <h3>Summary</h3>
        {escalation.brief_ready ? <p>{escalation.brief}</p> : <p className="muted" role="status">Writing a short summary from the record…</p>}
        <p className="muted"><strong>Still open:</strong> {escalation.outstanding}</p>
        {escalation.call_id && <Link to={`/calls?call=${escalation.call_id}`}>Read the call transcript</Link>}
      </div>

      <ol className="delivery" aria-label="Delivery and acknowledgement">
        {DELIVERY_STEPS.map(([status, label]) => {
          const entry = at(status);
          return (
            <li key={status} className={entry ? 'is-done' : ''}>
              <span className="delivery-label">{label}</span>
              <span className="muted">{entry ? `${dayLabel(entry.at) === 'Today' ? '' : `${dayLabel(entry.at)}, `}${formatTime(entry.at)}${entry.by ? `, ${entry.by}` : ''}` : 'Not yet'}</span>
            </li>
          );
        })}
      </ol>

      {resolved && escalation.note && <p className="note">Resolution note: {escalation.note}</p>}

      {!resolved && (
        <div className="escalation-actions">
          {!acknowledged && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => act('acknowledge')}>Acknowledge</button>}
          {acknowledged && (
            <form className="resolve-form" onSubmit={(event) => { event.preventDefault(); act('resolve'); }}>
              <label htmlFor={`note-${escalation.id}`}>What did you do? (optional)</label>
              <div className="resolve-row">
                <input id={`note-${escalation.id}`} className="input" value={note} onChange={(event) => setNote(event.target.value)} placeholder="For example: called the patient, advised to attend A&E" />
                <button type="submit" className="btn btn-primary" disabled={busy}>Resolve</button>
              </div>
            </form>
          )}
        </div>
      )}
    </article>
  );
}
