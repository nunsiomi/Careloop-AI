// MVP languages (doc v2, section 7.1). Pidgin is removed from the MVP.
// Hausa, Yoruba and Igbo stay in beta until native-speaker validation passes the acceptance gate.
export const LANGUAGES = [
  { name: 'Hausa', native: 'Hausa', greeting: 'Sannu', beta: true },
  { name: 'Yoruba', native: 'Yorùbá', greeting: 'Báwo ni', beta: true },
  { name: 'Igbo', native: 'Igbo', greeting: 'Ndewo', beta: true },
  { name: 'English', native: 'Plain English', greeting: 'Hello', beta: false }
];

export function languageInfo(name) {
  return LANGUAGES.find((language) => language.name === name) || { name, native: name, beta: true };
}

export const READING_LEVELS = [
  { id: 'basic', title: 'Short and simple', detail: 'Fewer words, one step at a time.' },
  { id: 'standard', title: 'Standard', detail: 'Clear language with normal detail.' },
  { id: 'caregiver', title: 'I help someone with care', detail: 'For a family member or helper.' }
];

export const CHANNELS = [
  { id: 'web', title: 'Chat in this app', detail: 'See your plan and message Tomi here.' },
  { id: 'voice', title: 'Phone calls from Tomi', detail: 'Tomi calls at your chosen time to check in. You can always call Tomi too.' },
  { id: 'sms', title: 'Text message reminders', detail: 'A short text before each medicine and the evening before a visit. It never says what the medicine is for.' },
  { id: 'email', title: 'Email reminders', detail: 'The same reminders by email, with a link back to this app.' }
];

export const CONTACT_WINDOWS = [
  { id: '08:00-11:00', title: 'Morning', detail: '8:00 to 11:00' },
  { id: '12:00-15:00', title: 'Afternoon', detail: '12:00 to 15:00' },
  { id: '16:00-19:00', title: 'Evening', detail: '16:00 to 19:00' }
];
