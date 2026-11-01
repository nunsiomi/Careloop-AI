/* The open loop from the logo, drawn large: a day of care with beads where tasks fall. Decorative only. */
export default function LoopArt() {
  const beads = [28, 104, 196, 262];
  const r = 70;
  const point = (deg) => [90 + r * Math.cos(((deg - 90) * Math.PI) / 180), 90 + r * Math.sin(((deg - 90) * Math.PI) / 180)];
  const [endX, endY] = point(318);
  return (
    <svg className="loop-art" viewBox="0 0 180 180" aria-hidden="true" focusable="false">
      <circle className="loop-art-track" cx="90" cy="90" r={r} />
      <path className="loop-art-arc" d={`M 90 20 A ${r} ${r} 0 1 1 ${endX} ${endY}`} />
      {beads.map((deg) => { const [x, y] = point(deg); return <circle key={deg} className="loop-art-bead" cx={x} cy={y} r="7" />; })}
      <circle className="loop-art-tomi" cx={endX} cy={endY} r="11" />
    </svg>
  );
}
