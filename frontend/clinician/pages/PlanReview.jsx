import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Plus, Save, Trash2, TriangleAlert } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { formatDateTime } from '../../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, Modal, StatusBadge, useAsync, useToast } from '../../shared/ui.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';
import { DurationField, FrequencyField, TimesField, timesPerDay } from '../plan-fields.jsx';

// Each field says how it is entered: typed text, a calendar, a clock, or a list to pick from.
const SECTIONS = [
  { key: 'medications', title: 'Medicines', item: 'medicine', blank: { name: '', dose: '', frequency: '', times: [], duration: '', instructions: '' },
    fields: [['name', 'Name', 'text', 'Name, strength and form, as on the note'], ['dose', 'Dose', 'text', 'Amount each time, such as 1 tablet or 5 ml'],
      ['frequency', 'How often', 'frequency'], ['times', 'Times', 'times'], ['duration', 'For how long', 'duration'], ['instructions', 'Instructions', 'text', 'Such as after food']] },
  { key: 'appointments', title: 'Appointments', item: 'appointment', blank: { what: '', where: '', date: '', time: '' },
    fields: [['what', 'What', 'text'], ['where', 'Where', 'text'], ['date', 'Date', 'date'], ['time', 'Time', 'time']] },
  { key: 'tests', title: 'Tests', item: 'test', blank: { name: '', where: '', date: '' },
    fields: [['name', 'Name', 'text'], ['where', 'Where', 'text'], ['date', 'Date', 'date']] }
];
const LISTS = [['symptoms_to_watch', 'Warning signs', 'warning sign'], ['reminder_times', 'Reminder times', 'reminder time']];

const fieldDomId = (path) => `field-${path.replace(/[^a-zA-Z0-9]+/g, '-')}`;
const display = (value) => (Array.isArray(value) ? value.join(', ') : value);

// Drop empty rows the clinician added and did not fill, so they are not saved as blanks.
const tidy = (plan) => ({
  ...plan,
  medications: plan.medications.map((item) => ({ ...item, frequency: item.frequency.trim(), times: item.times.filter(Boolean) })),
  symptoms_to_watch: plan.symptoms_to_watch.map((item) => item.trim()).filter(Boolean),
  reminder_times: plan.reminder_times.filter(Boolean)
});
// Every section and field present, so the form never meets a missing value.
const editable = (plan) => tidy({
  ...plan,
  ...Object.fromEntries(SECTIONS.map(({ key, blank }) => [key, (plan[key] || []).map((item) => ({ ...blank, ...item }))])),
  ...Object.fromEntries(LISTS.map(([key]) => [key, plan[key] || []]))
});
const planFields = (plan) => Object.fromEntries([...SECTIONS.map(({ key }) => key), ...LISTS.map(([key]) => key)].map((key) => [key, plan[key]]));

export default function PlanReview() {
  const { patientId } = useParams();
  const query = useAsync(async () => {
    const [patient, plan] = await Promise.all([CareLoopAPI.getPatient(patientId), CareLoopAPI.getPlan(patientId)]);
    return { patient: patient.patient, plan: plan.plan };
  }, [patientId]);
  const [plan, setPlan] = useState(null);
  const [draft, setDraft] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const toast = useToast();
  const { refreshCounts } = useDashboard();

  useEffect(() => {
    if (!query.data) return;
    setPlan(query.data.plan);
    setDraft(editable(structuredClone(query.data.plan)));
  }, [query.data]);

  const back = <Link className="back-link" to={`/patients/${patientId}`}><ArrowLeft aria-hidden="true" size={16} />Patient record</Link>;
  if (!query.data || !plan || !draft) {
    return <div className="page"><PageHeader title="Plan review" back={back} />{query.loading && <LoadingBlock lines={8} />}<ErrorNote error={query.error} onRetry={query.reload} /></div>;
  }

  const { patient } = query.data;
  const issues = plan.verifier_issues || [];
  const issuesFor = (path) => issues.filter((issue) => issue.field === path);
  const approved = plan.status === 'approved';
  const changed = JSON.stringify(planFields(tidy(draft))) !== JSON.stringify(planFields(editable(plan)));

  const update = (change) => setDraft((current) => { const next = structuredClone(current); change(next); return next; });
  const setField = (section, index, field, value) => update((next) => {
    const item = next[section][index];
    item[field] = value;
    // Picking "Twice a day" leaves room for two times; the clinician still sets each one.
    const perDay = field === 'frequency' ? timesPerDay(value) : null;
    if (perDay && item.times.length < perDay) item.times = [...item.times, ...Array(perDay - item.times.length).fill('')];
  });

  // Saves the edits; the server checks them again and returns the new list of things to check.
  const save = async () => {
    const { plan: saved } = await CareLoopAPI.updatePlan(plan.id, planFields(tidy(draft)));
    setPlan(saved);
    setDraft(editable(structuredClone(saved)));
    return saved;
  };
  const saveOnly = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = await save();
      const open = (saved.verifier_issues || []).length;
      toast(open ? `Changes saved. ${open} thing${open > 1 ? 's' : ''} still to check.` : 'Changes saved.');
    } catch (requestError) { setError(requestError.message); }
    setBusy(false);
  };
  const approve = async (acknowledged = false) => {
    setBusy(true);
    setError(null);
    try {
      const current = changed ? await save() : plan;
      const open = (current.verifier_issues || []).length;
      if (open && !acknowledged) { setConfirming(true); setBusy(false); return; }
      await CareLoopAPI.approvePlan(current.id, { override_issues: open > 0 });
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
    (target?.querySelector('input, select') || target)?.focus({ preventScroll: true });
  };

  const sourceTexts = issues.map((issue) => issue.source_text).filter(Boolean);
  const lines = (plan.source_note || '').split(/\r?\n/);

  const control = (kind, inputId, value, onChange, label, describedBy) => {
    if (kind === 'frequency') return <FrequencyField id={inputId} value={value} onChange={onChange} describedBy={describedBy} />;
    if (kind === 'duration') return <DurationField id={inputId} value={value} onChange={onChange} describedBy={describedBy} />;
    if (kind === 'times') return <TimesField id={inputId} label={label} value={value} onChange={onChange} describedBy={describedBy} />;
    if (kind === 'date') return <input id={inputId} className="input input-date" type="date" value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={describedBy} />;
    if (kind === 'time') return <input id={inputId} className="input input-time" type="time" value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={describedBy} />;
    return <input id={inputId} className="input" value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={describedBy} />;
  };

  return (
    <div className="page plan-review">
      <PageHeader title="Plan review" back={back} sub={<span className="inline-meta">{patient.name} <LanguageTag language={patient.language} /> <StatusBadge kind="plan" status={plan.status} /></span>}>
        {!approved && <button type="button" className="btn btn-secondary" disabled={busy || !changed} onClick={saveOnly}><Save aria-hidden="true" size={18} />Save changes</button>}
        {!approved && (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => approve()}>
            <Check aria-hidden="true" size={18} />{changed ? 'Save and approve' : 'Approve plan'}
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
        {!approved && changed && <p className="hint">You have changes that are not saved yet. Save them to check the plan again.</p>}
      </section>

      <div className="review-grid">
        <article className="panel source-note" aria-labelledby="source-title">
          <h2 id="source-title">Discharge note</h2>
          <p className="muted">Exactly as written. Highlighted text is what the verifier is asking about.</p>
          <ol className="note-lines">
            {lines.map((line, index) => {
              const match = sourceTexts.find((text) => line.includes(text));
              if (!match) return <li key={index}>{line || ' '}</li>;
              const start = line.indexOf(match);
              return <li key={index}>{line.slice(0, start)}<mark>{match}</mark>{line.slice(start + match.length)}</li>;
            })}
          </ol>
        </article>

        <div className="plan-columns">
          {SECTIONS.map((section) => (
            <section key={section.key} className="panel" aria-labelledby={`sec-${section.key}`}>
              <h2 id={`sec-${section.key}`}>{section.title}</h2>
              {!draft[section.key].length && <p className="muted">None in the note.{!approved && ` Add one if the patient needs it.`}</p>}
              {draft[section.key].map((item, index) => (
                <div key={index} className="plan-record">
                  {section.fields.map(([field, label, kind, hint]) => {
                    const path = `${section.key}[${index}].${field}`;
                    const fieldIssues = issuesFor(path);
                    const inputId = `${fieldDomId(path)}-input`;
                    const describedBy = [hint && `${inputId}-hint`, fieldIssues.length && `${inputId}-issue`].filter(Boolean).join(' ') || undefined;
                    return (
                      <div key={field} id={fieldDomId(path)} className={`plan-field${fieldIssues.length ? ' has-issue' : ''}`} tabIndex={approved ? -1 : undefined}>
                        {approved ? <span className="plan-field-label">{label}</span> : <label htmlFor={inputId}>{label}</label>}
                        <div>
                          {approved
                            ? <span className={display(item[field]) ? '' : 'missing'}>{display(item[field]) || 'Missing'}</span>
                            : control(kind, inputId, item[field], (value) => setField(section.key, index, field, value), label, describedBy)}
                          {!approved && hint && <p id={`${inputId}-hint`} className="hint">{hint}</p>}
                          {fieldIssues.map((issue) => <p key={issue.issue} id={`${inputId}-issue`} className="field-issue">{issue.issue}</p>)}
                        </div>
                      </div>
                    );
                  })}
                  {!approved && (
                    <button type="button" className="btn btn-quiet remove-item" onClick={() => update((next) => { next[section.key].splice(index, 1); })}>
                      <Trash2 aria-hidden="true" size={16} />Remove this {section.item}
                    </button>
                  )}
                </div>
              ))}
              {!approved && (
                <button type="button" className="btn btn-secondary add-item" onClick={() => update((next) => { next[section.key].push(structuredClone(section.blank)); })}>
                  <Plus aria-hidden="true" size={18} />Add {section.item}
                </button>
              )}
            </section>
          ))}
          {LISTS.map(([key, title, item]) => (
            <section key={key} className="panel" aria-labelledby={`sec-${key}`}>
              <h2 id={`sec-${key}`}>{title}</h2>
              {!draft[key].length && <p className="muted">None in the note.</p>}
              {approved
                ? <ul className="plain-list">{draft[key].map((value, index) => <li key={index}>{value}</li>)}</ul>
                : key === 'reminder_times'
                  ? draft[key].length > 0 && <TimesField id={fieldDomId(`${key}[0]`)} label="Reminder time" value={draft[key]} onChange={(value) => update((next) => { next[key] = value; })} />
                  : (
                    <ul className="plain-list">
                      {draft[key].map((value, index) => (
                        <li key={index} id={fieldDomId(`${key}[${index}]`)} className="field-row">
                          <label className="sr-only" htmlFor={`${key}-${index}`}>{title} {index + 1}</label>
                          <input id={`${key}-${index}`} className="input" value={value} onChange={(event) => update((next) => { next[key][index] = event.target.value; })} />
                          <button type="button" className="btn btn-quiet btn-icon" onClick={() => update((next) => { next[key].splice(index, 1); })} aria-label={`Remove ${item} ${index + 1}`}><Trash2 aria-hidden="true" size={16} /></button>
                        </li>
                      ))}
                    </ul>
                  )}
              {!approved && !(key === 'reminder_times' && draft[key].length) && (
                <button type="button" className="btn btn-secondary add-item" onClick={() => update((next) => { next[key].push(''); })}>
                  <Plus aria-hidden="true" size={18} />Add {item}
                </button>
              )}
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
            <button type="button" className="btn btn-primary" onClick={() => approve(true)} disabled={busy}>{busy ? 'Approving…' : 'Approve anyway'}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
