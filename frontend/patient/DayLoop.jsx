import { Mic } from 'lucide-react';
import { formatTime } from '../shared/format.js';

/* The day as a loop: midnight at the top, the arc filled up to now, one bead per task at its due time.
   Tomi sits in the middle, because talking to Tomi is how most patients report back.
   The ring is a picture of the list below it, so it is hidden from screen readers and summarised in text. */
const SIZE = 320;
const C = SIZE / 2;
const R = 126;
const LABELS = [[0, 'Midnight'], [6, '6 am'], [12, 'Noon'], [18, '6 pm']];

const angleFor = (date) => ((date.getHours() * 60 + date.getMinutes()) / 1440) * 360;
function point(deg, radius = R) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [C + radius * Math.cos(rad), C + radius * Math.sin(rad)];
}
function arc(fromDeg, toDeg, radius = R) {
  const [x1, y1] = point(fromDeg, radius);
  const [x2, y2] = point(Math.max(fromDeg + 0.5, toDeg), radius);
  return `M ${x1} ${y1} A ${radius} ${radius} 0 ${toDeg - fromDeg > 180 ? 1 : 0} 1 ${x2} ${y2}`;
}
const beadKind = (status) => (['patient_reported_done', 'clinician_verified'].includes(status) ? 'done' : ['unable', 'overdue'].includes(status) ? 'missed' : 'due');

export default function DayLoop({ tasks, now = new Date(), onTalk, describedBy }) {
  const nowDeg = angleFor(now);
  const [nowX, nowY] = point(nowDeg);
  const done = tasks.filter((task) => beadKind(task.status) === 'done').length;

  return (
    <div className="day-loop">
      <svg className="day-loop-svg" viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true" focusable="false">
        <circle className="loop-track" cx={C} cy={C} r={R} />
        <path className="loop-elapsed" d={arc(0, nowDeg)} />
        {LABELS.map(([hour, label]) => {
          const [x, y] = point(hour * 15, R - 34);
          const [tx1, ty1] = point(hour * 15, R - 16);
          const [tx2, ty2] = point(hour * 15, R - 22);
          return (
            <g key={hour}>
              <line className="loop-tick" x1={tx1} y1={ty1} x2={tx2} y2={ty2} />
              <text className="loop-label" x={x} y={y} textAnchor="middle" dominantBaseline="middle">{label}</text>
            </g>
          );
        })}
        <circle className="loop-now-halo" cx={nowX} cy={nowY} r="12" />
        <circle className="loop-now" cx={nowX} cy={nowY} r="5" />
        {tasks.map((task) => {
          const [x, y] = point(angleFor(new Date(task.due_at)));
          const kind = beadKind(task.status);
          return (
            <g key={task.id} className={`loop-bead bead-${kind}`}>
              <circle cx={x} cy={y} r="14" />
              {kind === 'done' && <path d={`M ${x - 5.5} ${y + 0.5} l 3.8 3.8 l 7.2 -7.6`} />}
              {kind === 'missed' && <path d={`M ${x} ${y - 6} v 7 M ${x} ${y + 5} v 0.5`} />}
            </g>
          );
        })}
      </svg>

      <button type="button" className="loop-tomi" onClick={onTalk} aria-describedby={describedBy}>
        <span className="loop-tomi-disc" aria-hidden="true"><Mic size={34} strokeWidth={2.2} /></span>
        <span className="loop-tomi-label">Talk to Tomi</span>
      </button>

      <p className="loop-caption">
        <span className="loop-now-text">Now {formatTime(now.toISOString())}</span>
        <span>{tasks.length ? `${done} of ${tasks.length} done today` : 'Nothing due today'}</span>
      </p>
    </div>
  );
}
