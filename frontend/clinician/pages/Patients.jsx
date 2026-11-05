import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, UserPlus } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { relativeTime } from '../../shared/format.js';
import { Badge, ErrorNote, LanguageTag, LoadingBlock, StatusBadge, useAsync } from '../../shared/ui.jsx';
import { AddPatientDialog, ChannelLabel } from '../components.jsx';
import { PageHeader, PatientLoop, useDashboard } from '../shell.jsx';

const FILTERS = [
  { id: 'all', label: 'All', match: () => true },
  { id: 'mine', label: 'My patients', match: (patient, user) => patient.assigned_to?.id === user.id },
  { id: 'review', label: 'Plan to review', match: (patient) => patient.plan_status === 'needs_review' },
  { id: 'escalated', label: 'Open escalation', match: (patient) => patient.open_escalations > 0 },
  { id: 'barrier', label: 'Open barrier', match: (patient) => patient.open_barriers > 0 },
  { id: 'invited', label: 'Not joined yet', match: (patient) => !patient.consent_at }
];

const urgency = (patient) => (patient.open_escalations ? 0 : patient.overdue_critical ? 1 : patient.plan_status === 'needs_review' ? 2 : patient.open_barriers ? 3 : 4);

export default function Patients() {
  const query = useAsync(() => CareLoopAPI.listPatients(), []);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const { user } = useDashboard();
  const active = FILTERS.find((item) => item.id === filter);
  const patients = (query.data?.patients || [])
    .filter((patient) => active.match(patient, user))
    .filter((patient) => patient.name.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((first, second) => urgency(first) - urgency(second) || first.name.localeCompare(second.name));

  return (
    <div className="page">
      <PageHeader title="Patients" sub="Patients who need you most are at the top.">
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}><UserPlus aria-hidden="true" size={18} />Add patient</button>
      </PageHeader>

      <div className="toolbar">
        <div className="search">
          <Search aria-hidden="true" size={18} />
          <label htmlFor="patient-search" className="sr-only">Search patients by name</label>
          <input id="patient-search" className="input" type="search" placeholder="Search by name" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <div className="filter-row" role="group" aria-label="Filter patients">
          {FILTERS.map((item) => <button key={item.id} type="button" className="filter-chip" aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}
        </div>
      </div>

      {query.loading && !query.data && <LoadingBlock lines={5} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !patients.length && <p className="empty">No patients match. Clear the search or choose another filter.</p>}

      {patients.length > 0 && (
        <div className="table-wrap" role="region" aria-label="Patients" tabIndex={0}>
          <table className="table">
            <caption className="sr-only">Patients</caption>
            <thead>
              <tr><th scope="col">Patient</th><th scope="col">Language</th><th scope="col">Lead</th><th scope="col">Plan</th><th scope="col">Open tasks</th><th scope="col">Needs attention</th><th scope="col">Last contact</th></tr>
            </thead>
            <tbody>
              {patients.map((patient) => (
                <tr key={patient.id} onClick={() => navigate(`/patients/${patient.id}`)}>
                  <td><span className="name-cell"><PatientLoop counts={patient.task_counts} escalated={patient.open_escalations > 0} size={32} /><span><Link className="table-link" to={`/patients/${patient.id}`} onClick={(event) => event.stopPropagation()}>{patient.name}</Link>{patient.age && <span className="muted"> {patient.age}</span>}</span></span></td>
                  <td><LanguageTag language={patient.language} /></td>
                  <td>{patient.assigned_to ? patient.assigned_to.name : <span className="muted">Not assigned</span>}</td>
                  <td><StatusBadge kind="plan" status={patient.plan_status} /></td>
                  <td>{patient.open_tasks}</td>
                  <td className="cell-badges">
                    {patient.open_escalations > 0 && <Badge tone="red">Escalation</Badge>}
                    {patient.overdue_critical > 0 && <Badge tone="amber">Overdue task</Badge>}
                    {patient.open_barriers > 0 && <Badge tone="amber">{patient.open_barriers} barrier{patient.open_barriers > 1 ? 's' : ''}</Badge>}
                    {patient.failed_messages > 0 && <Badge tone="amber">Message not delivered</Badge>}
                    {!patient.consent_at && <Badge tone="neutral">Not joined yet</Badge>}
                  </td>
                  <td>{patient.last_contact ? <span className="last-contact"><ChannelLabel channel={patient.last_contact.channel} iconOnly />{relativeTime(patient.last_contact.at)}</span> : <span className="muted">None</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding && <AddPatientDialog onClose={() => setAdding(false)} />}
    </div>
  );
}
