// In-browser mock of the CareLoop API (doc v2, section 11). Every person, hospital, phone number and record here is invented;
// names are kept realistic so the product reads naturally, but none of it refers to a real patient or place.
// Clinical wording lives here, standing in for the backend; UI components never write it.
import { maskPhone } from './format.js';
import { MESSAGE_CHANNELS } from './languages.js';

const STORAGE_KEY = 'careloop-mock-v5';
const DEFAULT_FACILITY = 'Kestrel General Hospital';
// The sample patients belong to whichever care facility the signed-in staff member chose (see setMockFacility).
let FACILITY = DEFAULT_FACILITY;
const shortFacility = (name) => name.replace(/\s+(General Hospital|Teaching Hospital|Specialist Hospital|Medical Centre|Pharmacy|Family Clinic|Care Home)$/, '');
const TOMI_LINE = '0800 000 0000';
const REVIEWER = 'Dr. Ada Okafor';
const DEMO_PIN = '1234';

// Demo stand-in for the backend safety engine's red_flags.json. Substrings only; the real rules live server-side.
const RED_FLAG_TERMS = ['chest', 'breath', 'breathe', 'faint', 'kirji', 'ƙirji', 'numfashi', 'àyà', 'mímí'];
const BARRIER_TERMS = { cost: ['cost', 'money', 'afford', 'price', 'kudi'], transport: ['transport', 'travel', 'bus', 'far'], stock: ['stock', 'buy', 'could not get', 'not get', 'pharmacy', 'out of'], understanding: ['understand', 'confus'] };

const RESOURCES = {
  stock: [{ name: 'Allen Junction Pharmacy', type: 'Pharmacy', distance: 'About 2 km', phone: '+2348000000555', note: 'Stock is not guaranteed. Call before you go.' }],
  cost: [{ name: 'Kestrel Patient Support Desk', type: 'Payment help', distance: 'At the clinic', phone: '+2348000000556', note: 'Ask about payment plans for prescribed medicine.' }],
  transport: [{ name: 'Kestrel Ride to Clinic scheme', type: 'Transport help', distance: 'Phone only', phone: '+2348000000557', note: 'May help with travel to clinic visits. Not guaranteed.' }],
  understanding: [{ name: 'Your care team', type: 'Care team', distance: 'Kestrel General Hospital', phone: '+2348000000558', note: 'Ask them to explain your plan again.' }]
};

const SUPPORT = { tomi_number: '+2348000000000', emergency_number: '112', emergency_text: 'If you feel very unwell, go to the nearest hospital now.' };

const SAMPLE_NOTES = [
  { id: 'note-a', title: 'Sample A: heart follow-up', text: 'Discharge summary, Kestrel General Hospital.\nAmlodipine 5 mg tablet, one tablet every morning at 08:00 for 30 days.\nFollow-up at the Heart Clinic, room 3, in 7 days at 10:00.\nKidney function blood test at the hospital laboratory within 7 days.\nReturn to hospital at once for chest pain, trouble breathing or fainting.' },
  { id: 'note-b', title: 'Sample B: antibiotic course', text: 'Discharge summary, Kestrel General Hospital.\nAmoxicillin 500 mg capsule, take as directed for 7 days.\nWound check at the Wound Clinic next week.\nReturn to hospital at once for high fever or spreading redness.' },
  { id: 'note-c', title: 'Sample C: diabetes review', text: 'Discharge summary, Kestrel General Hospital.\nMetformin 500 mg tablet, one tablet twice daily with food at 08:00 and 20:00.\nReview at the Diabetes Clinic in 14 days at 09:30.\nReturn to hospital at once for confusion or fainting.' }
];

/* ---------- Email (and later SMS) reminders (doc v2, section 8) ----------
   Texts and emails are generic: they never name a medicine, condition or test. They point the patient
   back to the app or to Tomi's phone line. Replies are not read. SMS is off until there is a provider (MESSAGE_CHANNELS). */
const MESSAGE_TEMPLATES = {
  medicine: { title: 'Medicine reminder', body: (first) => `CareLoop: Hello ${first}, you have a reminder from ${FACILITY}. Open the CareLoop app or call Tomi on ${TOMI_LINE}. Do not reply.` },
  test: { title: 'Test reminder', body: (first) => `CareLoop: Hello ${first}, you have a reminder from ${FACILITY}. Open the CareLoop app or call Tomi on ${TOMI_LINE}. Do not reply.` },
  visit: { title: 'Visit reminder', body: (first) => `CareLoop: Hello ${first}, you have a care visit soon. Open the CareLoop app for the time and place, or call Tomi on ${TOMI_LINE}. Do not reply.` },
  visit_moved: { title: 'Visit time changed', body: (first) => `CareLoop: Hello ${first}, your visit time has changed. Open the CareLoop app to see the new time, or call Tomi on ${TOMI_LINE}. Do not reply.` },
  support: { title: 'Contact that may help', body: (first) => `CareLoop: Hello ${first}, your care team shared a contact that may help. Open the CareLoop app to see it, or call Tomi on ${TOMI_LINE}. Do not reply.` },
  missed_call: { title: 'Tomi tried to call', body: (first) => `CareLoop: Hello ${first}, Tomi tried to call you. Call Tomi back on ${TOMI_LINE} when you can, or open the CareLoop app. Do not reply.` },
  call_clinic: { title: 'Please contact your care team', body: (first) => `CareLoop: Hello ${first}, your care team at ${FACILITY} would like to hear from you. Call Tomi on ${TOMI_LINE} or open the CareLoop app. Do not reply.` }
};
const MANUAL_TEMPLATES = ['medicine', 'visit', 'call_clinic'];
const QUIET_START = 21;
const QUIET_END = 7;
const ACTIVE_MESSAGE = ['scheduled', 'sent', 'delivered'];
const maskEmail = (email) => (email ? email.replace(/^(.)(.*)(@.*)$/, (_, a, b, c) => `${a}${'•'.repeat(Math.min(b.length, 5))}${c}`) : '');

// Move a send time out of quiet hours (21:00 to 07:00) to 07:00.
function outsideQuietHours(iso) {
  const date = new Date(iso);
  const hour = date.getHours();
  if (hour >= QUIET_START) { date.setDate(date.getDate() + 1); date.setHours(QUIET_END, 0, 0, 0); }
  else if (hour < QUIET_END) date.setHours(QUIET_END, 0, 0, 0);
  return date.toISOString();
}

function queueMessage(data, patient, { channel, template, scheduled_for = new Date().toISOString(), task_id = null, appointment_id = null, created_by = 'Reminder scheduler', status = 'scheduled', ...extra }) {
  const first = patient.name.split(' ')[0];
  const message = {
    id: makeId('n'), patient_id: patient.id, channel, template, title: MESSAGE_TEMPLATES[template].title,
    subject: channel === 'email' ? 'A reminder from your care team' : null, body: MESSAGE_TEMPLATES[template].body(first),
    to: channel === 'sms' ? maskPhone(patient.phone_e164) : maskEmail(patient.email),
    status, scheduled_for, sent_at: null, delivered_at: null, failure_reason: null, task_id, appointment_id, created_by, ...extra
  };
  data.notifications.push(message);
  return message;
}

// The channel a one-off message goes by: the first reminder channel the patient agreed to and can receive.
const messageChannels = (patient) => MESSAGE_CHANNELS.filter((channel) => patient.channels.includes(channel) && (channel !== 'email' || patient.email));
const messageChannel = (patient) => messageChannels(patient)[0] || null;
const channelNoun = (channel) => (channel === 'sms' ? 'text' : 'email');

function hasActive(data, patientId, match) {
  return data.notifications.some((item) => item.patient_id === patientId && ACTIVE_MESSAGE.includes(item.status) && match(item));
}

// What the backend scheduler does after consent and plan approval: one text (and/or email) 30 minutes before each
// due task, and one the evening before each visit, only on channels the patient agreed to.
function scheduleReminders(data, patient) {
  if (!patient.consent_at) return;
  const channels = messageChannels(patient);
  const now = Date.now();
  data.tasks.filter((task) => task.patient_id === patient.id && task.status === 'pending' && new Date(task.due_at).getTime() > now).forEach((task) => {
    channels.forEach((channel) => {
      if (hasActive(data, patient.id, (item) => item.task_id === task.id && item.channel === channel)) return;
      const sendAt = Math.max(new Date(task.due_at).getTime() - 30 * 60000, now + 60000);
      queueMessage(data, patient, { channel, template: task.type === 'medication' ? 'medicine' : 'test', task_id: task.id, scheduled_for: outsideQuietHours(new Date(sendAt).toISOString()) });
    });
  });
  data.appointments.filter((item) => item.patient_id === patient.id && ['scheduled', 'confirmed', 'rescheduled', 'reschedule_requested'].includes(item.status) && new Date(item.starts_at).getTime() > now).forEach((appointment) => {
    const eve = new Date(appointment.starts_at);
    eve.setDate(eve.getDate() - 1);
    eve.setHours(18, 0, 0, 0);
    if (eve.getTime() < now) return;
    channels.forEach((channel) => {
      if (hasActive(data, patient.id, (item) => item.appointment_id === appointment.id && item.template === 'visit' && item.channel === channel)) return;
      queueMessage(data, patient, { channel, template: 'visit', appointment_id: appointment.id, scheduled_for: eve.toISOString() });
    });
  });
}

function cancelMessages(patientId, match, reason) {
  db.notifications.forEach((item) => {
    if (item.patient_id === patientId && item.status === 'scheduled' && match(item)) { item.status = 'cancelled'; item.failure_reason = reason; }
  });
}

/* ---------- time helpers ---------- */

function at(dayOffset, hhmm) {
  const date = new Date();
  date.setDate(date.getDate() + dayOffset);
  const [hours, minutes] = hhmm.split(':').map(Number);
  date.setHours(hours, minutes, 0, 0);
  return date.toISOString();
}
const nowIso = () => new Date().toISOString();
const dateOnly = (iso) => iso.slice(0, 10);
let counter = 0;
const makeId = (prefix) => `${prefix}-${Date.now().toString(36)}-${(counter += 1)}`;

/* ---------- seed ---------- */

function seed() {
  const zainabNote = 'Discharge summary: Zainab Musa, Kestrel General Hospital.\nAmlodipine 5 mg tablet, one tablet every morning at 08:00 for 30 days.\nBisoprolol 5 mg tablet, one tablet every evening at 20:00 for 30 days.\nFollow-up at the Heart Clinic, room 3, at 10:00.\nKidney function blood test at the hospital laboratory within 7 days.\nReturn to hospital at once for chest pain, trouble breathing or fainting.';
  const ibrahimNote = 'Discharge summary: Ibrahim Danjuma, Kestrel General Hospital.\nAmoxicillin 500 mg capsule, take as directed for 7 days.\nWound check at the Wound Clinic next week.\nReturn to hospital at once for high fever or spreading redness.';
  const graceNote = 'Discharge summary: Grace Bassey, Kestrel General Hospital.\nMetformin 500 mg tablet, one tablet twice daily with food at 08:00 and 20:00.\nReview at the Diabetes Clinic at 09:30.\nReturn to hospital at once for confusion or fainting.';
  const simpleNote = (name) => `Discharge summary: ${name}, Kestrel General Hospital.\nAmlodipine 5 mg tablet, one tablet every morning at 09:00 for 14 days.\nReview visit at Medical Outpatients.\nReturn to hospital at once for chest pain or trouble breathing.`;

  const lead = { id: 'u-ada', name: REVIEWER };
  const patients = [
    { id: 'p-zainab', name: 'Zainab Musa', age: 58, language: 'Hausa', literacy_level: 'basic', caregiver_mode: true, caregiver: { name: 'Hadiza Musa', relation: 'Daughter', scope: 'Reminders and help with tasks' }, phone_e164: '+2348000000101', email: 'zainab.musa@kestrelmail.ng', channels: ['web', 'voice', 'email'], contact_window: '08:00-11:00', pin_set: true, consent_at: at(-3, '09:00'), activation_status: 'active', assigned_to: lead },
    { id: 'p-tola', name: 'Tola Adeyemi', age: 44, language: 'Yoruba', literacy_level: 'standard', caregiver_mode: false, caregiver: null, phone_e164: '+2348000000102', email: 'tola.adeyemi@kestrelmail.ng', channels: ['web', 'email', 'voice'], contact_window: '16:00-19:00', pin_set: true, consent_at: at(-6, '14:00'), activation_status: 'active', assigned_to: lead },
    { id: 'p-chidi', name: 'Chidi Okeke', age: 63, language: 'Igbo', literacy_level: 'standard', caregiver_mode: false, caregiver: null, phone_e164: '+2348000000103', email: null, channels: [], contact_window: null, pin_set: false, consent_at: null, activation_status: 'invited', assigned_to: lead },
    { id: 'p-grace', name: 'Grace Bassey', age: 51, language: 'English', literacy_level: 'standard', caregiver_mode: false, caregiver: null, phone_e164: '+2348000000104', email: 'grace.bassey@kestrelmail.ng', channels: [], contact_window: null, pin_set: false, consent_at: null, activation_status: 'plan_review', assigned_to: lead },
    { id: 'p-ibrahim', name: 'Ibrahim Danjuma', age: 37, language: 'Hausa', literacy_level: 'basic', caregiver_mode: false, caregiver: null, phone_e164: '+2348000000105', email: null, channels: [], contact_window: null, pin_set: false, consent_at: null, activation_status: 'plan_review', assigned_to: lead }
  ];

  const plans = [
    {
      id: 'plan-zainab', patient_id: 'p-zainab', status: 'approved', clinician_approved_at: at(-3, '08:45'), approved_by: REVIEWER, source_note: zainabNote,
      verifier_issues: [],
      medications: [
        { name: 'Amlodipine 5 mg tablet', dose: '1 tablet', frequency: 'Every morning', times: ['08:00'], duration: '30 days', instructions: 'Take with water' },
        { name: 'Bisoprolol 5 mg tablet', dose: '1 tablet', frequency: 'Every evening', times: ['20:00'], duration: '30 days', instructions: 'Take with water' }
      ],
      appointments: [{ what: 'Cardiology follow-up', where: 'Heart Clinic, room 3', date: dateOnly(at(2, '10:00')), time: '10:00' }],
      tests: [{ name: 'Kidney function blood test', where: 'Hospital laboratory', date: dateOnly(at(4, '09:00')) }],
      symptoms_to_watch: ['Chest pain', 'Trouble breathing', 'Fainting'],
      reminder_times: ['08:00', '20:00']
    },
    {
      id: 'plan-tola', patient_id: 'p-tola', status: 'approved', clinician_approved_at: at(-6, '11:00'), approved_by: REVIEWER, source_note: simpleNote('Tola Adeyemi'),
      verifier_issues: [],
      medications: [{ name: 'Amlodipine 5 mg tablet', dose: '1 tablet', frequency: 'Every morning', times: ['09:00'], duration: '14 days', instructions: 'Take after breakfast' }],
      appointments: [{ what: 'Review visit', where: 'Medical Outpatients', date: dateOnly(at(0, '11:30')), time: '11:30' }],
      tests: [], symptoms_to_watch: ['Chest pain', 'Trouble breathing'], reminder_times: ['09:00']
    },
    {
      id: 'plan-chidi', patient_id: 'p-chidi', status: 'approved', clinician_approved_at: at(-1, '15:00'), approved_by: REVIEWER, source_note: simpleNote('Chidi Okeke'),
      verifier_issues: [],
      medications: [{ name: 'Amlodipine 5 mg tablet', dose: '1 tablet', frequency: 'Every morning', times: ['09:00'], duration: '14 days', instructions: 'Take after breakfast' }],
      appointments: [{ what: 'Review visit', where: 'Medical Outpatients', date: dateOnly(at(0, '14:00')), time: '14:00' }],
      tests: [], symptoms_to_watch: ['Chest pain', 'Trouble breathing'], reminder_times: ['09:00']
    },
    {
      id: 'plan-grace', patient_id: 'p-grace', status: 'needs_review', clinician_approved_at: null, approved_by: null, source_note: graceNote,
      verifier_issues: [{ field: 'appointments[0].date', issue: 'Visit date is missing from the note', severity: 'medium', source_text: 'Review at the Diabetes Clinic at 09:30.' }],
      medications: [{ name: 'Metformin 500 mg tablet', dose: '1 tablet', frequency: 'Twice daily with food', times: ['08:00', '20:00'], duration: '', instructions: 'Take with food' }],
      appointments: [{ what: 'Diabetes review', where: 'Diabetes Clinic', date: '', time: '09:30' }],
      tests: [], symptoms_to_watch: ['Confusion', 'Fainting'], reminder_times: ['08:00', '20:00']
    },
    {
      id: 'plan-ibrahim', patient_id: 'p-ibrahim', status: 'needs_review', clinician_approved_at: null, approved_by: null, source_note: ibrahimNote,
      verifier_issues: [
        { field: 'medications[0].frequency', issue: 'How often to take it is not stated', severity: 'high', source_text: 'take as directed' },
        { field: 'appointments[0].date', issue: '"Next week" is not an exact date', severity: 'medium', source_text: 'next week' }
      ],
      medications: [{ name: 'Amoxicillin 500 mg capsule', dose: '1 capsule', frequency: '', times: [], duration: '7 days', instructions: '' }],
      appointments: [{ what: 'Wound check', where: 'Wound Clinic', date: '', time: '' }],
      tests: [], symptoms_to_watch: ['High fever', 'Spreading redness'], reminder_times: []
    }
  ];

  const tasks = [
    { id: 't-z1', patient_id: 'p-zainab', type: 'medication', title: 'Amlodipine 5 mg tablet', detail: '1 tablet', due_at: at(0, '08:00'), criticality: 'high', status: 'patient_reported_done', last_reported_at: at(0, '08:20') },
    { id: 't-z2', patient_id: 'p-zainab', type: 'medication', title: 'Bisoprolol 5 mg tablet', detail: '1 tablet', due_at: at(-1, '20:00'), criticality: 'high', status: 'unable', last_reported_at: at(-1, '09:17') },
    { id: 't-z3', patient_id: 'p-zainab', type: 'medication', title: 'Bisoprolol 5 mg tablet', detail: '1 tablet', due_at: at(0, '20:00'), criticality: 'high', status: 'pending', last_reported_at: null },
    { id: 't-z4', patient_id: 'p-zainab', type: 'test', title: 'Kidney function blood test', detail: 'Hospital laboratory', due_at: at(4, '09:00'), criticality: 'medium', status: 'pending', last_reported_at: null },
    { id: 't-t1', patient_id: 'p-tola', type: 'medication', title: 'Amlodipine 5 mg tablet', detail: '1 tablet', due_at: at(0, '09:00'), criticality: 'high', status: 'overdue', last_reported_at: null },
    { id: 't-c1', patient_id: 'p-chidi', type: 'medication', title: 'Amlodipine 5 mg tablet', detail: '1 tablet', due_at: at(0, '09:00'), criticality: 'high', status: 'pending', last_reported_at: null }
  ];

  const appointments = [
    { id: 'a-z1', patient_id: 'p-zainab', what: 'Cardiology follow-up', where: 'Heart Clinic, room 3', starts_at: at(2, '10:00'), status: 'reschedule_requested', created_by: REVIEWER },
    { id: 'a-t1', patient_id: 'p-tola', what: 'Review visit', where: 'Medical Outpatients', starts_at: at(0, '11:30'), status: 'confirmed', created_by: REVIEWER },
    { id: 'a-c1', patient_id: 'p-chidi', what: 'Review visit', where: 'Medical Outpatients', starts_at: at(0, '14:00'), status: 'scheduled', created_by: REVIEWER },
    { id: 'a-i1', patient_id: 'p-ibrahim', what: 'Dressing change', where: 'Wound Clinic', starts_at: at(-1, '10:00'), status: 'scheduled', created_by: REVIEWER },
    { id: 'a-g1', patient_id: 'p-grace', what: 'Diabetes review', where: 'Diabetes Clinic', starts_at: at(5, '09:30'), status: 'scheduled', created_by: REVIEWER }
  ];

  const clinic_slots = [
    { id: 's-1', where: 'Heart Clinic, room 3', starts_at: at(3, '10:00'), capacity: 1, reserved_count: 0 },
    { id: 's-2', where: 'Heart Clinic, room 3', starts_at: at(3, '14:00'), capacity: 1, reserved_count: 0 },
    { id: 's-3', where: 'Heart Clinic, room 3', starts_at: at(4, '09:30'), capacity: 1, reserved_count: 1 },
    { id: 's-4', where: 'Heart Clinic, room 3', starts_at: at(6, '11:00'), capacity: 2, reserved_count: 0 }
  ];

  const reschedule_requests = [
    { id: 'rr-1', appointment_id: 'a-z1', patient_id: 'p-zainab', reason: 'Travel cost to the clinic on the booked day', original_text: 'Ba zan iya biyan kuɗin mota ranar ba.', channel: 'voice', requested_at: at(0, '09:20'), status: 'pending', reviewer: null }
  ];

  const barriers = [
    { id: 'b-z1', patient_id: 'p-zainab', task_id: 't-z2', type: 'stock', status: 'option_offered', attempts: 1, opened_at: at(-1, '09:17'), options: RESOURCES.stock },
    { id: 'b-t1', patient_id: 'p-tola', task_id: 't-t1', type: 'transport', status: 'open', attempts: 0, opened_at: at(0, '10:05'), options: [] }
  ];

  const ev = (patient_id, reported_at, actor_type, actor_id, source_channel, event_type, summary, verification_status, extra = {}) => ({ id: makeId('ev'), patient_id, reported_at, recorded_at: reported_at, actor_type, actor_id, source_channel, event_type, summary, verification_status, supersedes_event_id: null, ...extra });
  const events = [
    ev('p-zainab', at(-3, '08:30'), 'agent', 'Care Plan Agent', 'system', 'plan_drafted', 'Plan drafted from discharge note. 1 dose line flagged.', 'system_recorded'),
    ev('p-zainab', at(-3, '08:45'), 'clinician', REVIEWER, 'dashboard', 'plan_approved', 'Plan corrected and approved.', 'clinician_verified'),
    ev('p-zainab', at(-3, '09:00'), 'patient', 'Zainab Musa', 'clinic', 'consent_recorded', 'Agreed at the clinic to phone calls, email and chat in the app. PIN set.', 'clinician_verified'),
    ev('p-zainab', at(-1, '09:15'), 'system', 'Scheduler', 'voice', 'call_answered', 'Reminder call answered. Identity verified by PIN.', 'provider_status'),
    ev('p-zainab', at(-1, '09:17'), 'patient', 'Zainab Musa', 'voice', 'task_reported', 'Morning medicine reported as taken.', 'self_reported'),
    ev('p-zainab', at(-1, '09:17'), 'patient', 'Zainab Musa', 'voice', 'barrier_opened', 'Could not get the evening medicine.', 'self_reported'),
    ev('p-zainab', at(-1, '09:18'), 'agent', 'Barrier Resolution Agent', 'voice', 'barrier_option_offered', 'Possible pharmacy contact shared. Barrier not resolved.', 'system_recorded'),
    ev('p-zainab', at(-1, '09:19'), 'provider', 'Email provider', 'email', 'notification_delivered', 'Email with a pharmacy contact delivered.', 'provider_status'),
    ev('p-zainab', at(0, '08:05'), 'provider', 'Telephony provider', 'voice', 'call_unanswered', 'Reminder call not answered. Not treated as a missed dose.', 'provider_status'),
    ev('p-zainab', at(0, '08:20'), 'patient', 'Zainab Musa', 'web', 'task_reported', 'Morning medicine reported as taken.', 'self_reported'),
    ev('p-zainab', at(0, '09:20'), 'patient', 'Zainab Musa', 'voice', 'reschedule_requested', 'Asked to move the cardiology visit because of travel cost.', 'self_reported'),
    ev('p-zainab', at(0, '09:24'), 'system', 'Safety engine', 'voice', 'escalation_created', 'Possible emergency phrase. Escalation created and care team notified.', 'system_recorded'),
    ev('p-tola', at(-6, '11:00'), 'clinician', REVIEWER, 'dashboard', 'plan_approved', 'Plan approved.', 'clinician_verified'),
    ev('p-tola', at(-2, '17:10'), 'patient', 'Tola Adeyemi', 'browser_voice', 'task_reported', 'Morning medicine reported as taken.', 'self_reported'),
    ev('p-tola', at(-1, '16:30'), 'provider', 'Email provider', 'email', 'notification_delivered', 'Medicine reminder email delivered.', 'provider_status'),
    ev('p-tola', at(0, '10:05'), 'patient', 'Tola Adeyemi', 'web', 'barrier_opened', 'Said transport to the clinic is a problem.', 'self_reported'),
    ev('p-tola', at(0, '10:30'), 'system', 'Safety engine', 'system', 'escalation_created', 'Critical medicine task overdue. Escalation created.', 'system_recorded'),
    ev('p-chidi', at(-1, '15:00'), 'clinician', REVIEWER, 'dashboard', 'plan_approved', 'Plan approved. Invite sent by text message.', 'clinician_verified'),
    ev('p-grace', at(0, '07:50'), 'agent', 'Plan Verifier Agent', 'system', 'plan_drafted', 'Plan drafted. 1 field needs review.', 'system_recorded'),
    ev('p-ibrahim', at(0, '08:10'), 'agent', 'Plan Verifier Agent', 'system', 'plan_drafted', 'Plan drafted. 2 fields need review.', 'system_recorded')
  ];

  const turn = (speaker, transcript, extra = {}) => ({ speaker, transcript, english: extra.english || null, confidence: extra.confidence ?? null, confirmed: extra.confirmed ?? null, keypad: extra.keypad || null });
  const calls = [
    {
      id: 'c-1', patient_id: 'p-zainab', direction: 'outbound', channel: 'phone', status: 'completed', verification_state: 'verified', language: 'Hausa', started_at: at(-1, '09:15'), ended_at: at(-1, '09:19'), outcome: 'Task reported, barrier opened',
      turns: [
        turn('tomi', 'Hello, this is Tomi, an automated assistant from your care team. To keep your details private, please enter your PIN.'),
        turn('patient', 'PIN entered', { keypad: true, confirmed: true }),
        turn('tomi', 'Thank you, Zainab. Your morning medicine was due at 08:00. Did you take it?'),
        turn('patient', 'Na sha na safe, amma ban samu ɗayan maganin ba.', { english: 'I took the morning one but could not get the other medicine.', confidence: 0.86 }),
        turn('tomi', 'I heard that you took the morning medicine, and you could not get the evening medicine. Is that right?'),
        turn('patient', 'Eh.', { english: 'Yes.', confidence: 0.95, confirmed: true }),
        turn('tomi', 'Thank you. Your care team shared a possible pharmacy contact. I will send it by text. Stock is not guaranteed.')
      ]
    },
    { id: 'c-2', patient_id: 'p-zainab', direction: 'outbound', channel: 'phone', status: 'failed', verification_state: 'not_reached', language: 'Hausa', started_at: at(0, '08:05'), ended_at: at(0, '08:06'), outcome: 'No answer', turns: [] },
    {
      id: 'c-3', patient_id: 'p-zainab', direction: 'inbound', channel: 'phone', status: 'completed', verification_state: 'verified', language: 'Hausa', started_at: at(0, '09:18'), ended_at: at(0, '09:25'), outcome: 'Reschedule requested, escalation created',
      turns: [
        turn('tomi', 'Hello, this is Tomi, an automated assistant from your care team. Please enter your PIN.'),
        turn('patient', 'PIN entered', { keypad: true, confirmed: true }),
        turn('patient', 'Ba zan iya biyan kuɗin mota ranar ba.', { english: 'I cannot pay for transport on that day.', confidence: 0.81 }),
        turn('tomi', 'I can ask the clinic for a new time. Your current visit stays booked until the clinic confirms. Shall I ask?'),
        turn('patient', 'Eh.', { english: 'Yes.', confidence: 0.94, confirmed: true }),
        turn('patient', 'Ƙirjina yana ciwo, kuma numfashi yana min wuya.', { english: 'My chest hurts and it is hard to breathe.', confidence: 0.71 }),
        turn('tomi', 'This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team.')
      ]
    },
    {
      id: 'c-4', patient_id: 'p-tola', direction: 'browser', channel: 'browser_voice', status: 'completed', verification_state: 'verified', language: 'Yoruba', started_at: at(-2, '17:08'), ended_at: at(-2, '17:11'), outcome: 'Task reported',
      turns: [
        turn('tomi', 'Hello Tola, this is Tomi. Did you take your morning medicine today?'),
        turn('patient', 'Bẹ́ẹ̀ni, mo ti lò ó.', { english: 'Yes, I have taken it.', confidence: 0.9 }),
        turn('tomi', 'I heard that you took it. Is that right?'),
        turn('patient', 'Bẹ́ẹ̀ni.', { english: 'Yes.', confidence: 0.96, confirmed: true }),
        turn('tomi', 'Thank you. I have noted it.')
      ]
    }
  ];

  const escalationHistory = (entries) => entries.map(([status, time, by]) => ({ status, at: time, by: by || null }));
  const escalations = [
    {
      id: 'e-1', patient_id: 'p-zainab', rule_id: 'possible_chest_pain', rule_label: 'Possible emergency phrase', severity: 'red', status: 'delivered', channel: 'voice', call_id: 'c-3',
      original_text: 'Ƙirjina yana ciwo, kuma numfashi yana min wuya.', english_text: 'My chest hurts and it is hard to breathe.', confidence: 0.71,
      brief: 'During an inbound call at 09:24 the patient said, in Hausa, that her chest hurts and breathing is hard (speech confidence 0.71). Approved emergency guidance was given. Open items: evening medicine not obtained since yesterday (barrier open); appointment move requested for travel cost.', brief_ready: true,
      outstanding: 'Evening medicine barrier open. Appointment move pending.', created_at: at(0, '09:24'),
      history: escalationHistory([['created', at(0, '09:24')], ['notification_attempted', at(0, '09:24')], ['delivered', at(0, '09:25')]]), note: null
    },
    {
      id: 'e-2', patient_id: 'p-tola', rule_id: 'missed_critical_task', rule_label: 'Critical medicine overdue', severity: 'amber', status: 'acknowledged', channel: 'system', call_id: null,
      original_text: 'Ọkọ̀ ò rọrùn láti rí.', english_text: 'Transport is hard to find.', confidence: 0.88,
      brief: 'Morning medicine due 09:00 has no report. Patient reported a transport problem at 10:05 in web chat.', brief_ready: true,
      outstanding: 'Morning medicine not reported.', created_at: at(0, '10:30'),
      history: escalationHistory([['created', at(0, '10:30')], ['notification_attempted', at(0, '10:30')], ['delivered', at(0, '10:31')], ['acknowledged', at(0, '10:40'), REVIEWER]]), note: null
    },
    {
      id: 'e-3', patient_id: 'p-chidi', rule_id: 'barrier_unresolved', rule_label: 'Barrier not resolved after 2 attempts', severity: 'amber', status: 'resolved', channel: 'web', call_id: null,
      original_text: 'Enweghị m ego ịzụta ọgwụ.', english_text: 'I do not have money to buy the medicine.', confidence: 0.9,
      brief: 'Patient reported cost barrier twice. Two support options offered; neither confirmed.', brief_ready: true,
      outstanding: 'None.', created_at: at(-4, '12:00'),
      history: escalationHistory([['created', at(-4, '12:00')], ['delivered', at(-4, '12:01')], ['acknowledged', at(-4, '12:30'), REVIEWER], ['resolved', at(-4, '15:00'), REVIEWER]]), note: 'Hospital social worker arranged help with the cost of medicine.'
    }
  ];

  const messages = [
    { id: 'm-1', patient_id: 'p-zainab', direction: 'careloop', channel: 'web', original_text: 'Good morning, Zainab. It is time for your morning medicine: Amlodipine 5 mg tablet, 1 tablet.', language: 'Hausa', created_at: at(0, '08:00'), task_id: 't-z1', number_check_passed: true, answered: true },
    { id: 'm-2', patient_id: 'p-zainab', direction: 'patient', channel: 'web', original_text: 'Done', language: 'Hausa', created_at: at(0, '08:20') },
    { id: 'm-3', patient_id: 'p-zainab', direction: 'careloop', channel: 'web', original_text: 'Thank you. I have noted that you took it.', language: 'Hausa', created_at: at(0, '08:20'), number_check_passed: true }
  ];

  const data = { patients, plans, tasks, appointments, clinic_slots, reschedule_requests, barriers, events, calls, escalations, messages, notifications: [], voice_sessions: [] };
  keepHistoryInThePast(data);

  // Messages already sent, with provider outcomes. The scheduler adds the upcoming ones.
  const zainab = patients[0];
  const tola = patients[1];
  const sent = (patient, fields, deliveredAfterMin = 1) => {
    const message = queueMessage(data, patient, { created_by: 'Reminder scheduler', ...fields, status: fields.status || 'delivered' });
    message.sent_at = message.scheduled_for;
    if (message.status === 'delivered') message.delivered_at = new Date(new Date(message.scheduled_for).getTime() + deliveredAfterMin * 60000).toISOString();
    return message;
  };
  const yesterdayEvening = tasks.find((task) => task.id === 't-z2');
  sent(zainab, { channel: 'email', template: 'medicine', task_id: 't-z2', scheduled_for: new Date(new Date(yesterdayEvening.due_at).getTime() - 30 * 60000).toISOString(), status: 'failed', failure_reason: 'Not delivered. The mailbox was full. Check the address with the patient.' });
  sent(zainab, { channel: 'email', template: 'support', created_by: 'Barrier Resolution Agent', scheduled_for: events.find((event) => event.event_type === 'notification_delivered').reported_at });
  const missed = calls.find((call) => call.id === 'c-2');
  sent(zainab, { channel: 'email', template: 'missed_call', created_by: 'Reminder scheduler', scheduled_for: new Date(new Date(missed.ended_at).getTime() + 2 * 60000).toISOString() });
  const morning = tasks.find((task) => task.id === 't-z1');
  sent(zainab, { channel: 'email', template: 'medicine', task_id: 't-z1', scheduled_for: new Date(new Date(morning.due_at).getTime() - 30 * 60000).toISOString() });
  sent(tola, { channel: 'email', template: 'medicine', scheduled_for: events.find((event) => event.actor_id === 'Email provider').reported_at }, 2);
  patients.forEach((patient) => scheduleReminders(data, patient));
  return data;
}

// Seed times are written as clock times ("today at 09:24"). Early in the morning some of those are still in the
// future, which would read as "raised in 9 h". Anything that already happened is moved back a day instead.
function keepHistoryInThePast(data) {
  const now = new Date().toISOString();
  const back = (iso) => (iso && iso > now ? new Date(new Date(iso).getTime() - 86400000).toISOString() : iso);
  const backAll = (item, keys) => keys.forEach((key) => { item[key] = back(item[key]); });
  data.events.forEach((event) => backAll(event, ['reported_at', 'recorded_at']));
  data.messages.forEach((message) => backAll(message, ['created_at']));
  data.barriers.forEach((barrier) => backAll(barrier, ['opened_at']));
  data.reschedule_requests.forEach((request) => backAll(request, ['requested_at']));
  data.calls.forEach((call) => { if (call.started_at > now) { call.started_at = back(call.started_at); call.ended_at = call.ended_at && new Date(new Date(call.ended_at).getTime() - 86400000).toISOString(); } });
  data.escalations.forEach((escalation) => {
    if (escalation.created_at <= now) return;
    escalation.created_at = back(escalation.created_at);
    escalation.history.forEach((entry) => { entry.at = new Date(new Date(entry.at).getTime() - 86400000).toISOString(); });
  });
  data.tasks.forEach((task) => {
    if (task.status === 'pending' || task.due_at <= now) return;
    task.due_at = back(task.due_at);
    task.last_reported_at = task.last_reported_at && (task.last_reported_at > now ? back(task.last_reported_at) : task.last_reported_at);
  });
  data.plans.forEach((plan) => backAll(plan, ['clinician_approved_at']));
  data.patients.forEach((patient) => backAll(patient, ['consent_at']));
}

/* ---------- storage ---------- */

let db = load();

function load() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const data = JSON.parse(stored);
      FACILITY = data.facility || DEFAULT_FACILITY;
      return data;
    }
  } catch { /* fall through to a fresh seed */ }
  const fresh = seed();
  persist(fresh);
  return fresh;
}

function persist(data = db) {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch { /* storage full or blocked; keep in memory */ }
}

const clone = (value) => JSON.parse(JSON.stringify(value));
const wait = (ms = 220) => new Promise((resolve) => window.setTimeout(resolve, ms + Math.random() * 180));

async function respond(value, ms) {
  await wait(ms);
  persist();
  return clone(value);
}

function notFound(what) {
  const error = new Error(`${what} was not found.`);
  error.status = 404;
  throw error;
}

const findPatient = (id) => db.patients.find((patient) => patient.id === id) || notFound('Patient');
const patientName = (id) => db.patients.find((patient) => patient.id === id)?.name || id;

const CHANNEL_WORDS = { web: 'chat in the app', voice: 'phone calls', sms: 'text messages', email: 'email' };
function channelList(channels) {
  const words = channels.map((channel) => CHANNEL_WORDS[channel] || channel);
  return words.length > 1 ? `${words.slice(0, -1).join(', ')} and ${words.at(-1)}` : words[0] || 'nothing';
}

// Stand-in for the Care Plan Agent: picks up the first line that names a dose. The real agent fills every field.
function draftMedicine(note) {
  const line = note.split(/\r?\n/).find((item) => /\d+\s*(mg|ml|mcg|g)\b/i.test(item));
  return line ? line.split(',')[0].trim() : '';
}

function logEvent(patientId, fields) {
  const event = { id: makeId('ev'), patient_id: patientId, reported_at: nowIso(), recorded_at: nowIso(), supersedes_event_id: null, ...fields };
  db.events.push(event);
  return event;
}

/* ---------- classification shared by chat and voice ---------- */

function classify(text) {
  const lower = text.toLowerCase();
  if (RED_FLAG_TERMS.some((term) => lower.includes(term))) return { kind: 'red_flag' };
  for (const [type, terms] of Object.entries(BARRIER_TERMS)) if (terms.some((term) => lower.includes(term))) return { kind: 'barrier', type };
  if (/(appointment|visit|reschedule|new time|change.*time)/.test(lower)) return { kind: 'reschedule' };
  if (/^(done|yes|i took|took it|i have taken|eh|bẹ́ẹ̀ni|ee)/.test(lower) || lower.includes('took')) return { kind: 'done' };
  if (/not yet|later|no\b/.test(lower)) return { kind: 'not_yet' };
  if (/problem/.test(lower)) return { kind: 'problem' };
  return { kind: 'other' };
}

function nextOpenTask(patientId) {
  return db.tasks
    .filter((task) => task.patient_id === patientId && ['pending', 'overdue'].includes(task.status))
    .sort((first, second) => first.due_at.localeCompare(second.due_at))[0] || null;
}

function createEscalation(patient, text, channel, callId = null, confidence = null) {
  const escalation = {
    id: makeId('e'), patient_id: patient.id, rule_id: 'possible_red_flag_phrase', rule_label: 'Possible emergency phrase', severity: 'red', status: 'delivered', channel, call_id: callId,
    original_text: text, english_text: text, confidence, brief: null, brief_ready: false, briefDueAt: Date.now() + 4000,
    outstanding: describeOutstanding(patient.id), created_at: nowIso(),
    history: [{ status: 'created', at: nowIso(), by: null }, { status: 'notification_attempted', at: nowIso(), by: null }, { status: 'delivered', at: nowIso(), by: null }], note: null
  };
  db.escalations.push(escalation);
  logEvent(patient.id, { actor_type: 'system', actor_id: 'Safety engine', source_channel: channel, event_type: 'escalation_created', summary: 'Possible emergency phrase. Escalation created and care team notified.', verification_status: 'system_recorded' });
  return escalation;
}

function describeOutstanding(patientId) {
  const openBarriers = db.barriers.filter((barrier) => barrier.patient_id === patientId && !barrier.status.startsWith('resolved')).length;
  const pendingMoves = db.reschedule_requests.filter((request) => request.patient_id === patientId && request.status === 'pending').length;
  const parts = [];
  if (openBarriers) parts.push(`${openBarriers} open barrier${openBarriers > 1 ? 's' : ''}`);
  if (pendingMoves) parts.push('appointment move pending');
  return parts.length ? `${parts.join(', ')}.` : 'None recorded.';
}

function openBarrier(patient, type, channel) {
  const task = nextOpenTask(patient.id);
  let barrier = db.barriers.find((item) => item.patient_id === patient.id && item.type === type && !item.status.startsWith('resolved'));
  if (!barrier) {
    barrier = { id: makeId('b'), patient_id: patient.id, task_id: task?.id || null, type, status: 'open', attempts: 0, opened_at: nowIso(), options: [] };
    db.barriers.push(barrier);
  }
  barrier.attempts += 1;
  barrier.options = JSON.parse(JSON.stringify(RESOURCES[type] || RESOURCES.understanding)
    .replaceAll(DEFAULT_FACILITY, FACILITY).replaceAll(`${shortFacility(DEFAULT_FACILITY)} `, `${shortFacility(FACILITY)} `));
  barrier.status = 'option_offered';
  logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: channel, event_type: 'barrier_opened', summary: `Reported a ${type} problem.`, verification_status: 'self_reported' });
  logEvent(patient.id, { actor_type: 'agent', actor_id: 'Barrier Resolution Agent', source_channel: channel, event_type: 'barrier_option_offered', summary: 'Possible support option shared. Barrier not resolved.', verification_status: 'system_recorded' });
  const supportChannel = messageChannel(patient);
  if (supportChannel) queueMessage(db, patient, { channel: supportChannel, template: 'support', created_by: 'Barrier Resolution Agent' });
  return barrier;
}

function requestReschedule(patient, reason, channel, originalText) {
  const appointment = db.appointments
    .filter((item) => item.patient_id === patient.id && ['scheduled', 'confirmed'].includes(item.status) && item.starts_at > nowIso())
    .sort((first, second) => first.starts_at.localeCompare(second.starts_at))[0];
  if (!appointment) return null;
  appointment.status = 'reschedule_requested';
  const request = { id: makeId('rr'), appointment_id: appointment.id, patient_id: patient.id, reason, original_text: originalText, channel, requested_at: nowIso(), status: 'pending', reviewer: null };
  db.reschedule_requests.push(request);
  logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: channel, event_type: 'reschedule_requested', summary: 'Asked for a new appointment time.', verification_status: 'self_reported' });
  return { request, appointment };
}

function reportTask(patient, task, status, channel) {
  if (!task) return;
  task.status = status === 'done' ? 'patient_reported_done' : status === 'unable' ? 'unable' : task.status;
  task.last_reported_at = nowIso();
  const summaries = { done: `${task.title}: reported as done.`, not_yet: `${task.title}: reported as not yet done.`, unable: `${task.title}: reported as not possible.` };
  logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: channel, event_type: 'task_reported', summary: summaries[status], verification_status: 'self_reported', target_id: task.id });
  if (status === 'done') cancelMessages(patient.id, (item) => item.task_id === task.id, 'Not needed. The patient already reported it done.');
}

/* ---------- chat ---------- */

function chatReply(patient, payload) {
  const text = payload.original_text.trim();
  const task = payload.task_id ? db.tasks.find((item) => item.id === payload.task_id) : nextOpenTask(patient.id);
  const quick = payload.quick_reply;
  const result = { reply: null, barrier: null, escalation: null, reschedule: null };
  const kind = quick || classify(text).kind;
  if (kind === 'red_flag') {
    result.escalation = { ...createEscalation(patient, text, 'web'), call_number: SUPPORT.emergency_number };
    result.reply = 'This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team.';
  } else if (kind === 'barrier' || ['cost', 'transport', 'stock', 'understanding'].includes(kind)) {
    const type = ['cost', 'transport', 'stock', 'understanding'].includes(kind) ? kind : classify(text).type;
    result.barrier = openBarrier(patient, type, 'web');
    result.reply = 'Thank you for telling me. Here is an option your care team shared. Please tell me if it worked.';
  } else if (kind === 'reschedule') {
    const moved = requestReschedule(patient, text, 'web', text);
    result.reschedule = moved;
    result.reply = moved ? 'I have asked the clinic for a new time. Your current visit stays booked until the clinic confirms a new one.' : 'You have no upcoming visit to move. Your care team can help.';
  } else if (kind === 'done') {
    reportTask(patient, task, 'done', 'web');
    result.reply = 'Thank you. I have noted that you took it.';
  } else if (kind === 'not_yet') {
    reportTask(patient, task, 'not_yet', 'web');
    result.reply = 'Okay. I will remind you again later.';
  } else if (kind === 'worked') {
    const barrier = db.barriers.find((item) => item.patient_id === patient.id && item.status === 'option_offered');
    if (barrier) barrier.status = 'resolved_patient_reported';
    logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'barrier_resolved', summary: 'Said the support option worked.', verification_status: 'self_reported' });
    result.reply = 'I am glad it helped. I have noted it.';
  } else if (kind === 'did_not_work') {
    const barrier = db.barriers.find((item) => item.patient_id === patient.id && item.status === 'option_offered');
    if (barrier) barrier.status = barrier.attempts >= 2 ? 'escalated' : 'awaiting_response';
    logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'barrier_update', summary: 'Said the support option did not work.', verification_status: 'self_reported' });
    result.reply = 'Thank you for telling me. I have told your care team so they can help.';
  } else {
    result.reply = 'Thank you. Your message has been received. Your care team can see it.';
  }
  return result;
}

/* ---------- voice dialog (browser voice and simulated calls share it) ---------- */

const KEYPAD = {
  verify: [],
  task: [{ key: '1', label: 'Yes, I did' }, { key: '2', label: 'Not yet' }, { key: '3', label: 'I have a problem' }],
  confirm: [{ key: '1', label: 'Yes, that is right' }, { key: '2', label: 'No' }],
  menu: [{ key: '1', label: 'Report a problem' }, { key: '2', label: 'My next visit' }, { key: '3', label: 'End' }],
  reschedule: [{ key: '1', label: 'Yes, ask for a new time' }, { key: '2', label: 'No' }]
};

function voiceSay(session, text, state, extra = {}) {
  session.state = state;
  const turn = { speaker: 'tomi', transcript: text, at: nowIso() };
  session.turns.push(turn);
  return { turns: [turn], state, keypad: KEYPAD[state] || [], ended: state === 'ended', ...extra };
}

function taskQuestion(task) {
  if (!task) return 'You have nothing due right now.';
  const time = new Date(task.due_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return task.type === 'medication'
    ? `Your medicine ${task.title}, ${task.detail}, is due at ${time}. Have you taken it? Press 1 for yes, 2 for not yet, or 3 for a problem.`
    : `${task.title} is due. Have you done it? Press 1 for yes, 2 for not yet, or 3 for a problem.`;
}

function voiceTurn(session, input) {
  const patient = findPatient(session.patient_id);
  const raw = (input?.transcript || '').trim();
  const digit = input?.digit || null;
  const confidence = input?.confidence ?? (digit ? 1 : 0.9);
  if (raw || digit) session.turns.push({ speaker: 'patient', transcript: digit ? `Pressed ${digit}` : raw, confidence, keypad: Boolean(digit), at: nowIso() });

  if (session.state === 'greeting') {
    return voiceSay(session, 'Hello, this is Tomi, an automated assistant from your care team. To keep your details private, please enter your 4-digit PIN.', 'verify', { pin_required: true });
  }
  if (session.state === 'verify') {
    const expectedPin = patient.pin_mock || DEMO_PIN;
    if (raw === expectedPin || input?.pin === expectedPin) {
      session.verified = true;
      session.task_id = nextOpenTask(patient.id)?.id || null;
      return voiceSay(session, `Thank you, ${patient.name.split(' ')[0]}. ${taskQuestion(nextOpenTask(patient.id))}`, session.task_id ? 'task' : 'menu');
    }
    session.pin_attempts = (session.pin_attempts || 0) + 1;
    if (session.pin_attempts >= 3) {
      logEvent(patient.id, { actor_type: 'system', actor_id: 'Tomi', source_channel: session.channel, event_type: 'verification_failed', summary: 'Identity not verified after 3 PIN attempts. No details shared.', verification_status: 'system_recorded' });
      return voiceSay(session, 'I could not confirm who you are, so I cannot share details. Please contact your care team. Goodbye.', 'ended');
    }
    return voiceSay(session, 'That PIN did not match. Please try again.', 'verify', { pin_required: true });
  }

  const intent = digit ? null : classify(raw);
  if (intent?.kind === 'red_flag' || (!digit && confidence < 0.6 && RED_FLAG_TERMS.some((term) => raw.toLowerCase().includes(term)))) {
    const escalation = createEscalation(patient, raw, session.channel, session.id, confidence);
    session.escalation_id = escalation.id;
    return voiceSay(session, 'This may need urgent care. Please go to the nearest hospital now, or call 112. I have sent this to your care team.', 'ended', { escalation: { id: escalation.id, call_number: SUPPORT.emergency_number } });
  }
  if (!digit && confidence < 0.6) return voiceSay(session, 'I am not sure I understood. Please say it again, or use the keypad.', session.state);

  if (session.state === 'task') {
    const choice = digit || (intent.kind === 'done' ? '1' : intent.kind === 'not_yet' ? '2' : intent.kind === 'barrier' || intent.kind === 'problem' ? '3' : null);
    if (choice === '1') { session.pending = 'done'; return voiceSay(session, 'I heard that you took it. Is that right? Press 1 for yes, or 2 for no.', 'confirm'); }
    if (choice === '2') { reportTask(patient, db.tasks.find((task) => task.id === session.task_id), 'not_yet', session.channel); return voiceSay(session, 'Okay. I will remind you again later. Is there anything else? Press 1 to report a problem, 2 for your next visit, or 3 to end.', 'menu'); }
    if (choice === '3') {
      const barrier = openBarrier(patient, intent?.type || 'stock', session.channel);
      const option = barrier.options[0];
      return voiceSay(session, `Thank you for telling me. Your care team shared this option: ${option.name}, ${option.distance}. Phone ${option.phone}. ${option.note} Is there anything else? Press 1 to report a problem, 2 for your next visit, or 3 to end.`, 'menu', { barrier });
    }
    if (intent?.kind === 'reschedule') return startReschedule(session, patient);
    return voiceSay(session, 'I did not catch that. Press 1 for yes, 2 for not yet, or 3 for a problem.', 'task');
  }
  if (session.state === 'confirm') {
    const yes = digit === '1' || intent?.kind === 'done';
    if (yes) {
      reportTask(patient, db.tasks.find((task) => task.id === session.task_id), 'done', session.channel);
      return voiceSay(session, 'Thank you. I have noted it. Is there anything else? Press 1 to report a problem, 2 for your next visit, or 3 to end.', 'menu');
    }
    return voiceSay(session, `Okay, let us try again. ${taskQuestion(db.tasks.find((task) => task.id === session.task_id))}`, 'task');
  }
  if (session.state === 'reschedule') {
    if (digit === '1' || intent?.kind === 'done') {
      const moved = requestReschedule(patient, 'Asked by voice for a new time', session.channel, raw || 'Pressed 1');
      return voiceSay(session, moved ? 'I have asked the clinic for a new time. Your current visit stays booked until the clinic confirms. Goodbye for now.' : 'You have no upcoming visit to move. Goodbye for now.', 'ended');
    }
    return voiceSay(session, 'Okay. Your visit stays as it is. Is there anything else? Press 1 to report a problem, 2 for your next visit, or 3 to end.', 'menu');
  }
  // menu
  if (digit === '1' || intent?.kind === 'barrier' || intent?.kind === 'problem') {
    const barrier = openBarrier(patient, intent?.type || 'understanding', session.channel);
    const option = barrier.options[0];
    return voiceSay(session, `Thank you. Your care team shared this option: ${option.name}. Phone ${option.phone}. ${option.note} Is there anything else? Press 2 for your next visit, or 3 to end.`, 'menu', { barrier });
  }
  if (digit === '2' || intent?.kind === 'reschedule') return startReschedule(session, patient);
  if (digit === '3') return voiceSay(session, 'Thank you for talking with me. Goodbye.', 'ended');
  return voiceSay(session, 'I did not catch that. Press 1 to report a problem, 2 for your next visit, or 3 to end.', 'menu');
}

function startReschedule(session, patient) {
  const appointment = db.appointments.filter((item) => item.patient_id === patient.id && item.starts_at > nowIso() && item.status !== 'cancelled').sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  if (!appointment) return voiceSay(session, 'You have no upcoming visit booked. Is there anything else? Press 1 to report a problem, or 3 to end.', 'menu');
  const when = new Date(appointment.starts_at).toLocaleString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
  if (appointment.status === 'reschedule_requested') return voiceSay(session, `Your visit is ${appointment.what} at ${appointment.where}, ${when}. You already asked for a new time. The clinic will confirm. Is there anything else? Press 1 to report a problem, or 3 to end.`, 'menu');
  return voiceSay(session, `Your next visit is ${appointment.what} at ${appointment.where}, ${when}. Do you want to ask for a new time? Press 1 for yes, or 2 for no.`, 'reschedule');
}

function closeVoiceSession(session) {
  if (session.closed) return;
  session.closed = true;
  const patient = findPatient(session.patient_id);
  const call = {
    id: makeId('c'), patient_id: patient.id, direction: session.channel === 'browser_voice' ? 'browser' : 'inbound', channel: session.channel, status: 'completed',
    verification_state: session.verified ? 'verified' : 'unverified', language: patient.language, started_at: session.started_at, ended_at: nowIso(),
    outcome: session.escalation_id ? 'Escalation created' : session.verified ? 'Check-in completed' : 'Not verified',
    turns: session.turns.map(({ speaker, transcript, confidence, keypad }) => ({ speaker, transcript, english: null, confidence: confidence ?? null, confirmed: null, keypad: keypad || null }))
  };
  db.calls.push(call);
  logEvent(patient.id, { actor_type: 'system', actor_id: 'Tomi', source_channel: session.channel, event_type: 'call_completed', summary: `${session.channel === 'browser_voice' ? 'Browser voice session' : 'Call'} ended. ${call.outcome}.`, verification_status: 'provider_status' });
}

/* ---------- simulated phone calls with live status ---------- */

function outboundScript(patient) {
  const task = nextOpenTask(patient.id);
  const steps = [
    { t: 0, status: 'initiated' },
    { t: 2500, status: 'ringing' },
    { t: 6000, status: 'answered' },
    { t: 7000, turn: { speaker: 'tomi', transcript: 'Hello, this is Tomi, an automated assistant from your care team. To keep your details private, please enter your PIN.' } },
    { t: 10000, status: 'verified', verification_state: 'verified', turn: { speaker: 'patient', transcript: 'PIN entered', keypad: true, confirmed: true } },
    { t: 11500, turn: { speaker: 'tomi', transcript: `Thank you. ${taskQuestion(task)}` } },
    { t: 15000, turn: { speaker: 'patient', transcript: 'Yes, I took it.', confidence: 0.92 } },
    { t: 16500, turn: { speaker: 'tomi', transcript: 'I heard that you took it. Is that right?' } },
    { t: 19000, turn: { speaker: 'patient', transcript: 'Pressed 1', keypad: true, confirmed: true } },
    { t: 20500, turn: { speaker: 'tomi', transcript: 'Thank you. I have noted it. Goodbye.' } },
    { t: 22500, status: 'completed', outcome: task ? 'Task reported' : 'Check-in completed', report_task_id: task?.id || null }
  ];
  return steps;
}

function inboundScript() {
  return [
    { t: 0, status: 'ringing' },
    { t: 2000, status: 'answered' },
    { t: 3000, turn: { speaker: 'tomi', transcript: 'Hello, this is Tomi, an automated assistant from your care team. Please enter your PIN.' } },
    { t: 6000, status: 'verified', verification_state: 'verified', turn: { speaker: 'patient', transcript: 'PIN entered', keypad: true, confirmed: true } },
    { t: 7500, turn: { speaker: 'tomi', transcript: 'You can press 1 for your tasks, 2 to report a problem, 3 for your visits, or 4 for your care team.' } },
    { t: 10500, turn: { speaker: 'patient', transcript: 'Pressed 3', keypad: true } },
    { t: 12000, turn: { speaker: 'tomi', transcript: 'Your next visit is booked. I will send the details by text.' } },
    { t: 14500, status: 'completed', outcome: 'Visit details requested' }
  ];
}

function advanceCall(call) {
  if (!call.script) return call;
  const elapsed = Date.now() - call.script_started;
  while (call.script_index < call.script.length && call.script[call.script_index].t <= elapsed) {
    const step = call.script[call.script_index];
    if (step.status) call.status = step.status;
    if (step.verification_state) call.verification_state = step.verification_state;
    if (step.turn) call.turns.push({ english: null, confidence: null, confirmed: null, keypad: null, ...step.turn });
    if (step.status === 'answered') logEvent(call.patient_id, { actor_type: 'provider', actor_id: 'Telephony provider', source_channel: 'voice', event_type: 'call_answered', summary: `${call.direction === 'outbound' ? 'Outbound' : 'Inbound'} call answered.`, verification_status: 'provider_status' });
    if (step.status === 'completed') {
      call.ended_at = nowIso();
      call.outcome = step.outcome;
      const patient = findPatient(call.patient_id);
      if (step.report_task_id) reportTask(patient, db.tasks.find((task) => task.id === step.report_task_id), 'done', 'voice');
      logEvent(call.patient_id, { actor_type: 'system', actor_id: 'Tomi', source_channel: 'voice', event_type: 'call_completed', summary: `Call completed. ${step.outcome}.`, verification_status: 'provider_status' });
    }
    call.script_index += 1;
  }
  if (call.script_index >= call.script.length) { delete call.script; delete call.script_started; delete call.script_index; }
  return call;
}

// Stand-in for the SMS and email providers: due messages are sent, then report delivery a few seconds later.
function advanceMessages() {
  const now = Date.now();
  db.notifications.forEach((message) => {
    if (message.status === 'scheduled' && new Date(message.scheduled_for).getTime() <= now) {
      const patient = db.patients.find((item) => item.id === message.patient_id);
      if (!patient.channels.includes(message.channel)) { message.status = 'cancelled'; message.failure_reason = 'Not sent. The patient turned this channel off.'; return; }
      message.status = 'sent';
      message.sent_at = new Date().toISOString();
      message.deliver_at = now + 5000;
    }
    if (message.status === 'sent' && message.deliver_at && message.deliver_at <= now) {
      message.status = 'delivered';
      message.delivered_at = new Date().toISOString();
      delete message.deliver_at;
      logEvent(message.patient_id, { actor_type: 'provider', actor_id: message.channel === 'sms' ? 'SMS provider' : 'Email provider', source_channel: message.channel, event_type: 'notification_delivered', summary: `${message.title} ${message.channel === 'sms' ? 'text' : 'email'} delivered.`, verification_status: 'provider_status' });
    }
  });
}

function advanceAll() {
  advanceMessages();
  db.calls.forEach(advanceCall);
  db.escalations.forEach((escalation) => {
    if (!escalation.brief_ready && escalation.briefDueAt && Date.now() >= escalation.briefDueAt) {
      escalation.brief = `The patient wrote or said: "${escalation.original_text}". Approved emergency guidance was given. Open items: ${escalation.outstanding}`;
      escalation.brief_ready = true;
      delete escalation.briefDueAt;
    }
  });
}

/* ---------- derived views ---------- */

function patientSummary(patient) {
  const plan = db.plans.find((item) => item.patient_id === patient.id);
  const tasks = db.tasks.filter((task) => task.patient_id === patient.id);
  const lastEvent = db.events.filter((event) => event.patient_id === patient.id && event.actor_type !== 'clinician').sort((a, b) => b.reported_at.localeCompare(a.reported_at))[0];
  return {
    ...patient,
    plan_status: plan?.status || 'not_created',
    open_tasks: tasks.filter((task) => ['pending', 'overdue', 'unable'].includes(task.status)).length,
    task_counts: {
      done: tasks.filter((task) => ['patient_reported_done', 'clinician_verified'].includes(task.status)).length,
      due: tasks.filter((task) => task.status === 'pending').length,
      missed: tasks.filter((task) => ['overdue', 'unable'].includes(task.status)).length
    },
    overdue_critical: tasks.filter((task) => task.status === 'overdue' && task.criticality === 'high').length,
    open_barriers: db.barriers.filter((barrier) => barrier.patient_id === patient.id && !barrier.status.startsWith('resolved')).length,
    open_escalations: db.escalations.filter((escalation) => escalation.patient_id === patient.id && escalation.status !== 'resolved').length,
    failed_messages: db.notifications.filter((item) => item.patient_id === patient.id && item.status === 'failed' && !item.retried).length,
    next_message: db.notifications.filter((item) => item.patient_id === patient.id && item.status === 'scheduled').sort((a, b) => a.scheduled_for.localeCompare(b.scheduled_for)).map(({ channel, scheduled_for, title }) => ({ channel, scheduled_for, title }))[0] || null,
    last_contact: lastEvent ? { at: lastEvent.reported_at, channel: lastEvent.source_channel, summary: lastEvent.summary } : null
  };
}

function withPatient(item) {
  const patient = db.patients.find((entry) => entry.id === item.patient_id);
  return { ...item, patient_name: patient?.name || item.patient_id, patient_language: patient?.language || null };
}

/* ---------- public mock API ---------- */

/* ---------- Care-team assistant (stand-in for the backend Clinician Assistant Agent) ----------
   Turns a typed or spoken instruction into proposed changes for one patient. Nothing is saved until the
   clinician confirms, and every field comes from the clinician's own words; the assistant never adds a
   medicine, dose or time they did not say. The real agent uses a language model; this stand-in uses patterns. */

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
const NUMBER_WORDS = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, fourteen: 14, thirty: 30 };
const TEST_WORDS = /\b(test|lab|labs|blood|scan|x-?ray|ecg|urine|swab)\b/;
const MEDICINE_WORDS = /\b\d+(?:\.\d+)?\s?(mg|mcg|ml|g|units?)\b|\b(tablets?|capsules?|syrup|injection|dose|medicine|medication|take|takes)\b/;
const VISIT_WORDS = /\b(book|appointment|visit|review|follow-?up|clinic|wound check|dressing|check-?up)\b/;
const TEXT_WORDS = /\b(text|sms|e-?mail|send (?:her|him|them)?\s*a message|message (?:her|him|them))\b/;
const CALL_WORDS = /\b(call|ring|phone)\b/;
const ASSISTANT_TEMPLATES = ['medicine', 'visit', 'call_clinic'];

const toNumber = (word) => NUMBER_WORDS[word] ?? Number(word);
const capitalise = (text) => text.charAt(0).toUpperCase() + text.slice(1);

// Reads a day and time from plain words. Returns null when the clause names neither.
function parseWhen(clause, fallbackHour) {
  const lower = clause.toLowerCase();
  const date = new Date();
  let dayFound = false;
  let match;
  if (/\btomorrow\b/.test(lower)) { date.setDate(date.getDate() + 1); dayFound = true; }
  else if (/\b(today|tonight|this (morning|afternoon|evening))\b/.test(lower)) dayFound = true;
  else if ((match = lower.match(/\bin (\d+|a|an|one|two|three|four|five|six|seven|ten|fourteen) (days?|weeks?)\b/))) {
    date.setDate(date.getDate() + toNumber(match[1]) * (match[2].startsWith('week') ? 7 : 1));
    dayFound = true;
  } else if (/\bnext week\b/.test(lower)) { date.setDate(date.getDate() + 7); dayFound = true; }
  else if ((match = lower.match(new RegExp(`\\b(${WEEKDAYS.join('|')})\\b`)))) {
    let diff = (WEEKDAYS.indexOf(match[1]) - date.getDay() + 7) % 7;
    if (diff === 0) diff = 7;
    date.setDate(date.getDate() + diff);
    dayFound = true;
  } else if ((match = lower.match(new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(?:of\\s+)?(${MONTHS.join('|')})\\b`))) || (match = lower.match(new RegExp(`\\b(${MONTHS.join('|')})\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b`)))) {
    const [day, month] = /\d/.test(match[1]) ? [Number(match[1]), MONTHS.indexOf(match[2])] : [Number(match[2]), MONTHS.indexOf(match[1])];
    date.setMonth(month, day);
    if (date < new Date(Date.now() - 864e5)) date.setFullYear(date.getFullYear() + 1);
    dayFound = true;
  }

  let hour = null;
  let minute = 0;
  if ((match = lower.match(/\b(\d{1,2})[:.](\d{2})\s*(am|pm)?\b/))) { hour = Number(match[1]); minute = Number(match[2]); if (match[3] === 'pm' && hour < 12) hour += 12; if (match[3] === 'am' && hour === 12) hour = 0; }
  else if ((match = lower.match(/\b(\d{1,2})\s*(am|pm)\b/))) { hour = Number(match[1]) % 12 + (match[2] === 'pm' ? 12 : 0); }
  else if ((match = lower.match(/\bat (\d{1,2})\b(?!\s*(mg|mcg|ml|g|days?|weeks?))/))) { hour = Number(match[1]); if (hour < 7) hour += 12; }
  else if (/\bmorning\b/.test(lower)) hour = 8;
  else if (/\bafternoon\b/.test(lower)) hour = 14;
  else if (/\b(evening|tonight|night)\b/.test(lower)) hour = 20;

  if (!dayFound && hour === null) return null;
  date.setHours(hour ?? fallbackHour, minute, 0, 0);
  if (!dayFound && date.getTime() < Date.now()) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

function parseTimes(lower) {
  if (/\b(three times|3 times)\b/.test(lower)) return ['08:00', '14:00', '20:00'];
  if (/\b(twice|two times|2 times|morning and (evening|night))\b/.test(lower)) return ['08:00', '20:00'];
  const clock = [...lower.matchAll(/\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b|\b(\d{1,2})[:.](\d{2})\b/g)].map((match) => {
    let hour = Number(match[1] ?? match[4]);
    const minute = Number(match[2] ?? match[5] ?? 0);
    if (match[3] === 'pm' && hour < 12) hour += 12;
    if (match[3] === 'am' && hour === 12) hour = 0;
    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  });
  if (clock.length) return [...new Set(clock)];
  if (/\b(evening|night|bedtime)\b/.test(lower)) return ['20:00'];
  if (/\bafternoon\b/.test(lower)) return ['14:00'];
  if (/\bmorning\b/.test(lower)) return ['08:00'];
  return null;
}

function mentionedPatient(text) {
  const lower = text.toLowerCase();
  return db.patients.find((patient) => lower.includes(patient.name.toLowerCase()))
    || db.patients.find((patient) => new RegExp(`\\b${patient.name.split(' ')[0].toLowerCase()}\\b`).test(lower))
    || null;
}

function splitInstruction(text) {
  return text
    .split(/(?<=[.!?;])\s+|\n+|\s+(?:and\s+)?also\s+|\s+(?:and\s+)?then\s+|\s+and\s+(?=(?:text|sms|e-?mail|send|message|call|ring|phone|book|schedule|add|remind|note|tell)\b)/i)
    .map((part) => part.trim().replace(/[.;]+$/, ''))
    .filter((part) => part.length > 2);
}

function draftAction(clause, patient) {
  const lower = clause.toLowerCase();
  const first = patient.name.split(' ')[0];
  const id = makeId('act');
  if (/^(note|add a note|write down|remember)\b[:\s]*/i.test(clause)) {
    return { id, kind: 'note', text: capitalise(clause.replace(/^(note|add a note|write down|remember)\b[:\s]*(that\s+)?/i, '')), issues: [] };
  }
  if (TEXT_WORDS.test(lower)) {
    const template = /\b(visit|appointment|clinic day)\b/.test(lower) ? 'visit' : MEDICINE_WORDS.test(lower) ? 'medicine' : 'call_clinic';
    if (!messageChannel(patient)) return { id, kind: 'send_text', template, blocked: true, issues: [`${first} has not agreed to email reminders, so this cannot be sent.`] };
    return { id, kind: 'send_text', template, issues: [] };
  }
  if (CALL_WORDS.test(lower) && !/\bcall (us|the clinic|the ward)\b/.test(lower)) {
    if (!patient.channels.includes('voice')) return { id, kind: 'call_patient', blocked: true, issues: [`${first} has not agreed to phone calls, so Tomi cannot call.`] };
    return { id, kind: 'call_patient', issues: parseWhen(clause, 10) ? ['Tomi calls straight away. Calls at a set time are not available yet.'] : [] };
  }
  if (TEST_WORDS.test(lower)) {
    const name = lower.match(/(?:(?:a|an|the|her|his|their)\s+)((?:[a-z-]+\s+){0,3}?(?:blood test|test|scan|x-?ray|ecg|swab|labs?))\b/)?.[1];
    const due_at = parseWhen(clause, 9);
    const issues = [];
    if (!due_at) issues.push('No date given. Set when it is due.');
    return { id, kind: 'test', title: name ? capitalise(name) : 'Test', detail: lower.match(/\bat (?:the )?([a-z ]*(?:laboratory|lab|clinic|radiology))\b/)?.[1] ? capitalise(lower.match(/\bat (?:the )?([a-z ]*(?:laboratory|lab|clinic|radiology))\b/)[1]) : 'Hospital laboratory', due_at, issues };
  }
  if (MEDICINE_WORDS.test(lower) && !VISIT_WORDS.test(lower.replace(/\b(review|follow-?up)\b/g, ''))) {
    const named = clause.match(/\b([A-Za-z][a-z]{3,}(?:[- ][A-Za-z][a-z]+)?)\s+(\d+(?:\.\d+)?\s?(?:mg|mcg|ml|g|units?))\b/i);
    const nameOnly = !named && clause.match(/\btakes?\s+(?:the\s+|her\s+|his\s+|their\s+)?([A-Za-z][a-z]{3,})\b/i)?.[1];
    const form = lower.match(/\b(tablet|capsule|syrup|injection)s?\b/)?.[1];
    const amount = lower.match(/\b(\d+|one|two|half)\s+(tablet|capsule|teaspoon|spoon)s?\b/);
    const daysMatch = lower.match(/\bfor (\d+|a|one|two|three|four|five|six|seven|ten|fourteen|thirty) (days?|weeks?)\b/);
    const times = parseTimes(lower);
    const issues = [];
    if (!named) issues.push(nameOnly ? 'No dose given. Add it after the name before you confirm.' : 'The medicine name or dose is not clear. Type it in before you confirm.');
    if (!times) issues.push('No time given. Set to 08:00. Change it if needed.');
    if (!daysMatch) issues.push('No length given. Set to 7 days. Change it if needed.');
    return {
      id, kind: 'medicine',
      title: named ? `${capitalise(named[1])} ${named[2].replace(/\s/g, ' ').replace(/(\d)(mg|mcg|ml|g)/i, '$1 $2')}${form ? ` ${form}` : ''}` : nameOnly ? capitalise(nameOnly) : '',
      detail: amount ? `${amount[1]} ${amount[2]}${amount[1] === 'one' || amount[1] === '1' ? '' : 's'}` : form ? `1 ${form}` : '',
      times: times || ['08:00'],
      days: daysMatch ? toNumber(daysMatch[1]) * (daysMatch[2].startsWith('week') ? 7 : 1) : 7,
      starts_on: (parseWhen(clause.replace(/\b(morning|evening|night|afternoon)\b/gi, ''), 8) || new Date().toISOString()).slice(0, 10),
      issues
    };
  }
  if (VISIT_WORDS.test(lower)) {
    const what = lower.match(/\b(wound check|dressing change|check-?up|review visit|review|follow-?up(?: visit)?|[a-z]+ review|[a-z]+ clinic visit)\b/)?.[1];
    const where = clause.match(/\b(?:at|in) (?:the )?((?:[A-Z][a-z]+ )*(?:Clinic|Outpatients|Ward|Unit|Centre)(?:,? room \d+)?)/)?.[0]?.replace(/^(at|in) (the )?/i, '');
    const starts_at = parseWhen(clause, 10);
    const issues = [];
    if (!starts_at) issues.push('No date or time given. Set when the visit is.');
    if (!where) issues.push('No place given. Add where the visit is.');
    return { id, kind: 'visit', what: what ? capitalise(what.replace(/^review$/, 'review visit')) : 'Review visit', where: where || '', starts_at, issues };
  }
  return { id, kind: 'note', text: capitalise(clause), issues: [] };
}

function templateOptions(patient) {
  const first = patient.name.split(' ')[0];
  return ASSISTANT_TEMPLATES.map((templateId) => ({ id: templateId, title: MESSAGE_TEMPLATES[templateId].title, body: MESSAGE_TEMPLATES[templateId].body(first) }));
}

function draftReply(patient, actions) {
  if (!actions.length) return `I did not find anything to change for ${patient.name}. Try saying what to add, book, send or note.`;
  const count = actions.length === 1 ? 'one change' : `${actions.length} changes`;
  const flagged = actions.some((action) => !action.blocked && action.issues.length);
  const blocked = actions.filter((action) => action.blocked).length;
  const left = blocked ? `${blocked === 1 ? 'One' : blocked} cannot be done, so ${blocked === 1 ? 'it is' : 'they are'} left out. ` : '';
  return `For ${patient.name}, I have drafted ${count}. ${flagged ? 'Some need a detail from you. ' : ''}${left}${actions.length === 1 ? 'Check it' : 'Check them'}, then confirm. Nothing is saved until you do.`;
}

function applyAction(patient, action, by) {
  const first = patient.name.split(' ')[0];
  if (action.kind === 'medicine') {
    if (!action.title?.trim()) throw new Error('Add the medicine name and dose.');
    const times = (Array.isArray(action.times) ? action.times : String(action.times).split(/[,\s]+/)).filter((time) => /^\d{1,2}:\d{2}$/.test(time));
    const days = Math.min(Math.max(Number(action.days) || 1, 1), 90);
    if (!times.length) throw new Error('Add at least one time, such as 08:00.');
    const start = new Date(`${action.starts_on}T00:00:00`);
    let created = 0;
    for (let day = 0; day < days; day += 1) {
      times.forEach((time) => {
        const due = new Date(start);
        due.setDate(due.getDate() + day);
        const [hour, minute] = time.split(':').map(Number);
        due.setHours(hour, minute, 0, 0);
        if (due.getTime() < Date.now()) return;
        db.tasks.push({ id: makeId('t'), patient_id: patient.id, type: 'medication', title: action.title.trim(), detail: action.detail?.trim() || '', due_at: due.toISOString(), criticality: 'high', status: 'pending', last_reported_at: null, created_by: by });
        created += 1;
      });
    }
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'task_added', summary: `Added ${action.title.trim()} at ${times.join(' and ')} for ${days} ${days === 1 ? 'day' : 'days'}.`, verification_status: 'clinician_verified' });
    scheduleReminders(db, patient);
    return `${action.title.trim()}: ${created} ${created === 1 ? 'reminder' : 'reminders'} added.`;
  }
  if (action.kind === 'test') {
    if (!action.title?.trim()) throw new Error('Add the name of the test.');
    if (!action.due_at) throw new Error('Set when the test is due.');
    db.tasks.push({ id: makeId('t'), patient_id: patient.id, type: 'test', title: action.title.trim(), detail: action.detail?.trim() || '', due_at: action.due_at, criticality: 'medium', status: 'pending', last_reported_at: null, created_by: by });
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'task_added', summary: `Added ${action.title.trim()}, due ${new Date(action.due_at).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}.`, verification_status: 'clinician_verified' });
    scheduleReminders(db, patient);
    return `${action.title.trim()} added to the plan.`;
  }
  if (action.kind === 'visit') {
    if (!action.starts_at) throw new Error('Set the date and time of the visit.');
    if (!action.where?.trim()) throw new Error('Add where the visit is.');
    const appointment = { id: makeId('a'), patient_id: patient.id, what: action.what?.trim() || 'Review visit', where: action.where.trim(), starts_at: action.starts_at, status: 'scheduled', created_by: by };
    db.appointments.push(appointment);
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'appointment_booked', summary: `Booked ${appointment.what.toLowerCase()} at ${appointment.where}.`, verification_status: 'clinician_verified' });
    scheduleReminders(db, patient);
    return `${appointment.what} booked.`;
  }
  if (action.kind === 'send_text') {
    const channel = messageChannel(patient);
    if (!channel) throw new Error(`${first} has not agreed to email reminders.`);
    if (!ASSISTANT_TEMPLATES.includes(action.template)) throw new Error('Choose which message to send.');
    const message = queueMessage(db, patient, { channel, template: action.template, created_by: by });
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'notification_requested', summary: `Sent a "${message.title}" ${channelNoun(channel)}.`, verification_status: 'clinician_verified' });
    advanceMessages();
    return `"${message.title}" ${channelNoun(channel)} sent to ${first}.`;
  }
  if (action.kind === 'call_patient') {
    if (!patient.channels.includes('voice')) throw new Error(`${first} has not agreed to phone calls.`);
    const call = { id: makeId('c'), patient_id: patient.id, direction: 'outbound', channel: 'phone', status: 'initiated', verification_state: 'pending', language: patient.language, started_at: nowIso(), ended_at: null, outcome: null, turns: [], script: outboundScript(patient), script_started: Date.now(), script_index: 0 };
    db.calls.push(call);
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'voice', event_type: 'call_requested', summary: 'Outbound Tomi call requested from the assistant.', verification_status: 'clinician_verified' });
    advanceCall(call);
    return `Tomi is calling ${first} now.`;
  }
  if (action.kind === 'note') {
    if (!action.text?.trim()) throw new Error('The note is empty.');
    logEvent(patient.id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'care_team_note', summary: action.text.trim(), verification_status: 'clinician_verified' });
    return 'Note added to the timeline.';
  }
  throw new Error('This kind of change is not supported.');
}

const assistantMethods = {
  async draftAssistantActions({ text, patient_id }) {
    const instruction = String(text || '').trim();
    if (!instruction) { const error = new Error('Type or say what you want done.'); error.status = 400; throw error; }
    const patient = patient_id ? findPatient(patient_id) : mentionedPatient(instruction);
    if (!patient) {
      return respond({ draft: { instruction, patient: null, reply: 'Which patient is this for? Choose one and I will draft the changes.', needs_patient: true, choices: db.patients.map((item) => ({ id: item.id, name: item.name })), actions: [] } }, 500);
    }
    const actions = splitInstruction(instruction).map((clause) => draftAction(clause, patient));
    return respond({ draft: { instruction, patient: { id: patient.id, name: patient.name, language: patient.language, channels: patient.channels }, reply: draftReply(patient, actions), needs_patient: false, actions, templates: templateOptions(patient) } }, 700);
  },

  async applyAssistantActions({ patient_id, actions, by }) {
    const patient = findPatient(patient_id);
    const who = by || REVIEWER;
    const results = (actions || []).filter((action) => !action.blocked).map((action) => {
      try { return { id: action.id, kind: action.kind, ok: true, summary: applyAction(patient, action, who) }; }
      catch (error) { return { id: action.id, kind: action.kind, ok: false, summary: error.message }; }
    });
    return respond({ results, patient: { id: patient.id, name: patient.name } }, 500);
  }
};

export const mock = {
  ...assistantMethods,
  async getSupportInfo() { return respond(SUPPORT, 60); },
  async listSampleNotes() { return respond({ notes: SAMPLE_NOTES.map((note) => ({ ...note, text: note.text.replaceAll(DEFAULT_FACILITY, FACILITY) })) }, 60); },

  async listPatients() { advanceAll(); return respond({ patients: db.patients.map(patientSummary) }); },
  async getPatient(id) { return respond({ patient: patientSummary(findPatient(id)) }); },
  async createPatient(input) {
    // The person who adds a patient becomes their lead clinician (the real backend reads the session the same way).
    const staff = JSON.parse(window.localStorage.getItem('careloop-session-staff') || 'null')?.user;
    const patient = { id: makeId('p'), age: null, caregiver: null, email: null, channels: [], contact_window: null, pin_set: false, consent_at: null, activation_status: 'plan_review', caregiver_mode: false, assigned_to: staff ? { id: staff.id, name: staff.name } : null, ...input };
    db.patients.push(patient);
    logEvent(patient.id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'patient_created', summary: 'Patient record created with discharge note.', verification_status: 'clinician_verified' });
    return respond({ patient: patientSummary(patient) });
  },
  async updateProfile(id, profile) {
    const patient = findPatient(id);
    Object.assign(patient, profile);
    logEvent(id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'profile_updated', summary: `Preferences updated: ${patient.language}, ${patient.literacy_level} reading.`, verification_status: 'self_reported' });
    return respond({ patient: patientSummary(patient) });
  },
  async recordConsent(id, consent) {
    const patient = findPatient(id);
    patient.channels = consent.channels;
    if (consent.email) patient.email = consent.email;
    patient.contact_window = consent.contact_window || patient.contact_window;
    patient.pin_set = Boolean(consent.pin) || patient.pin_set;
    patient.consent_at = nowIso();
    patient.activation_status = 'active';
    logEvent(id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'consent_recorded', summary: `Agreed to be contacted by ${channelList(consent.channels)}.`, verification_status: 'self_reported' });
    scheduleReminders(db, patient);
    return respond({ patient: patientSummary(patient) });
  },
  // Turning a channel on or off after sign-up. Withdrawals are logged and stop anything already scheduled.
  async updateConsent(id, { channels, by }) {
    const patient = findPatient(id);
    const removed = patient.channels.filter((channel) => !channels.includes(channel));
    const added = channels.filter((channel) => !patient.channels.includes(channel));
    patient.channels = channels;
    if (removed.length) {
      cancelMessages(id, (item) => removed.includes(item.channel), 'Not sent. The patient turned this channel off.');
      logEvent(id, { actor_type: by === 'caregiver' ? 'caregiver' : 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'consent_withdrawn', summary: `Turned off ${channelList(removed)}.`, verification_status: 'self_reported' });
    }
    if (added.length) logEvent(id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'consent_recorded', summary: `Turned on ${channelList(added)}.`, verification_status: 'self_reported' });
    scheduleReminders(db, patient);
    return respond({ patient: patientSummary(patient) });
  },

  async createPlan({ patient_id, source_note }) {
    await wait(900);
    const patient = findPatient(patient_id);
    const issues = /as directed|next week/i.test(source_note)
      ? [{ field: 'medications[0].frequency', issue: 'How often to take it is not stated', severity: 'high', source_text: source_note.match(/as directed|next week/i)[0] }]
      : [];
    const plan = {
      id: makeId('plan'), patient_id, status: 'needs_review', clinician_approved_at: null, approved_by: null, source_note, verifier_issues: issues,
      medications: [{ name: draftMedicine(source_note), dose: '', frequency: '', times: [], duration: '', instructions: '' }],
      appointments: [{ what: 'Follow-up visit', where: '', date: '', time: '' }], tests: [], symptoms_to_watch: [], reminder_times: []
    };
    db.plans = db.plans.filter((item) => item.patient_id !== patient_id).concat(plan);
    logEvent(patient.id, { actor_type: 'agent', actor_id: 'Care Plan Agent', source_channel: 'system', event_type: 'plan_drafted', summary: `Plan drafted. ${issues.length} field${issues.length === 1 ? '' : 's'} flagged by the verifier.`, verification_status: 'system_recorded' });
    return respond({ plan });
  },
  async getPlan(patientId) {
    const plan = db.plans.find((item) => item.patient_id === patientId) || notFound('Plan');
    const tasks = db.tasks.filter((task) => task.patient_id === patientId).sort((a, b) => a.due_at.localeCompare(b.due_at));
    return respond({ plan, tasks });
  },
  async updatePlan(planId, updates) {
    const plan = db.plans.find((item) => item.id === planId) || notFound('Plan');
    Object.assign(plan, updates, { id: plan.id, patient_id: plan.patient_id });
    logEvent(plan.patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'plan_edited', summary: 'Plan fields edited by clinician.', verification_status: 'clinician_verified' });
    return respond({ plan });
  },
  async approvePlan(planId, { override_issues = false } = {}) {
    const plan = db.plans.find((item) => item.id === planId) || notFound('Plan');
    plan.status = 'approved';
    plan.clinician_approved_at = nowIso();
    plan.approved_by = REVIEWER;
    const patient = findPatient(plan.patient_id);
    if (patient.activation_status === 'plan_review') patient.activation_status = 'invited';
    logEvent(plan.patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'plan_approved', summary: override_issues ? 'Plan approved with verifier issues acknowledged.' : 'Plan approved.', verification_status: 'clinician_verified' });
    scheduleReminders(db, patient);
    return respond({ plan });
  },

  async getMessages(patientId) { return respond({ messages: db.messages.filter((message) => message.patient_id === patientId) }); },
  async sendMessage(patientId, payload) {
    const patient = findPatient(patientId);
    db.messages.push({ id: makeId('m'), patient_id: patientId, direction: 'patient', channel: 'web', original_text: payload.original_text, language: patient.language, created_at: nowIso() });
    if (payload.task_id) { const prompt = db.messages.find((message) => message.task_id === payload.task_id && !message.answered); if (prompt) prompt.answered = true; }
    const result = chatReply(patient, payload);
    const reply = { id: makeId('m'), patient_id: patientId, direction: 'careloop', channel: 'web', original_text: result.reply, english_text: result.reply, language: patient.language, confidence: 0.98, number_check_passed: true, created_at: nowIso() };
    db.messages.push(reply);
    if (result.barrier) reply.barrier = result.barrier;
    if (result.escalation) reply.escalation = { id: result.escalation.id, call_number: SUPPORT.emergency_number };
    return respond({ reply, barrier: result.barrier, escalation: result.escalation ? { id: result.escalation.id, call_number: SUPPORT.emergency_number } : null, reschedule: result.reschedule });
  },

  async listEvents({ patient_id, limit } = {}) {
    advanceAll();
    let events = db.events.filter((event) => !patient_id || event.patient_id === patient_id).sort((a, b) => b.reported_at.localeCompare(a.reported_at));
    if (limit) events = events.slice(0, limit);
    return respond({ events: events.map(withPatient) });
  },

  async listAppointments({ patient_id } = {}) {
    const appointments = db.appointments.filter((item) => !patient_id || item.patient_id === patient_id).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    return respond({ appointments: appointments.map(withPatient) });
  },
  async listSlots() { return respond({ slots: db.clinic_slots.filter((slot) => slot.starts_at > nowIso()).sort((a, b) => a.starts_at.localeCompare(b.starts_at)) }); },
  async listRescheduleRequests({ status } = {}) {
    const requests = db.reschedule_requests.filter((item) => !status || item.status === status).map((item) => ({ ...withPatient(item), appointment: db.appointments.find((appointment) => appointment.id === item.appointment_id) }));
    return respond({ requests });
  },
  async createRescheduleRequest(appointmentId, { reason }) {
    const appointment = db.appointments.find((item) => item.id === appointmentId) || notFound('Appointment');
    const patient = findPatient(appointment.patient_id);
    if (appointment.status === 'reschedule_requested') return respond({ appointment });
    appointment.status = 'reschedule_requested';
    const request = { id: makeId('rr'), appointment_id: appointment.id, patient_id: patient.id, reason, original_text: reason, channel: 'web', requested_at: nowIso(), status: 'pending', reviewer: null };
    db.reschedule_requests.push(request);
    logEvent(patient.id, { actor_type: 'patient', actor_id: patient.name, source_channel: 'web', event_type: 'reschedule_requested', summary: `Asked for a new appointment time: ${reason}.`, verification_status: 'self_reported' });
    return respond({ request, appointment });
  },
  async decideReschedule(requestId, { decision, slot_id }) {
    const request = db.reschedule_requests.find((item) => item.id === requestId) || notFound('Request');
    const appointment = db.appointments.find((item) => item.id === request.appointment_id);
    if (decision === 'approve') {
      const slot = db.clinic_slots.find((item) => item.id === slot_id) || notFound('Slot');
      if (slot.reserved_count >= slot.capacity) { const error = new Error('That slot was just taken. Choose another time.'); error.status = 409; throw error; }
      slot.reserved_count += 1;
      const oldTime = appointment.starts_at;
      appointment.status = 'cancelled';
      const replacement = { ...appointment, id: makeId('a'), starts_at: slot.starts_at, where: slot.where, status: 'rescheduled', replaces: appointment.id };
      db.appointments.push(replacement);
      request.status = 'approved';
      const patient = findPatient(request.patient_id);
      cancelMessages(patient.id, (item) => item.appointment_id === appointment.id, 'Not sent. The visit was moved.');
      messageChannels(patient).forEach((channel) => queueMessage(db, patient, { channel, template: 'visit_moved', appointment_id: replacement.id, created_by: REVIEWER }));
      scheduleReminders(db, patient);
      logEvent(request.patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'appointment_rescheduled', summary: `Visit moved from ${new Date(oldTime).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} to ${new Date(slot.starts_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}. Old reminder cancelled, new reminder scheduled.`, verification_status: 'clinician_verified' });
    } else {
      appointment.status = 'scheduled';
      request.status = 'rejected';
      logEvent(request.patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'reschedule_declined', summary: 'Kept the original visit time. Patient to be told.', verification_status: 'clinician_verified' });
    }
    request.reviewer = REVIEWER;
    return respond({ request });
  },
  async recordAttendance(appointmentId, { status }) {
    const appointment = db.appointments.find((item) => item.id === appointmentId) || notFound('Appointment');
    appointment.status = status;
    logEvent(appointment.patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'dashboard', event_type: 'attendance_recorded', summary: `${appointment.what}: ${status === 'attended' ? 'attended' : 'did not attend'}.`, verification_status: 'clinician_verified' });
    return respond({ appointment });
  },

  async listBarriers({ status } = {}) {
    const barriers = db.barriers.filter((item) => status !== 'open' || !item.status.startsWith('resolved'));
    return respond({ barriers: barriers.map(withPatient) });
  },
  async listNotifications({ patient_id, status } = {}) {
    advanceMessages();
    const groups = { upcoming: ['scheduled'], sent: ['sent', 'delivered'], problem: ['failed'], cancelled: ['cancelled'] };
    const matches = db.notifications
      .filter((item) => (!patient_id || item.patient_id === patient_id) && (!status || groups[status]?.includes(item.status)))
      .map(({ deliver_at, ...item }) => withPatient(item))
      .sort((a, b) => (status === 'upcoming' ? a.scheduled_for.localeCompare(b.scheduled_for) : b.scheduled_for.localeCompare(a.scheduled_for)));
    return respond({ notifications: matches });
  },
  async listMessageTemplates({ patient_id }) {
    const patient = findPatient(patient_id);
    const first = patient.name.split(' ')[0];
    return respond({ templates: MANUAL_TEMPLATES.map((id) => ({ id, title: MESSAGE_TEMPLATES[id].title, body: MESSAGE_TEMPLATES[id].body(first) })) }, 60);
  },
  async sendPatientMessage({ patient_id, channel, template, by }) {
    const patient = findPatient(patient_id);
    if (!patient.channels.includes(channel)) {
      const error = new Error(`${patient.name} has not agreed to ${channel === 'sms' ? 'text messages' : 'email'}.`);
      error.status = 403;
      throw error;
    }
    const message = queueMessage(db, patient, { channel, template, created_by: by || REVIEWER });
    logEvent(patient_id, { actor_type: 'clinician', actor_id: by || REVIEWER, source_channel: 'dashboard', event_type: 'notification_requested', summary: `Sent a "${message.title}" ${channel === 'sms' ? 'text' : 'email'}.`, verification_status: 'clinician_verified' });
    advanceMessages();
    return respond({ notification: withPatient(message) });
  },
  async cancelNotification(id, { by } = {}) {
    const message = db.notifications.find((item) => item.id === id) || notFound('Message');
    if (message.status !== 'scheduled') { const error = new Error('This message has already been sent.'); error.status = 409; throw error; }
    message.status = 'cancelled';
    message.failure_reason = `Cancelled by ${by || REVIEWER}.`;
    return respond({ notification: withPatient(message) });
  },
  async retryNotification(id, { by } = {}) {
    const original = db.notifications.find((item) => item.id === id) || notFound('Message');
    const patient = findPatient(original.patient_id);
    if (!patient.channels.includes(original.channel)) { const error = new Error(`${patient.name} has turned this channel off.`); error.status = 403; throw error; }
    const message = queueMessage(db, patient, { channel: original.channel, template: original.template, task_id: original.task_id, appointment_id: original.appointment_id, created_by: by || REVIEWER, retry_of: original.id });
    original.retried = true;
    advanceMessages();
    return respond({ notification: withPatient(message) });
  },

  async listCalls({ patient_id } = {}) {
    advanceAll();
    const calls = db.calls.filter((call) => !patient_id || call.patient_id === patient_id).sort((a, b) => b.started_at.localeCompare(a.started_at));
    return respond({ calls: calls.map(withPatient) }, 120);
  },
  async getCall(callId) { advanceAll(); return respond({ call: withPatient(db.calls.find((call) => call.id === callId) || notFound('Call')) }, 80); },
  async requestOutboundCall({ patient_id }) {
    const patient = findPatient(patient_id);
    if (!patient.channels.includes('voice')) { const error = new Error(`${patient.name} has not agreed to phone calls.`); error.status = 403; throw error; }
    const call = { id: makeId('c'), patient_id, direction: 'outbound', channel: 'phone', status: 'initiated', verification_state: 'pending', language: patient.language, started_at: nowIso(), ended_at: null, outcome: null, turns: [], script: outboundScript(patient), script_started: Date.now(), script_index: 0 };
    db.calls.push(call);
    logEvent(patient_id, { actor_type: 'clinician', actor_id: REVIEWER, source_channel: 'voice', event_type: 'call_requested', summary: 'Outbound Tomi call requested from the dashboard.', verification_status: 'clinician_verified' });
    return respond({ call: withPatient(advanceCall(call)) });
  },
  async simulateInboundCall({ patient_id }) {
    const patient = findPatient(patient_id);
    const call = { id: makeId('c'), patient_id, direction: 'inbound', channel: 'phone', status: 'ringing', verification_state: 'pending', language: patient.language, started_at: nowIso(), ended_at: null, outcome: null, turns: [], script: inboundScript(), script_started: Date.now(), script_index: 0 };
    db.calls.push(call);
    return respond({ call: withPatient(advanceCall(call)) });
  },

  async createVoiceSession({ patient_id }) {
    const patient = findPatient(patient_id);
    const session = { id: makeId('vs'), patient_id, channel: 'browser_voice', state: 'greeting', turns: [], verified: false, started_at: nowIso(), closed: false };
    db.voice_sessions.push(session);
    return respond({ session: { id: session.id, mode: 'mock', language: patient.language, demo_pin: patient.pin_mock || DEMO_PIN } }, 600);
  },
  async sendVoiceInput(sessionId, input) {
    const session = db.voice_sessions.find((item) => item.id === sessionId) || notFound('Voice session');
    const result = voiceTurn(session, input);
    if (result.ended) closeVoiceSession(session);
    return respond(result, 500);
  },
  async endVoiceSession(sessionId) {
    const session = db.voice_sessions.find((item) => item.id === sessionId);
    if (session) closeVoiceSession(session);
    return respond({ ok: true }, 80);
  },
  async getVoiceDemoPhrases() {
    return respond({ phrases: [
      { label: 'Yes, I took it', transcript: 'Yes, I took it', confidence: 0.93 },
      { label: 'Not yet', transcript: 'Not yet', confidence: 0.9 },
      { label: 'I could not buy the medicine', transcript: 'I could not buy the medicine, the pharmacy is out of stock', confidence: 0.86 },
      { label: 'Can I change my visit?', transcript: 'Can I change my visit to a new time?', confidence: 0.88 },
      { label: 'Unclear speech', transcript: 'mm… ba…', confidence: 0.31, presenter_only: true },
      { label: 'My chest hurts', transcript: 'My chest hurts and it is hard to breathe', confidence: 0.74 }
    ] }, 60);
  },

  async listEscalations({ status } = {}) {
    advanceAll();
    const matches = db.escalations.filter((item) => !status || (status === 'open' ? item.status !== 'resolved' : item.status === status));
    return respond({ escalations: matches.map(withPatient).sort((a, b) => b.created_at.localeCompare(a.created_at)) });
  },
  async acknowledgeEscalation(id, { by }) {
    const escalation = db.escalations.find((item) => item.id === id) || notFound('Escalation');
    escalation.status = 'acknowledged';
    escalation.history.push({ status: 'acknowledged', at: nowIso(), by });
    logEvent(escalation.patient_id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'escalation_acknowledged', summary: `${escalation.rule_label}: acknowledged.`, verification_status: 'clinician_verified' });
    return respond({ escalation: withPatient(escalation) });
  },
  async resolveEscalation(id, { note, by }) {
    const escalation = db.escalations.find((item) => item.id === id) || notFound('Escalation');
    escalation.status = 'resolved';
    escalation.note = note || null;
    escalation.history.push({ status: 'resolved', at: nowIso(), by });
    logEvent(escalation.patient_id, { actor_type: 'clinician', actor_id: by, source_channel: 'dashboard', event_type: 'escalation_resolved', summary: `${escalation.rule_label}: resolved.${note ? ` Note: ${note}` : ''}`, verification_status: 'clinician_verified' });
    return respond({ escalation: withPatient(escalation) });
  },

  async sendNextReminder(patientId) {
    const patient = findPatient(patientId);
    const task = nextOpenTask(patientId);
    if (!task) return respond({ message: null });
    const message = { id: makeId('m'), patient_id: patientId, direction: 'careloop', channel: 'web', original_text: `Reminder: ${task.title}, ${task.detail}. Did you take it?`, language: patient.language, created_at: nowIso(), task_id: task.id, number_check_passed: true, answered: false };
    db.messages.push(message);
    return respond({ message });
  },
  async resetDemo() {
    FACILITY = DEFAULT_FACILITY;
    db = seed();
    persist();
    return respond({ ok: true });
  }
};

export { patientName };

// For shared/mock-auth.js, which signs people in against the same fake patients.
export const mockDb = () => db;
// Moves the sample patients to the given hospital, renaming it everywhere it appears in their records.
export function setMockFacility(name) {
  if (!name || name === FACILITY) return;
  const text = JSON.stringify(db).replaceAll(FACILITY, name).replaceAll(`${shortFacility(FACILITY)} Patient Support Desk`, `${shortFacility(name)} Patient Support Desk`).replaceAll(`${shortFacility(FACILITY)} Ride to Clinic`, `${shortFacility(name)} Ride to Clinic`);
  db = JSON.parse(text);
  db.facility = name;
  FACILITY = name;
  persist();
}
export const mockPersist = () => persist();
