import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Pencil, TriangleAlert } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { formatDateTime } from '../../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, Modal, StatusBadge, useAsync, useToast } from '../../shared/ui.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

const SECTIONS = [
  { key: 'medications', title: 'Medicines', fields: [['name', 'Name'], ['dose', 'Dose'], ['frequency', 'How often'], ['times', 'Times'], ['duration', 'For how long'], ['instructions', 'Instructions']] },
  { key: 'appointments', title: 'Appointments', fields: [['what', 'What'], ['where', 'Where'], ['date', 'Date'], ['time', 'Time']] },
  { key: 'tests', title: 'Tests', fields: [['name', 'Name'], ['where', 'Where'], ['date', 'Date']] }
];
const LISTS = [['symptoms_to_watch', 'Warning signs'], ['reminder_times', 'Reminder times']];

const fieldDomId = (path) => `field-${path.replace(/[^a-zA-Z0-9]+/g, '-')}`;
const display = (value) => (Array.isArray(value) ? value.join(', ') : value);

export default function PlanReview() {
  const { patientId } = useParams();
  const query = useAsync(async () => {
    const [patient, plan] = await Promise.all([CareLoopAPI.getPatient(patientId), CareLoopAPI.getPlan(patientId)]);
    return { patient: patient.patient, plan: plan.plan };
  }, [patientId]);
  const [draft, setDraft] = useState(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const toast = useToast();
  const { refreshCounts } = useDashboard();

  useEffect(() => { if (query.data) setDraft(structuredClone(query.data.plan)); }, [query.data]);

  const back = <Link className="back-link" to={`/patients/${patientId}`}><ArrowLeft aria-hidden="true" size={16} />Patient record</Link>;
  if (!query.data || !draft) {
    return <div className="page"><PageHeader title="Plan review" back={back} />{query.loading && <LoadingBlock lines={8} />}<ErrorNote error={query.error} onRetry={query.reload} /></div>;
  }

  const { patient, plan } = query.data;
  const issues = plan.verifier_issues || [];
  const issuesFor = (path) => issues.filter((issue) => issue.field === path);
  const approved = plan.status === 'approved';

  const setValue = (section, index, field, value) => setDraft((current) => {
    const next = structuredClone(current);
    if (index === null) next[section][field] = value;
    else next[section][index][field] = field === 'times' ? value.split(',').map((item) => item.trim()).filter(Boolean) : value;
    return next;
  });
  const setListValue = (key, index, value) => setDraft((current) => {
    const next = structuredClone(current);
    next[key][index] = value;
    return next;
  });

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      if (editing) await CareLoopAPI.updatePlan(plan.id, draft);
      await CareLoopAPI.approvePlan(plan.id, { override_issues: issues.length > 0 });
      toast(patient.consent_at ? 'Plan approved. Tomi will use it from now on.' : 'Plan approved. We will email the patient an invite; reminders start once they sign up.');
      refreshCounts();
      navigate(`/patients/${patient.id}`);
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
      setConfirming(false);
    }
  };

  const goToIssue = (issue) => {
    const target = document.getElementById(fieldDomId(issue.field));
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    (target?.querySelector('input') || target)?.focus({ preventScroll: true });
  };

  const sourceTexts = issues.map((issue) => issue.source_text).filter(Boolean);
  const lines = (plan.source_note || '').split(/\r?\n/);

  return (
    <div className="page plan-review">
      <PageHeader title="Plan review" back={back} sub={<span className="inline-meta">{patient.name} <LanguageTag language={patient.language} /> <StatusBadge kind="plan" status={plan.status} /></span>}>
        {!approved && !editing && <button type="button" className="btn btn-secondary" onClick={() => setEditing(true)}><Pencil aria-hidden="true" size={18} />Edit fields</button>}
        {!approved && (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => (issues.length ? setConfirming(true) : approve())}>
            <Check aria-hidden="true" size={18} />{editing ? 'Save and approve' : 'Approve plan'}
          </button>
        )}
      </PageHeader>
      {approved && <p className="note">Approved by {plan.approved_by}, {formatDateTime(plan.clinician_approved_at)}.</p>}
      {error && <p className="error-text" role="alert">{error}</p>}

      <section className={`verifier ${issues.length ? 'has-issues' : ''}`} aria-labelledby="verifier-title">
        <h2 id="verifier-title"><TriangleAlert aria-hidden="true" size={20} />{issues.length ? `Plan Verifier found ${issues.length} thing${issues.length > 1 ? 's' : ''} to check` : 'The Plan Verifier checked every field against the note and found nothing to fix'}</h2>
        {issues.length > 0 && (
          <ul>
            {issues.map((issue) => (
              <li key={issue.field}>
                <button type="button" className="issue-link" onClick={() => goToIssue(issue)}>{issue.issue}</button>
                <span className="muted"> {issue.severity === 'high' ? 'High' : 'Medium'} severity</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="review-grid">
        <article className="panel source-note" aria-labelledby="source-title">
          <h2 id="source-title">Discharge note</h2>
          <p className="muted">Exactly as written. Highlighted text is what the verifier is asking about.</p>
          <ol className="note-lines">
            {lines.map((line, index) => {
              const match = sourceTexts.find((text) => line.includes(text));
              if (!match) return <li key={index}>{line || ' '}</li>;
              const start = line.indexOf(match);
              return <li key={index}>{line.slice(0, start)}<mark>{match}</mark>{line.slice(start + match.length)}</li>;
            })}
          </ol>
        </article>

        <div className="plan-columns">
          {SECTIONS.map((section) => (
            <section key={section.key} className="panel" aria-labelledby={`sec-${section.key}`}>
              <h2 id={`sec-${section.key}`}>{section.title}</h2>
              {!(draft[section.key] || []).length && <p className="muted">None in the note.</p>}
              {(draft[section.key] || []).map((item, index) => (
                <div key={index} className="plan-record">
                  {section.fields.map(([field, label]) => {
                    const path = `${section.key}[${index}].${field}`;
                    const fieldIssues = issuesFor(path);
                    const inputId = `${fieldDomId(path)}-input`;
                    return (
                      <div key={field} id={fieldDomId(path)} className={`plan-field${fieldIssues.length ? ' has-issue' : ''}`} tabIndex={editing ? undefined : -1}>
                        {editing ? <label htmlFor={inputId}>{label}</label> : <span className="plan-field-label">{label}</span>}
                        <div>
                          {editing
                            ? <input id={inputId} className="input" value={display(item[field]) || ''} onChange={(event) => setValue(section.key, index, field, event.target.value)} aria-describedby={fieldIssues.length ? `${inputId}-issue` : undefined} />
                            : <span className={display(item[field]) ? '' : 'missing'}>{display(item[field]) || 'Missing'}</span>}
                          {fieldIssues.map((issue) => <p key={issue.issue} id={`${inputId}-issue`} className="field-issue">{issue.issue}</p>)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </section>
          ))}
          {LISTS.map(([key, title]) => (
            <section key={key} className="panel" aria-labelledby={`sec-${key}`}>
              <h2 id={`sec-${key}`}>{title}</h2>
              {!(draft[key] || []).length && <p className="muted">None in the note.</p>}
              <ul className="plain-list">
                {(draft[key] || []).map((value, index) => (
                  <li key={index} id={fieldDomId(`${key}[${index}]`)}>
                    {editing
                      ? <><label className="sr-only" htmlFor={`${key}-${index}`}>{title} {index + 1}</label><input id={`${key}-${index}`} className="input" value={value} onChange={(event) => setListValue(key, index, event.target.value)} /></>
                      : value}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>

      <aside className="safety-strip">Tomi will repeat this plan to the patient word for word. Please check every dose before you approve.</aside>

      {confirming && (
        <Modal title="Approve with open issues?" onClose={() => setConfirming(false)}>
          <p>The Plan Verifier flagged {issues.length} field{issues.length > 1 ? 's' : ''}. If you approve now, the patient gets the plan exactly as shown, and the record notes that you approved it anyway.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)}>Go back and fix</button>
            <button type="button" className="btn btn-primary" onClick={approve} disabled={busy}>{busy ? 'Approving…' : 'Approve anyway'}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
