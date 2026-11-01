/*
 * CareLoop frontend API boundary.
 * API shapes marked PROPOSED must be confirmed with Olamide before backend integration.
 */
const BASE_URL = window.location.origin;
const USE_MOCKS = new URLSearchParams(window.location.search).get('mock') !== '0';
const MOCK_STORAGE_KEY = 'careloop.mock-state.v1';

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function waitForMock() {
  const delay = 400 + Math.floor(Math.random() * 401);
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

function newMockState() {
  const plans = [
    {
      id: 'plan-pidgin-001',
      patient_id: 'patient-pidgin-001',
      status: 'approved',
      source_note: 'Example care-team note for a fictional patient.',
      verifier_issues: [],
      medications: [{
        name: 'Example tablet', dose: '1 tablet', frequency: 'once daily', times: ['08:00'], duration: '7 days', instructions: 'Use the approved instruction from the care team.'
      }],
      appointments: [{ what: 'Example follow-up', where: 'Example Clinic', date: '2026-11-06', time: '10:00', critical: false }],
      tests: [],
      symptoms_to_watch: ['Use the safety guidance provided by the care team.'],
      reminder_times: ['08:00']
    },
    {
      id: 'plan-hausa-001',
      patient_id: 'patient-hausa-001',
      status: 'needs_review',
      source_note: 'Take the blue tablet as directed. Return for follow-up.',
      verifier_issues: [
        { field: 'medications[0].dose', issue: 'Ambiguous dose', severity: 'high', source_text: 'Take the blue tablet as directed.' },
        { field: 'appointments[0].date', issue: 'Missing follow-up date', severity: 'medium', source_text: 'Return for follow-up.' }
      ],
      medications: [{
        name: 'Example blue tablet', dose: 'Needs clinician review', frequency: 'once daily', times: ['08:00'], duration: 'Needs clinician review', instructions: 'Do not send until the clinician approves the plan.'
      }],
      appointments: [{ what: 'Follow-up', where: 'Example Clinic', date: null, time: null, critical: true }],
      tests: [],
      symptoms_to_watch: [],
      reminder_times: []
    },
    {
      id: 'plan-yoruba-001',
      patient_id: 'patient-yoruba-001',
      status: 'approved',
      source_note: 'Example care-team note for a fictional patient.',
      verifier_issues: [],
      medications: [{
        name: 'Example capsule', dose: '1 capsule', frequency: 'twice daily', times: ['08:00', '20:00'], duration: '5 days', instructions: 'Use the approved instruction from the care team.'
      }],
      appointments: [{ what: 'Example check-in', where: 'Example Clinic', date: '2026-11-08', time: '09:30', critical: false }],
      tests: [{ name: 'Example test', where: 'Example Clinic', date: '2026-11-07' }],
      symptoms_to_watch: ['Use the safety guidance provided by the care team.'],
      reminder_times: ['08:00', '20:00']
    }
  ];

  return {
    patients: [
      { id: 'patient-pidgin-001', name: 'Ebi Okoro', language: 'Pidgin', literacy_level: 'plain', caregiver_mode: false, consent: { status: 'active', channels: ['web'] } },
      { id: 'patient-hausa-001', name: 'Amina Bello', language: 'Hausa', literacy_level: 'plain', caregiver_mode: false, consent: { status: 'active', channels: ['web', 'sms'] } },
      { id: 'patient-yoruba-001', name: 'Tola Adeyemi', language: 'Yoruba', literacy_level: 'plain', caregiver_mode: true, consent: { status: 'active', channels: ['web'] } }
    ],
    plans,
    messages: {
      'patient-pidgin-001': [],
      'patient-hausa-001': [],
      'patient-yoruba-001': []
    },
    task_statuses: {
      'patient-pidgin-001': [{ id: 'plan-pidgin-001-medication-0', name: 'Example tablet', status: 'pending' }],
      'patient-hausa-001': [{ id: 'plan-hausa-001-medication-0', name: 'Example blue tablet', status: 'pending' }],
      'patient-yoruba-001': [{ id: 'plan-yoruba-001-medication-0', name: 'Example capsule', status: 'patient_reported_done' }]
    },
    escalations: [
      {
        id: 'escalation-demo-001', patient_id: 'patient-hausa-001', patient_name: 'Amina Bello', patient_language: 'Hausa',
        rule_id: 'possible_chest_pain', rule_label: 'Possible emergency phrase', status: 'open',
        original_text: 'ciwon kirji', english_text: 'chest pain',
        brief: 'Patient-reported possible chest-pain phrase. Identity and care-plan context require reviewer assessment.',
        outstanding: 'Human acknowledgement is still required.', brief_ready: true, created_at: '2026-10-30T09:15:00Z', call_number: '112'
      },
      {
        id: 'escalation-demo-002', patient_id: 'patient-yoruba-001', patient_name: 'Tola Adeyemi', patient_language: 'Yoruba',
        rule_id: 'missed_task', rule_label: 'Missed task', status: 'resolved',
        original_text: 'Fictional task reminder was not completed.', english_text: 'Fictional task reminder was not completed.',
        brief: 'Patient-reported task remains incomplete in this fictional demo.',
        outstanding: 'No outstanding action recorded.', brief_ready: true, created_at: '2026-10-29T10:00:00Z', resolved_at: '2026-10-29T11:00:00Z'
      }
    ]
  };
}

function loadMockState() {
  try {
    const saved = window.localStorage.getItem(MOCK_STORAGE_KEY);
    return saved ? JSON.parse(saved) : newMockState();
  } catch (error) {
    return newMockState();
  }
}

let mockState = loadMockState();

function saveMockState() {
  try {
    window.localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(mockState));
  } catch (error) {
    // Storage is optional; mocks continue in memory when it is unavailable.
  }
}

function requireValue(value, label) {
  if (value === undefined || value === null || value === '') {
    throw new Error(`${label} is required.`);
  }
}

function findPatient(patientId) {
  const index = Number(patientId);
  const patient = Number.isInteger(index) && index > 0
    ? mockState.patients[index - 1]
    : mockState.patients.find((item) => item.id === patientId);
  if (!patient) throw new Error(`Patient "${patientId}" was not found.`);
  return patient;
}

function findPlan(planId) {
  const plan = mockState.plans.find((item) => item.id === planId);
  if (!plan) throw new Error(`Plan "${planId}" was not found.`);
  return plan;
}

function makeId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await window.fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options
    });
  } catch (error) {
    throw new Error(`Could not reach CareLoop: ${error.message}`);
  }

  const contentType = response.headers.get('content-type') || '';
  let payload = null;
  if (contentType.includes('application/json')) {
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error(`CareLoop returned an unreadable response (${response.status}).`);
    }
  }
  if (!response.ok) {
    throw new Error(payload?.message || payload?.detail || `CareLoop request failed (${response.status}).`);
  }
  return payload;
}

function messageResponse(patient, text) {
  const normalized = text.toLowerCase();
  const message = {
    id: makeId('message'),
    patient_id: patient.id,
    direction: 'patient',
    original_text: text,
    created_at: new Date().toISOString()
  };
  mockState.messages[patient.id].push(message);

  const response = {
    reply: { original_text: 'Thank you. Your message has been received.', english_text: 'Thank you. Your message has been received.', language: patient.language, confidence: 0.98, number_check_passed: true },
    buttons: [],
    tasks_updated: [],
    barrier: null,
    escalation: null
  };

  if (/chest pain|chest dey pain me|ciwon kirji/.test(normalized)) {
    const escalation = {
      id: makeId('escalation'), patient_id: patient.id, patient_name: patient.name, patient_language: patient.language,
      rule_id: 'possible_chest_pain', rule_label: 'Possible emergency phrase', reason: 'Possible chest-pain phrase reported',
      original_text: text, english_text: 'Possible chest-pain phrase reported',
      brief: null, outstanding: 'Human acknowledgement is still required.', brief_ready: false,
      call_number: '112', status: 'open', created_at: new Date().toISOString()
    };
    mockState.escalations.push(escalation);
    response.reply = { original_text: 'This may need urgent attention. Please follow the approved emergency guidance now.', english_text: 'This may need urgent attention. Please follow the approved emergency guidance now.', language: patient.language, confidence: 0.98, number_check_passed: true };
    response.escalation = { id: escalation.id, rule_id: escalation.rule_id, reason: escalation.reason, call_number: escalation.call_number };
  } else if (/cost|money|afford/.test(normalized)) {
    const barrier = {
      id: makeId('barrier'),
      type: 'cost',
      attempts: 1,
      options: [
        { name: 'Example care-team support desk', type: 'Care team support', price: 'No cost', phone: '+2348000000001' },
        { name: 'Example clinic callback', type: 'Clinic support', distance: 'Phone support', phone: '+2348000000002' }
      ]
    };
    response.reply = { original_text: 'I have recorded that cost may be a barrier. Here are two options to consider.', english_text: 'I have recorded that cost may be a barrier. Here are two options to consider.', language: patient.language, confidence: 0.98, number_check_passed: true };
    response.buttons = barrier.options.map((option) => option.name);
    response.barrier = barrier;
  } else if (/\bdone\b/.test(normalized)) {
    const task = mockState.task_statuses[patient.id].find((item) => item.status !== 'patient_reported_done');
    if (task) {
      task.status = 'patient_reported_done';
      task.reported_at = new Date().toISOString();
      response.tasks_updated = [clone(task)];
    }
    response.reply = { original_text: 'Thank you. Your update has been recorded as patient-reported.', english_text: 'Thank you. Your update has been recorded as patient-reported.', language: patient.language, confidence: 0.98, number_check_passed: true };
  }

  mockState.messages[patient.id].push({ id: makeId('reply'), patient_id: patient.id, direction: 'careloop', ...response.reply, created_at: new Date().toISOString() });
  saveMockState();
  return clone(response);
}

function nextReminderMessage(patientId) {
  const plan = mockState.plans.find((item) => item.patient_id === patientId);
  if (!plan || !plan.medications.length) throw new Error(`No reminder task exists for patient "${patientId}".`);
  const medication = plan.medications[0];
  const message = {
    id: makeId('reminder'),
    patient_id: patientId,
    direction: 'careloop',
    kind: 'reminder',
    original_text: `Reminder: ${medication.name}`,
    task: { id: `${plan.id}-medication-0`, name: medication.name },
    created_at: new Date().toISOString()
  };
  mockState.messages[patientId].push(message);
  saveMockState();
  return clone(message);
}

const CareLoopAPI = {
  BASE_URL,
  USE_MOCKS,

  async createPatient(patient) {
    requireValue(patient?.name, 'Patient name');
    if (!CareLoopAPI.USE_MOCKS) return request('/api/patients', { method: 'POST', body: JSON.stringify(patient) });
    await waitForMock();
    const created = { id: makeId('patient'), language: 'English', literacy_level: 'plain', caregiver_mode: false, consent: { status: 'not_recorded', channels: [] }, ...clone(patient) };
    mockState.patients.push(created);
    mockState.messages[created.id] = [];
    mockState.task_statuses[created.id] = [];
    saveMockState();
    return { patient: clone(created) };
  },

  async getPatient(patientId) {
    requireValue(patientId, 'Patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}`);
    await waitForMock();
    return { patient: clone(findPatient(patientId)) };
  },

  async listPatients() {
    if (!CareLoopAPI.USE_MOCKS) return request('/api/patients');
    await waitForMock();
    const patients = mockState.patients.map((patient) => {
      const plan = mockState.plans.find((item) => item.patient_id === patient.id);
      const tasks = mockState.task_statuses[patient.id] || [];
      const messages = mockState.messages[patient.id] || [];
      const lastMessage = messages[messages.length - 1] || null;
      return {
        ...patient,
        plan_status: plan?.status || 'not_created',
        open_tasks: tasks.filter((task) => task.status !== 'patient_reported_done').length,
        last_message: lastMessage?.original_text || null
      };
    });
    return { patients: clone(patients) };
  },

  async recordConsent(patientId, consent) {
    requireValue(patientId, 'Patient ID');
    requireValue(consent?.channels, 'Consent channels');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}/consents`, { method: 'POST', body: JSON.stringify(consent) });
    await waitForMock();
    const patient = findPatient(patientId);
    const consentAt = new Date().toISOString();
    patient.consent_at = consentAt;
    patient.consent = { status: 'active', recorded_at: consentAt, ...clone(consent) };
    saveMockState();
    return { consent: clone(patient.consent) };
  },

  async updateProfile(patientId, profile) {
    requireValue(patientId, 'Patient ID');
    if (!profile || typeof profile !== 'object') throw new Error('Profile updates are required.');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}`, { method: 'PATCH', body: JSON.stringify(profile) });
    await waitForMock();
    const patient = findPatient(patientId);
    Object.assign(patient, clone(profile));
    saveMockState();
    return { patient: clone(patient) };
  },

  async createPlan(plan) {
    requireValue(plan?.patient_id, 'Plan patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request('/api/plans', { method: 'POST', body: JSON.stringify(plan) });
    await waitForMock();
    findPatient(plan.patient_id);
    const created = { id: makeId('plan'), status: 'needs_review', verifier_issues: [], medications: [], appointments: [], tests: [], symptoms_to_watch: [], reminder_times: [], ...clone(plan) };
    mockState.plans.push(created);
    saveMockState();
    return { plan: clone(created) };
  },

  async updatePlan(planId, updates) {
    requireValue(planId, 'Plan ID');
    if (!updates || typeof updates !== 'object') throw new Error('Plan updates are required.');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/plans/${encodeURIComponent(planId)}`, { method: 'PATCH', body: JSON.stringify(updates) });
    await waitForMock();
    const plan = findPlan(planId);
    Object.assign(plan, clone(updates));
    plan.updated_at = new Date().toISOString();
    saveMockState();
    return { plan: clone(plan) };
  },

  async getPlan(patientId) {
    requireValue(patientId, 'Patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}/plan`);
    await waitForMock();
    findPatient(patientId);
    const plan = mockState.plans.find((item) => item.patient_id === patientId);
    if (!plan) throw new Error(`No plan exists for patient "${patientId}".`);
    return { plan: clone(plan) };
  },

  async approvePlan(planId, options = {}) {
    requireValue(planId, 'Plan ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/plans/${encodeURIComponent(planId)}/approve`, { method: 'POST', body: JSON.stringify(options) });
    await waitForMock();
    const plan = findPlan(planId);
    if (plan.verifier_issues.length && !options.override_issues) throw new Error('This plan cannot be approved while verifier issues remain.');
    plan.status = 'approved';
    plan.approved_at = new Date().toISOString();
    saveMockState();
    return { plan: clone(plan) };
  },

  async sendMessage(patientId, message) {
    requireValue(patientId, 'Patient ID');
    requireValue(message?.original_text || message, 'Message text');
    const text = typeof message === 'string' ? message : message.original_text;
    if (typeof text !== 'string') throw new Error('Message text must be a string.');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}/messages`, { method: 'POST', body: JSON.stringify(typeof message === 'string' ? { original_text: text } : message) });
    await waitForMock();
    return messageResponse(findPatient(patientId), text);
  },

  async getMessages(patientId) {
    requireValue(patientId, 'Patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/patients/${encodeURIComponent(patientId)}/messages`);
    await waitForMock();
    findPatient(patientId);
    return { messages: clone(mockState.messages[patientId] || []) };
  },

  async listEscalations(filters = {}) {
    if (!CareLoopAPI.USE_MOCKS) {
      const query = new URLSearchParams(filters).toString();
      return request(`/api/escalations${query ? `?${query}` : ''}`);
    }
    await waitForMock();
    mockState.escalations.forEach((escalation) => {
      if (!escalation.brief_ready && new Date(escalation.created_at).getTime() + 5000 < Date.now()) {
        escalation.brief_ready = true;
        escalation.brief = 'Factual clinician brief is ready for reviewer assessment.';
      }
    });
    let escalations = mockState.escalations;
    if (filters.patient_id) escalations = escalations.filter((item) => item.patient_id === filters.patient_id);
    if (filters.status) escalations = escalations.filter((item) => item.status === filters.status);
    return { escalations: clone([...escalations].sort((first, second) => new Date(second.created_at) - new Date(first.created_at))) };
  },

  async resolveEscalation(escalationId, resolution = {}) {
    requireValue(escalationId, 'Escalation ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/escalations/${encodeURIComponent(escalationId)}/resolve`, { method: 'POST', body: JSON.stringify(resolution) });
    await waitForMock();
    const escalation = mockState.escalations.find((item) => item.id === escalationId);
    if (!escalation) throw new Error(`Escalation "${escalationId}" was not found.`);
    escalation.status = 'resolved';
    escalation.resolved_at = new Date().toISOString();
    escalation.resolution = clone(resolution);
    saveMockState();
    return { escalation: clone(escalation) };
  },

  async sendNextReminder(patientId) {
    requireValue(patientId, 'Patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/demo/patients/${encodeURIComponent(patientId)}/reminders/next`, { method: 'POST' });
    await waitForMock();
    const patient = findPatient(patientId);
    return { message: nextReminderMessage(patient.id) };
  },

  async simulateMissedTask(patientId) {
    requireValue(patientId, 'Patient ID');
    if (!CareLoopAPI.USE_MOCKS) return request(`/api/demo/patients/${encodeURIComponent(patientId)}/tasks/missed`, { method: 'POST' });
    await waitForMock();
    const patient = findPatient(patientId);
    const task = mockState.task_statuses[patient.id]?.find((item) => item.status !== 'patient_reported_done');
    if (!task) throw new Error('There is no pending task to mark as missed.');
    task.status = 'overdue';
    task.updated_at = new Date().toISOString();
    const message = { id: makeId('system'), patient_id: patient.id, direction: 'careloop', original_text: 'A task is now overdue.', created_at: new Date().toISOString() };
    mockState.messages[patient.id].push(message);
    saveMockState();
    return { task: clone(task), message: clone(message) };
  },

  async resetDemo() {
    if (!CareLoopAPI.USE_MOCKS) return request('/api/demo/reset', { method: 'POST' });
    return { state: CareLoopAPI.resetMocks() };
  },

  resetMocks() {
    mockState = newMockState();
    try { window.localStorage.removeItem(MOCK_STORAGE_KEY); } catch (error) { /* In-memory reset still succeeds. */ }
    return clone(mockState);
  }
};

window.CareLoopAPI = CareLoopAPI;
