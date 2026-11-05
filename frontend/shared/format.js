const locale = 'en-GB';

// Countries offered in phone fields. Nigeria first, as most patients are there; a number typed with + works for anywhere.
export const PHONE_COUNTRIES = [
  { id: 'NG', name: 'Nigeria', dial: '234', example: '0803 123 4567', national: 10 },
  { id: 'GH', name: 'Ghana', dial: '233', example: '024 123 4567', national: 9 },
  { id: 'KE', name: 'Kenya', dial: '254', example: '0712 345 678', national: 9 },
  { id: 'ZA', name: 'South Africa', dial: '27', example: '071 234 5678', national: 9 },
  { id: 'UG', name: 'Uganda', dial: '256', example: '0772 123 456', national: 9 },
  { id: 'RW', name: 'Rwanda', dial: '250', example: '0788 123 456', national: 9 },
  { id: 'CM', name: 'Cameroon', dial: '237', example: '6 71 23 45 67', national: 9 },
  { id: 'GB', name: 'United Kingdom', dial: '44', example: '07400 123456', national: 10 },
  { id: 'US', name: 'United States or Canada', dial: '1', example: '201 555 0123', national: 10 }
];
const BY_DIAL = [...PHONE_COUNTRIES].sort((a, b) => b.dial.length - a.dial.length);

// Turns "+234 0803 123 4567", "0803 123 4567" (Nigeria) or "+44 7400 123456" into E.164, or null if it can't be a mobile number.
export function normalizePhone(raw) {
  const text = String(raw || '').trim();
  const digits = text.replace(/\D/g, '');
  if (!text.startsWith('+')) {
    if (digits.startsWith('234') && digits.length === 13) return `+${digits}`;
    if (digits.startsWith('0') && digits.length === 11) return `+234${digits.slice(1)}`;
    if (digits.length === 10 && /^[789]/.test(digits)) return `+234${digits}`;
    return null;
  }
  const country = BY_DIAL.find((item) => digits.startsWith(item.dial));
  if (!country) return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null;
  const national = digits.slice(country.dial.length).replace(/^0/, '');
  return national.length === country.national ? `+${country.dial}${national}` : null;
}

export function maskPhone(e164) {
  if (!e164) return '';
  const country = BY_DIAL.find((item) => e164.slice(1).startsWith(item.dial));
  return `+${country ? country.dial : e164.slice(1, 4)} ••• ••• ${e164.slice(-4)}`;
}

export const maskEmail = (email = '') => email.replace(/^(.)(.*)(@.*)$/, (_, first, middle, domain) => `${first}${'•'.repeat(Math.min(middle.length, 6))}${domain}`);

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
