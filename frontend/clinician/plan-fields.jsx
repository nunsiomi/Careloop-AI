// Form controls for the plan review page: a calendar for dates, a clock for times, and lists for how often and
// for how long, so a clinician picks values instead of typing them in a set format.
import { useState } from 'react';
import { Plus, X } from 'lucide-react';

// How often a medicine is taken, and how many times a day that means (null: no set number of times).
export const FREQUENCIES = [
  ['Once a day', 1], ['Twice a day', 2], ['Three times a day', 3], ['Four times a day', 4],
  ['Every other day', 1], ['Once a week', 1], ['Only when needed', null]
];
const OTHER = 'other';
const UNITS = ['days', 'weeks', 'months'];

export const timesPerDay = (frequency) => FREQUENCIES.find(([label]) => label === frequency)?.[1] ?? null;

export function FrequencyField({ id, value, onChange, describedBy }) {
  const listed = !value || FREQUENCIES.some(([label]) => label === value);
  const [ownWords, setOwnWords] = useState(!listed);
  const pick = (choice) => {
    setOwnWords(choice === OTHER);
    onChange(choice === OTHER ? (listed ? '' : value) : choice);
  };
  return (
    <div className="field-stack">
      <select id={id} className="select" value={ownWords ? OTHER : value} onChange={(event) => pick(event.target.value)} aria-describedby={describedBy}>
        <option value="">Choose</option>
        {FREQUENCIES.map(([label]) => <option key={label} value={label}>{label}</option>)}
        <option value={OTHER}>Something else</option>
      </select>
      {ownWords && <><label className="sr-only" htmlFor={`${id}-other`}>How often, in your words</label><input id={`${id}-other`} className="input" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Every 8 hours" autoFocus={listed} /></>}
    </div>
  );
}

export function DurationField({ id, value, onChange, describedBy }) {
  const match = /^(\d+)\s*(day|week|month)s?$/i.exec((value || '').trim());
  if (value && !match) {
    return <input id={id} className="input" value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={describedBy} />;
  }
  const count = match ? match[1] : '';
  const unit = match ? `${match[2].toLowerCase()}s` : 'days';
  const set = (nextCount, nextUnit) => onChange(nextCount ? `${nextCount} ${Number(nextCount) === 1 ? nextUnit.slice(0, -1) : nextUnit}` : '');
  return (
    <div className="field-row">
      <input id={id} className="input input-number" type="number" min="1" max="365" inputMode="numeric" value={count} onChange={(event) => set(event.target.value, unit)} aria-describedby={describedBy} />
      <label className="sr-only" htmlFor={`${id}-unit`}>Days, weeks or months</label>
      <select id={`${id}-unit`} className="select" value={unit} onChange={(event) => set(count || '1', event.target.value)}>
        {UNITS.map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
    </div>
  );
}

// One clock per time of day, with a button to add or remove a time.
export function TimesField({ id, label, value, onChange, describedBy }) {
  const times = value.length ? value : [''];
  const set = (index, time) => onChange(times.map((item, place) => (place === index ? time : item)));
  return (
    <div className="field-stack">
      {times.map((time, index) => (
        <div key={index} className="field-row">
          <input id={index ? `${id}-${index}` : id} className="input input-time" type="time" value={time} onChange={(event) => set(index, event.target.value)} aria-label={index ? `${label} ${index + 1}` : undefined} aria-describedby={describedBy} />
          {times.length > 1 && <button type="button" className="btn btn-quiet btn-icon" onClick={() => onChange(times.filter((_, place) => place !== index))} aria-label={`Remove ${label.toLowerCase()} ${index + 1}`}><X aria-hidden="true" size={18} /></button>}
        </div>
      ))}
      <button type="button" className="btn btn-quiet add-time" onClick={() => onChange([...times, ''])}><Plus aria-hidden="true" size={16} />Add a time</button>
    </div>
  );
}
