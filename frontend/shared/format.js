const locale = 'en-GB';

export const formatTime = (iso) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });

export const formatDate = (iso) => new Date(iso).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' });

export const formatDateLong = (iso) => new Date(iso).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' });

export const formatDateTime = (iso) => `${formatDate(iso)}, ${formatTime(iso)}`;

export function isSameDay(first, second = new Date()) {
  const a = new Date(first);
  const b = new Date(second);
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function dayLabel(iso) {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (isSameDay(date, today)) return 'Today';
  if (isSameDay(date, yesterday)) return 'Yesterday';
  if (isSameDay(date, tomorrow)) return 'Tomorrow';
  return formatDateLong(iso);
}

export function relativeTime(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (Math.abs(minutes) < 1) return 'just now';
  if (minutes > 0 && minutes < 60) return `${minutes} min ago`;
  if (minutes < 0 && minutes > -60) return `in ${-minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours > 0 && hours < 24) return `${hours} h ago`;
  if (hours < 0 && hours > -24) return `in ${-hours} h`;
  return formatDateTime(iso);
}

export function duration(startIso, endIso) {
  if (!endIso) return null;
  const seconds = Math.max(0, Math.round((new Date(endIso) - new Date(startIso)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes} min ${seconds % 60} s` : `${seconds} s`;
}

// "today at 19:30", "tomorrow at 07:00", "on Monday 2 November at 10:00".
export function whenLabel(iso) {
  const day = dayLabel(iso);
  const time = formatTime(iso);
  return ['Today', 'Tomorrow', 'Yesterday'].includes(day) ? `${day.toLowerCase()} at ${time}` : `on ${day} at ${time}`;
}

export const firstName = (name = '') => name.split(' ')[0];

export function groupByDay(items, key) {
  const groups = new Map();
  items.forEach((item) => {
    const label = dayLabel(item[key]);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  });
  return [...groups.entries()];
}
