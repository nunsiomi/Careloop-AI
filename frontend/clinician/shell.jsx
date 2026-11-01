import { createContext, useContext } from 'react';

// `user` comes from the staff session; actions such as acknowledging an escalation are recorded under their name.
export const DashboardContext = createContext({ counts: {}, refreshCounts: () => {}, user: null, signOut: () => {}, dataVersion: 0, dataChanged: () => {}, openAssistant: () => {} });
export const useDashboard = () => useContext(DashboardContext);

export function PageHeader({ title, sub, children, back }) {
  return (
    <header className="page-head">
      <div className="page-head-text">
        {back}
        <h1 tabIndex={-1}>{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

/* A patient's tasks as a small ring: done, due and missed segments, with a red centre for an open escalation.
   Decorative; the same numbers are always written next to it. */
export function PatientLoop({ counts = {}, escalated = false, size = 40 }) {
  const done = counts.done || 0;
  const due = counts.due || 0;
  const missed = counts.missed || 0;
  const total = done + due + missed;
  const r = 15;
  const length = 2 * Math.PI * r;
  let offset = 0;
  const segment = (value, className) => {
    if (!value) return null;
    const dash = (value / total) * length;
    const element = <circle key={className} className={className} cx="20" cy="20" r={r} strokeDasharray={`${Math.max(dash - 2.5, 1)} ${length}`} strokeDashoffset={-offset} />;
    offset += dash;
    return element;
  };
  return (
    <svg className="patient-loop" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <circle className="pl-track" cx="20" cy="20" r={r} />
      <g transform="rotate(-90 20 20)">
        {total > 0 && [segment(done, 'pl-done'), segment(due, 'pl-due'), segment(missed, 'pl-missed')]}
      </g>
      {escalated && <circle className="pl-flag" cx="20" cy="20" r="6" />}
    </svg>
  );
}
