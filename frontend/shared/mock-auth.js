// In-browser stand-in for the auth endpoints in docs/api_shapes.md ("Sign-in and accounts").
// Every account, code, password and invite here is invented and exists only in this browser.
// The real backend keeps sessions in httpOnly cookies; this mock keeps them in local storage.
import { maskEmail, maskPhone, normalizePhone } from './format.js';
import { mockDb, mockPersist, setMockFacility, setSessionReader } from './mock-server.js';

// Bump the version whenever the seeded accounts change, so browsers drop their old saved copy.
const AUTH_KEY = 'careloop-auth-v7';
const SESSION_KEY = { patient: 'careloop-session-patient', staff: 'careloop-session-staff' };
const DEMO_PIN = '1234';
const CODE_TTL = 300; // seconds a sign-in code stays valid
const RESEND_AFTER = 60;
const MAX_TRIES = 5;
const COMMON_PASSWORDS = ['password', 'password1', 'password123', '123456789012', 'careloop123', 'qwertyuiop', 'iloveyou', 'nigeria123', 'lagos12345', 'welcome123', '12345678', '123456789', '87654321', '11111111', 'qwerty123', 'abc12345', 'abcd1234', 'passw0rd', 'letmein1', 'sunshine', 'football', 'baseball'];

const FACILITY = 'Kestrel General Hospital';
const FACILITY_TYPES = [
  { id: 'hospital', label: 'Hospital' },
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'clinic', label: 'Clinic or health centre' },
  { id: 'care_home', label: 'Care home' }
];
// Care facilities that use CareLoop. All invented. Each facility's CareLoop admin gives its join code to their own
// staff; nobody can create an account without it. The code never leaves the server.
const FACILITIES = [
  { id: 'kestrel', type: 'hospital', name: 'Kestrel General Hospital', city: 'Abuja', country: 'Nigeria', join_code: 'KGH-4821' },
  { id: 'egret', type: 'hospital', name: 'Egret Teaching Hospital', city: 'Ibadan', country: 'Nigeria', join_code: 'ETH-3067' },
  { id: 'hornbill', type: 'hospital', name: 'Hornbill Specialist Hospital', city: 'Kano', country: 'Nigeria', join_code: 'HSH-5914' },
  { id: 'weaverbird', type: 'hospital', name: 'Weaverbird Medical Centre', city: 'Enugu', country: 'Nigeria', join_code: 'WMC-2738' },
  { id: 'heron-bay', type: 'hospital', name: 'Heron Bay General Hospital', city: 'Lagos', country: 'Nigeria', join_code: 'HBG-6409' },
  { id: 'sunbird', type: 'pharmacy', name: 'Sunbird Pharmacy', city: 'Abuja', country: 'Nigeria', join_code: 'SBP-1956' },
  { id: 'ibis', type: 'clinic', name: 'Ibis Family Clinic', city: 'Accra', country: 'Ghana', join_code: 'IFC-4173' },
  { id: 'kingfisher', type: 'care_home', name: 'Kingfisher Care Home', city: 'Nairobi', country: 'Kenya', join_code: 'KCH-8352' }
];
const STAFF_ROLES = ['Doctor', 'Nurse', 'Follow-up nurse', 'Pharmacist', 'Pharmacy technician', 'Carer', 'Care coordinator'];
const EMAIL_FROM = 'CareLoop';
const ADMIN_ONLY = "Only your facility's CareLoop admin can open this page.";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function seedAuth() {
  return {
    signups: {},
    join_failures: { count: 0, locked_until: null },
    challenges: {},
    pin_failures: {},
    patient_pins: {},
    invites: {
      'CL-7K4Q': { code: 'CL-7K4Q', kind: 'patient', patient_id: 'p-chidi', facility: FACILITY, invited_by: 'Dr. Ada Okafor', status: 'pending' },
      'CG-3M9D': { code: 'CG-3M9D', kind: 'caregiver', patient_id: 'p-tola', name: 'Femi Adeyemi', relation: 'Son', facility: FACILITY, invited_by: 'Tola Adeyemi', status: 'pending' }
    },
    caregivers: [
      { id: 'cg-1', patient_id: 'p-zainab', name: 'Hadiza Musa', relation: 'Daughter', phone_e164: '+2348000000201', email: 'hadiza.musa@kestrelmail.ng', scope: 'Reminders and help with tasks', added_at: new Date(Date.now() - 3 * 864e5).toISOString() }
    ],
    staff: [
      { id: 'u-ada', name: 'Dr. Ada Okafor', email: 'ada.okafor@kestrelgeneral.ng', password: 'Blue-ward-morning-24', role: 'Clinician reviewer', facility: FACILITY, mfa: true, mfa_method: 'email', failures: 0, locked_until: null, is_admin: true, created_at: new Date(Date.now() - 30 * 864e5).toISOString() }
    ],
    staff_invites: {
      'join-7f3k': { token: 'join-7f3k', name: 'Bisi Ola', email: 'bisi.ola@kestrelgeneral.ng', role: 'Follow-up nurse', facility: FACILITY, invited_by: 'Dr. Ada Okafor', status: 'pending' }
    },
    mfa_tokens: {},
    resets: {},
    staff_sessions: []
  };
}

let auth = loadAuth();

function loadAuth() {
  try {
    const stored = window.localStorage.getItem(AUTH_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* fall through */ }
  return seedAuth();
}
function save() {
  try { window.localStorage.setItem(AUTH_KEY, JSON.stringify(auth)); } catch { /* keep in memory */ }
  mockPersist();
}

const wait = (ms = 380) => new Promise((resolve) => window.setTimeout(resolve, ms + Math.random() * 200));
async function ok(value, ms) { await wait(ms); save(); return JSON.parse(JSON.stringify(value)); }
async function fail(message, status = 400, extra = {}) {
  await wait(260);
  save();
  const error = new Error(message);
  error.status = status;
  Object.assign(error, extra);
  throw error;
}

const token = (prefix) => `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
const inSeconds = (seconds) => new Date(Date.now() + seconds * 1000).toISOString();
const sixDigits = () => String(Math.floor(100000 + Math.random() * 900000));
const db = () => mockDb();


function readSession(kind) {
  try {
    const session = JSON.parse(window.localStorage.getItem(SESSION_KEY[kind]) || 'null');
    if (session && session.expires_at > new Date().toISOString()) return session;
  } catch { /* ignore */ }
  return null;
}
setSessionReader(readSession);  // so Tomi's welcome in the mock can greet whoever is signed in

function writeSession(kind, session) {
  if (session) window.localStorage.setItem(SESSION_KEY[kind], JSON.stringify(session));
  else window.localStorage.removeItem(SESSION_KEY[kind]);
}

/* ---------- patients and caregivers ---------- */

// Patients and caregivers sign in by email (decided by Nunsi, 5 Nov 2026); one account per address.
const sameEmail = (a, b) => Boolean(a) && Boolean(b) && a.trim().toLowerCase() === b.trim().toLowerCase();
const pinKey = ({ kind, patient, caregiver }) => (kind === 'caregiver' ? `caregiver:${caregiver.id}` : `patient:${patient.id}`);

function patientSession({ kind, patient, caregiver }) {
  const pinSet = kind === 'caregiver' ? Boolean(auth.patient_pins[pinKey({ kind, patient, caregiver })]) || caregiver.id === 'cg-1' : Boolean(patient.pin_set);
  return {
    id: token('ps'),
    kind,
    patient_id: patient.id,
    user_name: kind === 'caregiver' ? caregiver.name : patient.name,
    acting_for_name: kind === 'caregiver' ? patient.name : null,
    relation: kind === 'caregiver' ? caregiver.relation : null,
    caregiver_id: kind === 'caregiver' ? caregiver.id : null,
    email: (kind === 'caregiver' ? caregiver.email : patient.email) || null,
    pin_set: pinSet,
    consent_needed: kind === 'patient' && !patient.consent_at,
    idle_lock_minutes: 10,
    expires_at: inSeconds(30 * 86400)
  };
}

// The PIN-failure key for a session (it carries kind, patient_id and caregiver_id rather than the records).
const sessionPinKey = (session) => (session.kind === 'caregiver' ? `caregiver:${session.caregiver_id}` : `patient:${session.patient_id}`);

function newChallenge(fields) {
  const challenge = { id: token('ch'), code: sixDigits(), tries: 0, expires_at: inSeconds(CODE_TTL), resend_at: inSeconds(RESEND_AFTER), ...fields };
  auth.challenges[challenge.id] = challenge;
  return challenge;
}
// Codes go by email only. The screen shows back the address the person typed, whether or not it has an account.
function demoMessage(challenge) {
  const code = challenge.code;
  if (!challenge.holder && challenge.purpose !== 'invite') return null; // no account with this address: nothing is sent
  return { channel: 'email', from: `${EMAIL_FROM} <codes@careloop.app>`, text: `${greeting(challenge.name)}

Here is your code to sign in to CareLoop:

    ${code}

It works for 5 minutes. Never share it, not even with your care team. If you did not ask for it, you can ignore this email.

The CareLoop team` };
}
const challengeView = (challenge) => ({
  challenge_id: challenge.id, via: 'email', masked_email: maskEmail(challenge.email),
  expires_in: CODE_TTL, resend_in: RESEND_AFTER, demo_code: challenge.code, demo_message: demoMessage(challenge)
});

function holderByEmail(email) {
  const patient = db().patients.find((item) => sameEmail(item.email, email));
  if (patient) return { kind: 'patient', patient };
  const caregiver = auth.caregivers.find((item) => sameEmail(item.email, email));
  if (caregiver) return { kind: 'caregiver', caregiver, patient: db().patients.find((item) => item.id === caregiver.patient_id) };
  return null;
}

export const authMock = {
  /* Patient app */
  async getPatientSession() { return ok({ session: readSession('patient') }, 40); },

  async startEmailSignIn({ email }) {
    const address = String(email || '').trim();
    if (!EMAIL_PATTERN.test(address)) return fail('Enter your email address, for example name@example.com.');
    const holder = holderByEmail(address);
    // Same answer whether or not the address is known, so the form cannot be used to look people up.
    const challenge = newChallenge({ email: address, via: 'email', purpose: 'sign_in', name: holder ? (holder.caregiver || holder.patient).name : null, holder: holder ? { kind: holder.kind, patient_id: holder.patient.id, caregiver_id: holder.caregiver?.id } : null });
    return ok(challengeView(challenge));
  },

  async startInviteSignIn(code, { email } = {}) {
    const invite = auth.invites[code?.toUpperCase()];
    if (!invite || invite.status !== 'pending') return fail('This invite code is not valid or has been used. Ask your care team for a new one.', 404);
    const address = String(email || '').trim();
    if (!EMAIL_PATTERN.test(address)) return fail('Enter your email address, for example name@example.com.');
    const holder = holderByEmail(address);
    if (holder && !(invite.kind === 'patient' && holder.kind === 'patient' && holder.patient.id === invite.patient_id)) return fail('This email address is already used for another CareLoop account. Use a different one.', 409);
    const name = invite.kind === 'caregiver' ? invite.name : db().patients.find((patient) => patient.id === invite.patient_id).name;
    const challenge = newChallenge({ email: address, via: 'email', purpose: 'invite', invite_code: invite.code, name });
    return ok(challengeView(challenge));
  },

  async resendCode(challengeId) {
    const challenge = auth.challenges[challengeId];
    if (!challenge) return fail('This code has expired. Start again.', 410);
    if (challenge.resend_at > new Date().toISOString()) return fail('Wait a moment before asking for another code.', 429);
    Object.assign(challenge, { code: sixDigits(), tries: 0, expires_at: inSeconds(CODE_TTL), resend_at: inSeconds(RESEND_AFTER) });
    return ok(challengeView(challenge));
  },

  async verifyCode({ challenge_id, code }) {
    const challenge = auth.challenges[challenge_id];
    if (!challenge || challenge.expires_at < new Date().toISOString()) return fail('This code has expired. Ask for a new one.', 410);
    if (challenge.tries >= MAX_TRIES) return fail('Too many wrong codes. Ask for a new one.', 429);
    if (String(code) !== challenge.code) {
      challenge.tries += 1;
      const left = MAX_TRIES - challenge.tries;
      return fail(left > 0 ? `That code is not right. You have ${left} ${left === 1 ? 'try' : 'tries'} left.` : 'Too many wrong codes. Ask for a new one.', 401);
    }
    delete auth.challenges[challenge_id];

    let session;
    if (challenge.purpose === 'invite') {
      const invite = auth.invites[challenge.invite_code];
      const patient = db().patients.find((item) => item.id === invite.patient_id);
      invite.status = 'accepted';
      if (invite.kind === 'caregiver') {
        const caregiver = { id: token('cg'), patient_id: patient.id, name: invite.name, relation: invite.relation, phone_e164: invite.phone_e164 || null, email: challenge.email, scope: 'See the plan, tasks and visits. Report on their behalf.', added_at: new Date().toISOString() };
        auth.caregivers.push(caregiver);
        session = patientSession({ kind: 'caregiver', patient, caregiver });
      } else {
        patient.activation_status = patient.consent_at ? patient.activation_status : 'invited';
        patient.email = challenge.email;
        session = patientSession({ kind: 'patient', patient });
      }
    } else {
      if (!challenge.holder) return fail('This email address is not linked to a CareLoop account. Use the invite your care team sent, or ask them to add you.', 404);
      const patient = db().patients.find((item) => item.id === challenge.holder.patient_id);
      const caregiver = auth.caregivers.find((item) => item.id === challenge.holder.caregiver_id);
      session = patientSession({ kind: challenge.holder.kind, patient, caregiver });
    }
    delete auth.pin_failures[sessionPinKey(session)];
    writeSession('patient', session);
    return ok({ session });
  },

  async signInWithPin({ email, pin }) {
    const holder = holderByEmail(email);
    if (!holder) return fail('This phone is not set up. Sign in with a code instead.', 404);
    const key = pinKey(holder);
    const failures = auth.pin_failures[key] || 0;
    if (failures >= MAX_TRIES) return fail('Too many wrong PINs. Sign in with a code to set a new PIN.', 429, { locked: true });
    const expected = auth.patient_pins[key] || DEMO_PIN;
    if (pin !== expected) {
      auth.pin_failures[key] = failures + 1;
      const left = MAX_TRIES - failures - 1;
      return fail(left > 0 ? `That PIN is not right. ${left} ${left === 1 ? 'try' : 'tries'} left.` : 'Too many wrong PINs. Sign in with a code to set a new PIN.', 401, { locked: left <= 0 });
    }
    delete auth.pin_failures[key];
    const session = patientSession(holder);
    writeSession('patient', session);
    return ok({ session });
  },

  async setPin({ pin }) {
    const session = readSession('patient');
    if (!session) return fail('Your session has ended. Sign in again.', 401);
    if (!/^\d{4}$/.test(pin)) return fail('Your PIN must be 4 numbers.');
    auth.patient_pins[sessionPinKey(session)] = pin;
    if (session.kind === 'patient') {
      const patient = db().patients.find((item) => item.id === session.patient_id);
      patient.pin_set = true;
      patient.pin_mock = pin;
    }
    const next = { ...session, pin_set: true };
    writeSession('patient', next);
    return ok({ session: next });
  },

  async getInvite(code) {
    const invite = auth.invites[code?.toUpperCase()];
    if (!invite) return fail('We could not find that invite code. Check the letters and numbers, or ask your care team.', 404);
    if (invite.status !== 'pending') return fail('This invite has already been used. Sign in with your email address instead.', 410);
    const patient = db().patients.find((item) => item.id === invite.patient_id);
    return ok({ invite: { code: invite.code, kind: invite.kind, facility: invite.facility, invited_by: invite.invited_by, patient_first_name: patient.name.split(' ')[0], caregiver_name: invite.name || null, relation: invite.relation || null, masked_email: invite.kind === 'patient' && patient.email ? maskEmail(patient.email) : null } });
  },

  async refreshPatientSession() {
    const session = readSession('patient');
    if (!session) return ok({ session: null }, 20);
    const patient = db().patients.find((item) => item.id === session.patient_id);
    const next = { ...session, consent_needed: session.kind === 'patient' && !patient?.consent_at };
    writeSession('patient', next);
    return ok({ session: next }, 20);
  },

  async signOutPatient() { writeSession('patient', null); return ok({ ok: true }, 120); },

  async listCaregivers(patientId) {
    return ok({
      caregivers: auth.caregivers.filter((item) => item.patient_id === patientId).map(({ phone_e164, ...rest }) => ({ ...rest, masked_phone: phone_e164 ? maskPhone(phone_e164) : null })),
      invites: Object.values(auth.invites).filter((item) => item.patient_id === patientId && item.kind === 'caregiver' && item.status === 'pending').map(({ phone_e164, ...rest }) => rest)
    });
  },
  async inviteCaregiver(patientId, { name, relation, phone, email }) {
    if (!name?.trim()) return fail('Enter their name.');
    if (!normalizePhone(phone)) return fail('Enter their mobile number. Check the country, then type the number, for example 0803 123 4567.');
    if (!EMAIL_PATTERN.test(String(email || '').trim())) return fail('Enter their email address, so we can send them the invite.');
    const code = `CG-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    const patient = db().patients.find((item) => item.id === patientId);
    auth.invites[code] = { code, kind: 'caregiver', patient_id: patientId, name: name.trim(), relation: relation || 'Family', facility: db().facility || FACILITY, invited_by: patient.name, status: 'pending', phone_e164: normalizePhone(phone), masked_phone: maskPhone(normalizePhone(phone)), email: String(email).trim() };
    return ok({ invite: auth.invites[code] });
  },
  async removeCaregiver(patientId, caregiverId) {
    auth.caregivers = auth.caregivers.filter((item) => item.id !== caregiverId);
    Object.values(auth.invites).forEach((invite) => { if (invite.code === caregiverId) invite.status = 'cancelled'; });
    return ok({ ok: true });
  },

  /* Clinician dashboard */
  async getStaffSession() { return ok({ session: readSession('staff') }, 40); },

  async staffSignIn({ email, password }) {
    const user = auth.staff.find((item) => item.email.toLowerCase() === String(email).trim().toLowerCase());
    const generic = 'That email and password do not match. Check both and try again.';
    if (user?.locked_until && user.locked_until > new Date().toISOString()) return fail('Too many attempts. Wait one minute or reset your password.', 429);
    if (!user || user.password !== password) {
      if (user) {
        user.failures += 1;
        if (user.failures >= MAX_TRIES) { user.locked_until = inSeconds(60); user.failures = 0; }
      }
      return fail(generic, 401);
    }
    user.failures = 0;
    const mfaToken = token('mfa');
    const pending = { user_id: user.id, expires_at: inSeconds(300), tries: 0 };
    auth.mfa_tokens[mfaToken] = pending;
    // Second step: a 6-digit code sent to the account's email address.
    pending.email_code = sixDigits();
    return ok({ mfa_token: mfaToken, masked_email: maskEmail(user.email), resend_in: RESEND_AFTER, demo_message: emailCodeMessage(pending.email_code, user.name, 'sign in') });
  },

  async resendStaffMfaEmail({ mfa_token }) {
    const pending = auth.mfa_tokens[mfa_token];
    if (!pending || pending.expires_at < new Date().toISOString()) return fail('Sign-in timed out. Enter your password again.', 410);
    pending.email_code = sixDigits();
    pending.tries = 0;
    const user = auth.staff.find((item) => item.id === pending.user_id);
    return ok({ resend_in: RESEND_AFTER, demo_message: emailCodeMessage(pending.email_code, user?.name, 'sign in') });
  },

  async verifyStaffMfa({ mfa_token, code, remember_device = false }) {
    const pending = auth.mfa_tokens[mfa_token];
    if (!pending || pending.expires_at < new Date().toISOString()) return fail('Sign-in timed out. Enter your password again.', 410);
    const user = auth.staff.find((item) => item.id === pending.user_id);
    if (String(code) !== pending.email_code) {
      pending.tries += 1;
      if (pending.tries >= MAX_TRIES) { delete auth.mfa_tokens[mfa_token]; return fail('Too many wrong codes. Enter your password again.', 429); }
      const left = MAX_TRIES - pending.tries;
      return fail(`That code is not right. Use the code from the newest email. ${left} ${left === 1 ? 'try' : 'tries'} left.`, 401);
    }
    delete auth.mfa_tokens[mfa_token];
    const session = staffSession(user, remember_device);
    return ok({ session });
  },

  async requestPasswordReset({ email }) {
    const user = auth.staff.find((item) => item.email.toLowerCase() === String(email).trim().toLowerCase());
    let demoLink = null;
    let demoMessage = null;
    if (user) {
      const resetToken = token('rst');
      auth.resets[resetToken] = { user_id: user.id, expires_at: inSeconds(1800) };
      demoLink = `#/reset-password/${resetToken}`;
      demoMessage = { channel: 'email', from: EMAIL_FROM, text: 'Reset your CareLoop password. This link works for 30 minutes. If you did not ask for this, ignore this email.', link: { href: demoLink, label: 'Choose a new password' } };
    }
    // Same response either way, so the form does not reveal who has an account.
    return ok({ ok: true, demo_link: demoLink, demo_message: demoMessage });
  },
  async checkResetToken(resetToken) {
    const reset = auth.resets[resetToken];
    if (!reset || reset.expires_at < new Date().toISOString()) return fail('This reset link has expired or was already used. Ask for a new one.', 410);
    const user = auth.staff.find((item) => item.id === reset.user_id);
    return ok({ email_masked: maskEmail(user.email) });
  },
  async resetPassword(resetToken, { password }) {
    const reset = auth.resets[resetToken];
    if (!reset) return fail('This reset link has expired or was already used. Ask for a new one.', 410);
    const user = auth.staff.find((item) => item.id === reset.user_id);
    const problem = passwordProblem(password, user.email);
    if (problem) return fail(problem);
    user.password = password;
    user.locked_until = null;
    delete auth.resets[resetToken];
    auth.staff_sessions = auth.staff_sessions.filter((item) => item.user_id !== user.id);
    writeSession('staff', null);
    return ok({ ok: true });
  },

  async getStaffInvite(inviteToken) {
    const invite = auth.staff_invites[inviteToken];
    if (!invite) return fail('This invite link is not valid. Ask the person who invited you to send a new one.', 404);
    if (invite.status !== 'pending') return fail('This invite was already used. Sign in instead.', 410);
    return ok({ invite: { name: invite.name, email: invite.email, role: invite.role, facility: invite.facility, invited_by: invite.invited_by } });
  },
  async acceptStaffInvite(inviteToken, { password }) {
    const invite = auth.staff_invites[inviteToken];
    if (!invite || invite.status !== 'pending') return fail('This invite is no longer valid.', 410);
    const problem = passwordProblem(password, invite.email);
    if (problem) return fail(problem);
    // The invite link went to this address, so the email is already confirmed.
    const user = newStaffUser({ name: invite.name, email: invite.email, password, role: invite.role, facility: invite.facility });
    invite.status = 'accepted';
    return ok({ session: staffSession(user, false) });
  },

  /* Self sign-up: any email address, a care facility from the list, then an email check. */
  // demo_join_code is mock-only, so testers can sign up without a facility admin. The real backend never returns join codes.
  async listFacilities() { return ok({ types: FACILITY_TYPES, facilities: FACILITIES.map(({ join_code, ...facility }) => ({ ...facility, demo_join_code: join_code })), roles: STAFF_ROLES }, 120); },

  async staffSignUp({ name, email, password, facility_id, join_code, role, confirmed }) {
    const cleanEmail = String(email || '').trim().toLowerCase();
    const facility = FACILITIES.find((item) => item.id === facility_id);
    if (!name?.trim() || name.trim().length < 3) return fail('Enter your full name.');
    if (!EMAIL_PATTERN.test(cleanEmail)) return fail('Enter an email address, for example amina@gmail.com.');
    if (!facility) return fail('Choose where you work.');
    const guard = auth.join_failures;
    if (guard.locked_until && guard.locked_until > new Date().toISOString()) return fail('Too many wrong facility codes. Wait 10 minutes, then try again.', 429);
    if (String(join_code || '').trim().toUpperCase().replace(/\s/g, '') !== facility.join_code) {
      guard.count += 1;
      if (guard.count >= MAX_TRIES) { guard.locked_until = inSeconds(600); guard.count = 0; return fail('Too many wrong facility codes. Wait 10 minutes, then try again.', 429); }
      return fail(`That code is not right for ${facility.name}. Ask your facility's CareLoop admin for it.`, 403, { field: 'join_code' });
    }
    guard.count = 0;
    if (!STAFF_ROLES.includes(role)) return fail('Choose your role.');
    const problem = passwordProblem(password, cleanEmail);
    if (problem) return fail(problem);
    if (!confirmed) return fail(`Confirm that you work at ${facility.name}.`);
    const signupToken = token('su');
    const existing = auth.staff.some((item) => item.email.toLowerCase() === cleanEmail);
    const code = sixDigits();
    auth.signups[signupToken] = { name: name.trim(), email: cleanEmail, password, role, facility: facility.name, code, existing, tries: 0, expires_at: inSeconds(900), resend_at: inSeconds(RESEND_AFTER) };
    // Same response whether or not the address already has an account; only the email itself differs.
    return ok({ signup_token: signupToken, masked_email: maskEmail(cleanEmail), resend_in: RESEND_AFTER, demo_message: existing ? existingAccountMessage() : emailCodeMessage(code, name, 'sign up') });
  },

  async resendSignUpCode({ signup_token }) {
    const signup = auth.signups[signup_token];
    if (!signup || signup.expires_at < new Date().toISOString()) return fail('This sign-up has expired. Start again.', 410);
    if (signup.resend_at > new Date().toISOString()) return fail('Wait a moment before asking for another code.', 429);
    Object.assign(signup, { code: sixDigits(), tries: 0, resend_at: inSeconds(RESEND_AFTER) });
    return ok({ resend_in: RESEND_AFTER, demo_message: signup.existing ? existingAccountMessage() : emailCodeMessage(signup.code, signup.name, 'sign up') });
  },

  async verifySignUpEmail({ signup_token, code }) {
    const signup = auth.signups[signup_token];
    if (!signup || signup.expires_at < new Date().toISOString()) return fail('This sign-up has expired. Start again.', 410);
    if (signup.tries >= MAX_TRIES) return fail('Too many wrong codes. Ask for a new one.', 429);
    if (signup.existing || String(code) !== signup.code) {
      signup.tries += 1;
      const left = MAX_TRIES - signup.tries;
      return fail(left > 0 ? `That code is not right. You have ${left} ${left === 1 ? 'try' : 'tries'} left.` : 'Too many wrong codes. Ask for a new one.', 401);
    }
    delete auth.signups[signup_token];
    const { name, email, password, role, facility } = signup;
    const user = newStaffUser({ name, email, password, role, facility });
    return ok({ session: staffSession(user, false) });
  },

  async unlockStaffSession({ password }) {
    const session = readSession('staff');
    if (!session) return fail('Your session has ended. Sign in again.', 401);
    const user = auth.staff.find((item) => item.id === session.user.id);
    if (!user || user.password !== password) return fail('That password is not right.', 401);
    return ok({ session });
  },
  async changePassword({ current, next }) {
    const session = readSession('staff');
    const user = auth.staff.find((item) => item.id === session?.user.id);
    if (!user) return fail('Your session has ended. Sign in again.', 401);
    if (user.password !== current) return fail('Your current password is not right.', 401);
    const problem = passwordProblem(next, user.email);
    if (problem) return fail(problem);
    user.password = next;
    auth.staff_sessions = auth.staff_sessions.filter((item) => item.user_id !== user.id || item.id === session.id);
    return ok({ ok: true });
  },
  async listStaffSessions() {
    const session = readSession('staff');
    if (!session) return fail('Your session has ended. Sign in again.', 401);
    return ok({ sessions: auth.staff_sessions.filter((item) => item.user_id === session.user.id).map((item) => ({ ...item, current: item.id === session.id })) });
  },
  async staffSignOut({ everywhere = false } = {}) {
    const session = readSession('staff');
    if (session) auth.staff_sessions = auth.staff_sessions.filter((item) => (everywhere ? item.user_id !== session.user.id : item.id !== session.id));
    writeSession('staff', null);
    return ok({ ok: true }, 120);
  },

  /* Care team at the signed-in person's facility, assignment, and the facility admin page */
  async listStaff() {
    const session = readSession('staff');
    if (!session) return fail('Your session has ended. Sign in again.', 401);
    return ok({ staff: auth.staff.filter((item) => item.facility === session.user.facility).map(({ id, name, role }) => ({ id, name, role })) }, 80);
  },
  async assignPatient(patientId, { staff_id }) {
    const session = readSession('staff');
    if (!session) return fail('Your session has ended. Sign in again.', 401);
    const patient = db().patients.find((item) => item.id === patientId);
    const lead = staff_id ? auth.staff.find((item) => item.id === staff_id && item.facility === session.user.facility) : null;
    if (staff_id && !lead) return fail('Choose someone from your care team.');
    patient.assigned_to = lead ? { id: lead.id, name: lead.name } : null;
    const stamp = new Date().toISOString();
    db().events.push({ id: token('ev'), patient_id: patientId, reported_at: stamp, recorded_at: stamp, actor_type: 'clinician', actor_id: session.user.name, source_channel: 'dashboard', event_type: 'patient_assigned', summary: lead ? `Lead clinician set to ${lead.name}.` : 'Lead clinician removed.', verification_status: 'clinician_verified', supersedes_event_id: null });
    return ok({ patient: { ...patient } });
  },
  async getAdminFacility() {
    const { session, facility } = adminContext();
    if (!session) return fail(ADMIN_ONLY, 403);
    const staff = auth.staff.filter((item) => item.facility === facility.name).map((item) => {
      const seen = auth.staff_sessions.filter((entry) => entry.user_id === item.id).map((entry) => entry.last_seen_at).sort().at(-1) || null;
      return { id: item.id, name: item.name, email: item.email, role: item.role, is_admin: Boolean(item.is_admin), joined_at: item.created_at || null, last_seen_at: seen };
    }).sort((first, second) => (second.joined_at || '').localeCompare(first.joined_at || ''));
    const { id, type, name, city, country, join_code } = facility;
    return ok({ facility: { id, type, name, city, country, join_code }, staff });
  },
  async newJoinCode() {
    const { session, facility } = adminContext();
    if (!session) return fail(ADMIN_ONLY, 403);
    facility.join_code = `${facility.join_code.split('-')[0]}-${Math.floor(1000 + Math.random() * 9000)}`;
    return ok({ join_code: facility.join_code });
  },
  async removeStaff(staffId) {
    const { session, facility } = adminContext();
    if (!session) return fail(ADMIN_ONLY, 403);
    if (staffId === session.user.id) return fail('You cannot remove your own account.', 409);
    auth.staff = auth.staff.filter((item) => item.id !== staffId || item.facility !== facility.name);
    auth.staff_sessions = auth.staff_sessions.filter((item) => item.user_id !== staffId);
    db().patients.forEach((patient) => { if (patient.assigned_to?.id === staffId) patient.assigned_to = null; });
    return ok({ ok: true });
  },

  resetAuth() {
    auth = seedAuth();
    writeSession('patient', null);
    save();
  }
};

function adminContext() {
  const session = readSession('staff');
  const user = session && auth.staff.find((item) => item.id === session.user.id);
  if (!user?.is_admin) return {};
  return { session, facility: FACILITIES.find((item) => item.name === user.facility) };
}

const greeting = (name) => (name?.trim() ? `Hello ${name.trim().split(' ')[0]},` : 'Hello,');
// Same wording as the backend (_code_email in backend/app/services/identity.py).
function emailCodeMessage(code, name, purpose) {
  const [lead, other] = purpose === 'sign up'
    ? ['Thank you for creating a CareLoop account. Here is your code to confirm your email:', 'create a CareLoop account']
    : ['Here is your code to sign in to CareLoop:', 'try to sign in'];
  return { channel: 'email', from: EMAIL_FROM, text: `${greeting(name)}

${lead}

    ${code}

It works for 15 minutes. If you did not ${other}, you can ignore this email.

The CareLoop team` };
}
function existingAccountMessage() {
  return { channel: 'email', from: EMAIL_FROM, text: 'Someone tried to create a CareLoop account with this email address, but you already have one. Sign in instead, or reset your password if you have forgotten it.', link: { href: '#/sign-in', label: 'Go to sign in' } };
}

function newStaffUser(account) {
  const user = { id: token('u'), ...account, mfa: true, mfa_method: 'email', failures: 0, locked_until: null, is_admin: false, created_at: new Date().toISOString() };
  auth.staff.push(user);
  return user;
}

function staffSession(user, rememberDevice) {
  // The sample patients and their invites belong to the care facility of whoever is signed in.
  setMockFacility(user.facility);
  Object.values(auth.invites).forEach((invite) => { invite.facility = user.facility; });
  const session = {
    id: token('ss'),
    user: { id: user.id, name: user.name, email: user.email, role: user.role, facility: user.facility, initials: user.name.replace(/^Dr\.\s*/, '').split(' ').map((part) => part[0]).join('').slice(0, 2), is_admin: Boolean(user.is_admin) },
    remember_device: rememberDevice,
    idle_lock_minutes: 15,
    expires_at: inSeconds(12 * 3600)
  };
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  auth.staff_sessions = auth.staff_sessions.filter((item) => item.user_id !== user.id || item.device !== 'Ward 4 nurses\' station');
  auth.staff_sessions.push(
    { id: session.id, user_id: user.id, device: `${browser} on this computer`, signed_in_at: new Date().toISOString(), last_seen_at: new Date().toISOString() },
    { id: token('ss'), user_id: user.id, device: 'Ward 4 nurses\' station', signed_in_at: new Date(Date.now() - 26 * 3600e3).toISOString(), last_seen_at: new Date(Date.now() - 5 * 3600e3).toISOString() }
  );
  writeSession('staff', session);
  return session;
}

export function passwordProblem(password, email = '') {
  if (!password || password.length < 8) return 'Use at least 8 characters.';
  if (password.length > 128) return 'Use 128 characters or fewer.';
  if (COMMON_PASSWORDS.includes(password.toLowerCase())) return 'That password is too common. Try a short phrase only you would know.';
  const local = email.split('@')[0]?.toLowerCase();
  if (local && local.length > 3 && password.toLowerCase().includes(local)) return 'Do not use your email address in your password.';
  return null;
}

export const DEMO_AUTH = { pin: DEMO_PIN, staffEmail: 'ada.okafor@kestrelgeneral.ng', staffPassword: 'Blue-ward-morning-24', patientInvite: 'CL-7K4Q', caregiverInvite: 'CG-3M9D', staffInvite: 'join-7f3k', facilityCodes: Object.fromEntries(FACILITIES.map((item) => [item.name, item.join_code])) };
