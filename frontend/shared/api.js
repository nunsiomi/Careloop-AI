// The only module that talks to the network. Pages and components import CareLoopAPI and never call fetch.
// Routes follow the proposed contract in docs/api_shapes.md (project documentation v2, section 11). Confirm shapes with Olamide.
// USE_MOCKS is on by default; add ?mock=0 to a page URL to call the FastAPI backend instead.
// A build made with VITE_USE_MOCKS=0 (the Railway image) uses the backend by default; ?mock=1 brings the mocks back.
import { mock } from './mock-server.js';
import { authMock } from './mock-auth.js';

const MOCK_PARAM = new URLSearchParams(window.location.search).get('mock');
export const USE_MOCKS = MOCK_PARAM === null ? import.meta.env.VITE_USE_MOCKS !== '0' : MOCK_PARAM !== '0';
const BASE_URL = '/api';

async function request(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await window.fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      // Sessions live in httpOnly cookies set by the backend.
      credentials: 'same-origin'
    });
  } catch {
    throw new Error('Could not reach CareLoop. Check your connection and try again.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || data.message || `Request failed (${response.status}).`);
    error.status = response.status;
    error.locked = Boolean(data.locked);
    throw error;
  }
  return data;
}

const query = (params = {}) => {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '');
  return entries.length ? `?${new URLSearchParams(entries)}` : '';
};
const id = encodeURIComponent;

const http = {
  /* Sign-in and accounts: patients and caregivers */
  getPatientSession: () => request('/auth/patient/session'),
  refreshPatientSession: () => request('/auth/patient/session'),
  startEmailSignIn: (body) => request('/auth/patient/otp', { method: 'POST', body }),
  startInviteSignIn: (code, body) => request(`/auth/invites/${id(code)}/otp`, { method: 'POST', body }),
  resendCode: (challengeId, body) => request(`/auth/patient/otp/${id(challengeId)}/resend`, { method: 'POST', body }),
  verifyCode: ({ challenge_id, code }) => request(`/auth/patient/otp/${id(challenge_id)}/verify`, { method: 'POST', body: { code } }),
  signInWithPin: (body) => request('/auth/patient/pin-sign-in', { method: 'POST', body }),
  setPin: (body) => request('/auth/patient/pin', { method: 'POST', body }),
  getInvite: (code) => request(`/auth/invites/${id(code)}`),
  signOutPatient: () => request('/auth/patient/sign-out', { method: 'POST' }),
  listCaregivers: (patientId) => request(`/patients/${id(patientId)}/caregivers`),
  inviteCaregiver: (patientId, body) => request(`/patients/${id(patientId)}/caregivers`, { method: 'POST', body }),
  removeCaregiver: (patientId, caregiverId) => request(`/patients/${id(patientId)}/caregivers/${id(caregiverId)}`, { method: 'DELETE' }),

  /* Sign-in and accounts: care team */
  getStaffSession: () => request('/auth/staff/session'),
  staffSignIn: (body) => request('/auth/staff/sign-in', { method: 'POST', body }),
  verifyStaffMfa: (body) => request('/auth/staff/mfa', { method: 'POST', body }),
  requestPasswordReset: (body) => request('/auth/staff/password-reset', { method: 'POST', body }),
  checkResetToken: (token) => request(`/auth/staff/password-reset/${id(token)}`),
  resetPassword: (token, body) => request(`/auth/staff/password-reset/${id(token)}`, { method: 'POST', body }),
  getStaffInvite: (token) => request(`/auth/staff/invites/${id(token)}`),
  acceptStaffInvite: (token, body) => request(`/auth/staff/invites/${id(token)}/accept`, { method: 'POST', body }),
  listFacilities: () => request('/facilities'),
  staffSignUp: (body) => request('/auth/staff/sign-up', { method: 'POST', body }),
  verifySignUpEmail: (body) => request('/auth/staff/sign-up/verify', { method: 'POST', body }),
  resendSignUpCode: (body) => request('/auth/staff/sign-up/resend', { method: 'POST', body }),
  resendStaffMfaEmail: (body) => request('/auth/staff/mfa/email', { method: 'POST', body }),
  unlockStaffSession: (body) => request('/auth/staff/unlock', { method: 'POST', body }),
  changePassword: (body) => request('/auth/staff/password', { method: 'POST', body }),
  listStaffSessions: () => request('/auth/staff/sessions'),
  staffSignOut: (body) => request('/auth/staff/sign-out', { method: 'POST', body }),

  listStaff: () => request('/staff'),
  assignPatient: (patientId, body) => request(`/patients/${id(patientId)}/assignment`, { method: 'PATCH', body }),
  getAdminFacility: () => request('/admin/facility'),
  newJoinCode: () => request('/admin/join-code', { method: 'POST' }),
  removeStaff: (staffId) => request(`/admin/staff/${id(staffId)}`, { method: 'DELETE' }),

  getSupportInfo: () => request('/support'),
  listSampleNotes: () => request('/demo/sample-notes'),

  listPatients: () => request('/patients'),
  getPatient: (patientId) => request(`/patients/${id(patientId)}`),
  createPatient: (patient) => request('/patients', { method: 'POST', body: patient }),
  updateProfile: (patientId, profile) => request(`/patients/${id(patientId)}/profile`, { method: 'PATCH', body: profile }),
  recordConsent: (patientId, consent) => request(`/patients/${id(patientId)}/consent`, { method: 'POST', body: consent }),
  updateConsent: (patientId, body) => request(`/patients/${id(patientId)}/consent`, { method: 'PATCH', body }),

  createPlan: (plan) => request(`/patients/${id(plan.patient_id)}/plan`, { method: 'POST', body: plan }),
  getPlan: (patientId) => request(`/patients/${id(patientId)}/plan`),
  updatePlan: (planId, updates) => request(`/plans/${id(planId)}`, { method: 'PATCH', body: updates }),
  approvePlan: (planId, options) => request(`/plans/${id(planId)}/approve`, { method: 'POST', body: options }),

  getMessages: (patientId) => request(`/patients/${id(patientId)}/messages`),
  sendMessage: (patientId, message) => request(`/patients/${id(patientId)}/messages`, { method: 'POST', body: message }),
  listEvents: ({ patient_id, limit } = {}) => request(patient_id ? `/patients/${id(patient_id)}/events${query({ limit })}` : `/events${query({ limit })}`),

  listAppointments: (filters) => request(`/appointments${query(filters)}`),
  listSlots: () => request('/clinic-slots'),
  listRescheduleRequests: (filters) => request(`/reschedule-requests${query(filters)}`),
  createRescheduleRequest: (appointmentId, body) => request(`/appointments/${id(appointmentId)}/reschedule-requests`, { method: 'POST', body }),
  decideReschedule: (requestId, body) => request(`/reschedule-requests/${id(requestId)}/decision`, { method: 'POST', body }),
  recordAttendance: (appointmentId, body) => request(`/appointments/${id(appointmentId)}/attendance`, { method: 'POST', body }),

  listBarriers: (filters) => request(`/barriers${query(filters)}`),
  // SMS and email reminders: generic text only, delivery status from the provider.
  listNotifications: (filters) => request(`/notifications${query(filters)}`),
  listMessageTemplates: ({ patient_id }) => request(`/patients/${id(patient_id)}/message-templates`),
  sendPatientMessage: (body) => request('/notifications', { method: 'POST', body }),
  cancelNotification: (notificationId, body) => request(`/notifications/${id(notificationId)}/cancel`, { method: 'POST', body }),
  retryNotification: (notificationId, body) => request(`/notifications/${id(notificationId)}/retry`, { method: 'POST', body }),

  listCalls: ({ patient_id } = {}) => request(patient_id ? `/patients/${id(patient_id)}/calls` : '/calls'),
  getCall: (callId) => request(`/calls/${id(callId)}`),
  requestOutboundCall: (body) => request('/calls/outbound', { method: 'POST', body }),
  simulateInboundCall: (body) => request('/demo/calls/inbound', { method: 'POST', body }),

  // Browser voice: the backend issues a short-lived LiveKit token; the Tomi worker handles audio, Spitch and turns.
  createVoiceSession: (body) => request('/voice/sessions', { method: 'POST', body }),
  sendVoiceInput: (sessionId, input) => request(`/voice/sessions/${id(sessionId)}/input`, { method: 'POST', body: input }),
  endVoiceSession: (sessionId) => request(`/voice/sessions/${id(sessionId)}/end`, { method: 'POST' }),
  getVoiceDemoPhrases: () => request('/demo/voice-phrases'),

  listEscalations: (filters) => request(`/escalations${query(filters)}`),
  acknowledgeEscalation: (escalationId, body) => request(`/escalations/${id(escalationId)}/acknowledge`, { method: 'POST', body }),
  resolveEscalation: (escalationId, body) => request(`/escalations/${id(escalationId)}/resolve`, { method: 'POST', body }),

  sendNextReminder: (patientId) => request(`/demo/patients/${id(patientId)}/reminders/next`, { method: 'POST' }),
  getAssistantWelcome: ({ patient_id } = {}) => request(`/assistant/welcome${query({ patient_id })}`),
  draftAssistantActions: (body) => request('/assistant/drafts', { method: 'POST', body }),
  applyAssistantActions: (body) => request('/assistant/apply', { method: 'POST', body }),
  resetDemo: () => request('/demo/reset', { method: 'POST' })
};

// ?voice=mock keeps the scripted voice demo even where live Tomi is set up.
const SCRIPTED_VOICE = new URLSearchParams(window.location.search).get('voice') === 'mock';

const mockApi = {
  ...mock,
  ...authMock,
  // Live Tomi in the browser wherever the voice token route is set up (frontend/api/voice/sessions.js);
  // otherwise the scripted voice demo from the mock.
  async createVoiceSession(body) {
    if (!SCRIPTED_VOICE) {
      try {
        const live = await http.createVoiceSession(body);
        if (live?.session?.mode === 'livekit') return live;
      } catch {
        // Not set up here: fall back to the scripted demo.
      }
    }
    return mock.createVoiceSession(body);
  },
  async resetDemo() {
    authMock.resetAuth();
    return mock.resetDemo();
  }
};

export const CareLoopAPI = USE_MOCKS ? mockApi : http;
