const VALIDATED_DASHBOARD_LANGUAGES = ['English', 'Hausa', 'Yoruba', 'Igbo'];

const SAMPLE_NOTES = [
  { title: 'Sample note A', text: 'Fictional source note for demo patient A.' },
  { title: 'Sample note B', text: 'Fictional source note for demo patient B.' },
  { title: 'Sample note C', text: 'Fictional source note for demo patient C.' }
];

const STRINGS = {
  pageTitle: 'CareLoop clinician dashboard',
  brand: 'CareLoop',
  navLabel: 'Main',
  filtersLabel: 'Filter escalations',
  patients: 'Patients',
  escalations: 'Escalations',
  reviewer: 'Clinician reviewer',
  reviewerName: 'Dr. Ada Okafor',
  addPatient: 'Add patient',
  loading: 'Loading…',
  errorPrefix: 'We could not load this page: ',
  emptyPatients: 'No patients to show.',
  emptyEscalations: 'No open escalations to show.',
  escalationFilters: { open: 'Open', resolved: 'Resolved', all: 'All' },
  markResolved: 'Mark resolved',
  resolutionNote: 'Resolution note (optional)',
  resolutionPlaceholder: 'Add a factual resolution note',
  resolving: 'Resolving…',
  originalMessage: 'Patient’s original message',
  englishVersion: 'English version',
  summaryBrief: 'Summary brief',
  outstanding: 'Still outstanding',
  briefLoading: 'Preparing factual summary brief…',
  backToPatients: 'Back to patients',
  planReview: 'Plan review',
  sourceNote: 'Discharge note',
  planSections: { medications: 'Medications', appointments: 'Appointments', tests: 'Tests', symptoms: 'Symptoms to watch', reminders: 'Reminder times' },
  planLabels: { name: 'Name', dose: 'Dose', frequency: 'Frequency', times: 'Times', duration: 'Duration', instructions: 'Instructions', what: 'What', where: 'Where', date: 'Date', time: 'Time' },
  verifierIssues: 'Verifier issues',
  noVerifierIssues: 'No verifier issues.',
  issueField: 'Field',
  issueDetail: 'Issue',
  issueSeverity: 'Severity',
  issueSource: 'Source text',
  table: {
    name: 'Name', language: 'Language', readingLevel: 'Reading level', planStatus: 'Plan status', openTasks: 'Open tasks', lastMessage: 'Last message', reason: 'Reason', status: 'Status'
  },
  status: {
    needs_review: 'Needs review', approved: 'Approved', escalated: 'Escalated', resolved: 'Resolved', not_created: 'Not created', open: 'Open'
  },
  beta: 'Beta',
  approve: 'Approve',
  edit: 'Edit',
  saveAndApprove: 'Save and approve',
  approveConfirm: 'This plan still has verifier issues. Do you want to approve it anyway?',
  sentToast: 'The plan was sent to the patient.',
  fixedSafetyNote: 'CareLoop only restates what the clinician wrote. Check every dose.',
  noMessage: '—',
  modal: {
    title: 'Add patient', close: 'Close', name: 'Name', phone: 'Fake phone', language: 'Language', reading: 'Reading level', caregiver: 'Caregiver mode', note: 'Discharge note', sample: 'Load sample note', chooseSample: 'Choose a sample note', cancel: 'Cancel', submit: 'Create patient and plan', creating: 'Creating…', required: 'Name and discharge note are required.'
  },
  toast: 'Patient and plan created.',
  escalationCount: (count) => `${count} open escalations`
};

const app = document.getElementById('app');
let escalationTimer = null;
let modalReturnFocus = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function currentRoute() {
  const hash = window.location.hash || '#patients';
  if (hash === '#escalations') return { name: 'escalations' };
  if (hash.startsWith('#plan/')) return { name: 'plan', patientId: decodeURIComponent(hash.slice(6)) };
  return { name: 'patients' };
}

function statusChip(status) {
  const className = status === 'approved' ? 'status-approved' : status === 'resolved' ? 'status-resolved' : status === 'escalated' || status === 'open' ? 'status-escalated' : 'status-needs-review';
  return element('span', `status-chip ${className}`, STRINGS.status[status] || status);
}

function languageLabel(language) {
  const label = element('span', 'language-label');
  label.append(document.createTextNode(language));
  if (!VALIDATED_DASHBOARD_LANGUAGES.includes(language)) label.append(document.createTextNode(' '), element('span', 'status-chip status-beta', STRINGS.beta));
  return label;
}

function showToast(message) {
  const toast = element('div', 'toast dashboard-toast', message);
  toast.setAttribute('role', 'status');
  document.body.append(toast);
  window.setTimeout(() => toast.remove(), 3200);
}

function renderShell() {
  app.replaceChildren();
  const shell = element('div', 'app-shell');
  const sidebar = element('aside', 'sidebar');
  const brand = element('a', 'brand', STRINGS.brand);
  brand.href = '#patients';
  const nav = element('nav', 'sidebar-nav');
  nav.setAttribute('aria-label', STRINGS.navLabel);
  const patients = element('a', '', STRINGS.patients);
  patients.href = '#patients';
  const escalations = element('a', 'sidebar-escalations');
  escalations.href = '#escalations';
  escalations.append(document.createTextNode(STRINGS.escalations));
  const badge = element('span', 'escalation-count', '0');
  badge.id = 'escalation-count';
  escalations.append(badge);
  (currentRoute().name === 'escalations' ? escalations : patients).setAttribute('aria-current', 'page');
  nav.append(patients, escalations);
  sidebar.append(brand, nav);

  const main = element('main', 'dashboard-main');
  const topbar = element('header', 'dashboard-topbar');
  const reviewer = element('div', 'reviewer');
  reviewer.append(element('span', 'reviewer-role', STRINGS.reviewer), element('strong', '', STRINGS.reviewerName));
  const add = element('button', 'btn btn-primary', STRINGS.addPatient);
  add.type = 'button';
  add.addEventListener('click', showAddPatientModal);
  topbar.append(reviewer, add);
  const view = element('section', 'dashboard-view');
  view.id = 'dashboard-view';
  main.append(topbar, view);
  shell.append(sidebar, main);
  app.append(shell);
}

function showLoading() {
  const view = document.getElementById('dashboard-view');
  view.replaceChildren(element('p', 'dashboard-state', STRINGS.loading));
}

function showError(error) {
  const view = document.getElementById('dashboard-view');
  view.replaceChildren(element('p', 'dashboard-state dashboard-error', `${STRINGS.errorPrefix}${error.message}`));
}

function sortPatients(patients) {
  return [...patients].sort((first, second) => Number(second.plan_status === 'needs_review') - Number(first.plan_status === 'needs_review') || first.name.localeCompare(second.name));
}

function patientRow(patient) {
  const row = document.createElement('tr');
  row.addEventListener('click', () => { window.location.hash = `#plan/${encodeURIComponent(patient.id)}`; });
  const name = element('a', 'table-link', patient.name);
  name.href = `#plan/${encodeURIComponent(patient.id)}`;
  const language = element('td');
  language.append(languageLabel(patient.language));
  const cells = [element('td'), language, element('td', '', patient.literacy_level), element('td'), element('td', '', String(patient.open_tasks)), element('td', '', patient.last_message || STRINGS.noMessage)];
  cells[0].append(name);
  cells[3].append(statusChip(patient.plan_status));
  row.append(...cells);
  return row;
}

async function renderPatients() {
  showLoading();
  try {
    const response = await CareLoopAPI.listPatients();
    const view = document.getElementById('dashboard-view');
    const heading = element('h1', 'dashboard-heading', STRINGS.patients);
    if (!response.patients.length) { view.replaceChildren(heading, element('p', 'dashboard-state', STRINGS.emptyPatients)); return; }
    const wrap = element('div', 'table-wrap');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', STRINGS.patients);
    const table = element('table', 'table patient-table');
    table.append(element('caption', 'sr-only', STRINGS.patients));
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    [STRINGS.table.name, STRINGS.table.language, STRINGS.table.readingLevel, STRINGS.table.planStatus, STRINGS.table.openTasks, STRINGS.table.lastMessage].forEach((label) => { const header = element('th', '', label); header.scope = 'col'; headRow.append(header); });
    head.append(headRow);
    const body = document.createElement('tbody');
    sortPatients(response.patients).forEach((patient) => body.append(patientRow(patient)));
    table.append(head, body);
    wrap.append(table);
    view.replaceChildren(heading, wrap);
  } catch (error) { showError(error); }
}

function fieldId(path) {
  return `plan-field-${path.replace(/[^a-zA-Z0-9]+/g, '-')}`;
}

function issuesFor(path, issues) {
  return issues.filter((issue) => issue.field === path);
}

function appendIssueHints(container, path, issues) {
  issuesFor(path, issues).forEach((issue) => container.append(element('p', 'inline-issue', issue.issue)));
}

function appendSourceLine(line, sourceText) {
  const lineNode = element('span', 'note-line');
  if (!sourceText || !line.includes(sourceText)) {
    lineNode.textContent = line;
    return lineNode;
  }
  const start = line.indexOf(sourceText);
  lineNode.append(document.createTextNode(line.slice(0, start)), element('mark', 'note-highlight', sourceText), document.createTextNode(line.slice(start + sourceText.length)));
  return lineNode;
}

function renderSourceNote(plan) {
  const note = element('article', 'card plan-source');
  note.append(element('h2', 'card-title dashboard-heading', STRINGS.sourceNote));
  const sourceTexts = plan.verifier_issues.map((issue) => issue.source_text).filter(Boolean);
  const lines = element('ol', 'note-lines');
  const noteText = plan.source_note || STRINGS.noMessage;
  noteText.split(/\r?\n/).forEach((line) => {
    const item = document.createElement('li');
    item.append(appendSourceLine(line, sourceTexts.find((text) => line.includes(text))));
    lines.append(item);
  });
  note.append(lines);
  return note;
}

function renderPlanValue(value, path, editing, issues, label = path) {
  const wrapper = element('div', 'plan-value');
  wrapper.id = fieldId(path);
  if (editing) {
    const input = element('input', 'input');
    input.value = Array.isArray(value) ? value.join(', ') : value ?? '';
    input.dataset.planPath = path;
    input.setAttribute('aria-label', label);
    wrapper.append(input);
  } else wrapper.append(element('span', '', Array.isArray(value) ? value.join(', ') : value ?? STRINGS.noMessage));
  appendIssueHints(wrapper, path, issues);
  return wrapper;
}

function renderPlanCollection(title, collection, fields, editing, issues) {
  const section = element('section', 'card plan-section');
  section.append(element('h2', 'card-title dashboard-heading', title));
  if (!collection.length) { section.append(element('p', 'card-copy', STRINGS.noMessage)); return section; }
  collection.forEach((item, index) => {
    const itemNode = element('article', 'plan-record');
    fields.forEach((field) => {
      const row = element('div', 'plan-field');
      row.append(element('strong', '', STRINGS.planLabels[field] || field), renderPlanValue(item[field], `${collection._name}[${index}].${field}`, editing, issues, `${title} ${index + 1}: ${STRINGS.planLabels[field] || field}`));
      itemNode.append(row);
    });
    section.append(itemNode);
  });
  return section;
}

function renderPlanSections(plan, editing) {
  const content = element('div', 'plan-sections');
  const medications = plan.medications || [];
  medications._name = 'medications';
  const appointments = plan.appointments || [];
  appointments._name = 'appointments';
  const tests = plan.tests || [];
  tests._name = 'tests';
  content.append(
    renderPlanCollection(STRINGS.planSections.medications, medications, ['name', 'dose', 'frequency', 'times', 'duration', 'instructions'], editing, plan.verifier_issues),
    renderPlanCollection(STRINGS.planSections.appointments, appointments, ['what', 'where', 'date', 'time'], editing, plan.verifier_issues),
    renderPlanCollection(STRINGS.planSections.tests, tests, ['name', 'where', 'date'], editing, plan.verifier_issues)
  );
  const symptoms = element('section', 'card plan-section');
  symptoms.append(element('h2', 'card-title dashboard-heading', STRINGS.planSections.symptoms));
  (plan.symptoms_to_watch || []).forEach((value, index) => symptoms.append(renderPlanValue(value, `symptoms_to_watch[${index}]`, editing, plan.verifier_issues, `${STRINGS.planSections.symptoms} ${index + 1}`)));
  if (!(plan.symptoms_to_watch || []).length) symptoms.append(element('p', 'card-copy', STRINGS.noMessage));
  const reminders = element('section', 'card plan-section');
  reminders.append(element('h2', 'card-title dashboard-heading', STRINGS.planSections.reminders));
  (plan.reminder_times || []).forEach((value, index) => reminders.append(renderPlanValue(value, `reminder_times[${index}]`, editing, plan.verifier_issues, `${STRINGS.planSections.reminders} ${index + 1}`)));
  if (!(plan.reminder_times || []).length) reminders.append(element('p', 'card-copy', STRINGS.noMessage));
  content.append(symptoms, reminders);
  return content;
}

function renderIssueList(plan) {
  const panel = element('section', 'verifier-panel');
  panel.append(element('h2', 'card-title dashboard-heading', STRINGS.verifierIssues));
  if (!plan.verifier_issues.length) { panel.append(element('p', '', STRINGS.noVerifierIssues)); return panel; }
  const list = element('ul', 'verifier-list');
  plan.verifier_issues.forEach((issue) => {
    const item = element('li');
    const button = element('button', 'issue-link', issue.issue);
    button.type = 'button';
    button.addEventListener('click', () => document.getElementById(fieldId(issue.field))?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    item.append(button, element('span', '', ` (${issue.field})`));
    list.append(item);
  });
  panel.append(list);
  return panel;
}

function setPlanValue(plan, path, value) {
  const parts = path.match(/[^.\[\]]+/g);
  let target = plan;
  parts.slice(0, -1).forEach((part) => { target = target[Number.isNaN(Number(part)) ? part : Number(part)]; });
  const finalKey = parts.at(-1);
  target[Number.isNaN(Number(finalKey)) ? finalKey : Number(finalKey)] = path.endsWith('.times') ? value.split(',').map((item) => item.trim()).filter(Boolean) : value;
}

async function approveReviewedPlan(plan, updates) {
  if (plan.verifier_issues.length && !window.confirm(STRINGS.approveConfirm)) return;
  const saved = updates ? await CareLoopAPI.updatePlan(plan.id, updates) : { plan };
  await CareLoopAPI.approvePlan(saved.plan.id, { override_issues: saved.plan.verifier_issues.length > 0 });
  showToast(STRINGS.sentToast);
  renderPlan(saved.plan.patient_id);
}

async function renderPlan(patientId, editing = false) {
  showLoading();
  try {
    const [patientResponse, planResponse] = await Promise.all([CareLoopAPI.getPatient(patientId), CareLoopAPI.getPlan(patientId)]);
    const patient = patientResponse.patient;
    const plan = planResponse.plan;
    const view = document.getElementById('dashboard-view');
    const back = element('a', 'back-link', STRINGS.backToPatients);
    back.href = '#patients';
    const heading = element('h1', 'dashboard-heading', STRINGS.planReview);
    const patientName = element('p', 'dashboard-subtitle', patient.name);
    const patientLanguage = element('p', 'dashboard-subtitle');
    patientLanguage.append(languageLabel(patient.language));
    const actions = element('div', 'cluster plan-actions');
    const approve = element('button', 'btn btn-success', STRINGS.approve);
    approve.type = 'button';
    approve.disabled = plan.status === 'approved';
    approve.addEventListener('click', async () => { try { await approveReviewedPlan(plan); } catch (error) { showError(error); } });
    const edit = element('button', 'btn btn-secondary', STRINGS.edit);
    edit.type = 'button';
    edit.addEventListener('click', () => renderPlan(patientId, true));
    actions.append(approve, edit);
    if (editing) {
      const save = element('button', 'btn btn-primary', STRINGS.saveAndApprove);
      save.type = 'button';
      save.addEventListener('click', async () => {
        try {
          const updates = JSON.parse(JSON.stringify(plan));
          view.querySelectorAll('[data-plan-path]').forEach((input) => setPlanValue(updates, input.dataset.planPath, input.value));
          await approveReviewedPlan(plan, updates);
        } catch (error) { showError(error); }
      });
      actions.append(save);
    }
    const fixedNote = element('aside', 'plan-safety-note', STRINGS.fixedSafetyNote);
    const review = element('div', 'plan-review-layout');
    const left = element('div', 'plan-note-column');
    const right = element('div', 'plan-content-column');
    left.append(renderSourceNote(plan));
    right.append(renderPlanSections(plan, editing));
    review.append(left, right);
    view.replaceChildren(back, heading, patientName, patientLanguage, statusChip(plan.status), actions, renderIssueList(plan), review, fixedNote);
  } catch (error) { showError(error); }
}

function escalationTone(ruleId) {
  return /missed|barrier/i.test(ruleId) ? 'escalation-amber' : 'escalation-red';
}

function escalationCard(escalation, activeFilter) {
  const card = element('article', `escalation-card ${escalationTone(escalation.rule_id)}`);
  const header = element('div', 'escalation-card-header');
  const identity = element('div');
  const language = element('p', 'card-copy');
  language.append(languageLabel(escalation.patient_language || STRINGS.noMessage));
  identity.append(element('h2', '', escalation.patient_name || escalation.patient_id), language);
  const meta = element('div', 'escalation-meta');
  meta.append(statusChip(escalation.status), element('time', '', escalation.created_at));
  header.append(identity, meta);
  const rule = element('p', 'escalation-rule');
  rule.append(element('strong', '', escalation.rule_label || escalation.rule_id), document.createTextNode(` (${escalation.rule_id})`));
  const original = element('section', 'escalation-copy');
  original.append(element('h3', '', STRINGS.originalMessage), element('p', '', escalation.original_text || STRINGS.noMessage));
  const english = element('section', 'escalation-copy');
  english.append(element('h3', '', STRINGS.englishVersion), element('p', '', escalation.english_text || STRINGS.noMessage));
  const brief = element('section', 'escalation-copy');
  brief.append(element('h3', '', STRINGS.summaryBrief));
  if (escalation.brief_ready && escalation.brief) brief.append(element('p', '', escalation.brief));
  else {
    const loading = element('p', 'brief-loading', STRINGS.briefLoading);
    loading.setAttribute('aria-live', 'polite');
    brief.append(loading);
    window.setTimeout(() => {
      if (currentRoute().name === 'escalations') renderEscalations(activeFilter);
    }, 5000);
  }
  const outstanding = element('section', 'escalation-copy');
  outstanding.append(element('h3', '', STRINGS.outstanding), element('p', '', escalation.outstanding || STRINGS.noMessage));
  card.append(header, rule, original, english, brief, outstanding);
  if (escalation.status !== 'resolved') {
    const form = element('form', 'escalation-resolve');
    const label = element('label', 'sr-only', STRINGS.resolutionNote);
    label.htmlFor = `resolution-${escalation.id}`;
    const note = element('input', 'input');
    note.id = `resolution-${escalation.id}`;
    note.type = 'text';
    note.placeholder = STRINGS.resolutionPlaceholder;
    const resolve = element('button', 'btn btn-success', STRINGS.markResolved);
    resolve.type = 'submit';
    form.append(label, note, resolve);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      resolve.disabled = true;
      resolve.textContent = STRINGS.resolving;
      try {
        await CareLoopAPI.resolveEscalation(escalation.id, { note: note.value.trim(), resolved_by: STRINGS.reviewerName });
        refreshEscalationBadge();
        renderEscalations(activeFilter);
      } catch (error) {
        resolve.disabled = false;
        resolve.textContent = STRINGS.markResolved;
        showError(error);
      }
    });
    card.append(form);
  }
  return card;
}

async function renderEscalations(activeFilter = 'open') {
  showLoading();
  try {
    const response = await CareLoopAPI.listEscalations(activeFilter === 'all' ? {} : { status: activeFilter });
    const view = document.getElementById('dashboard-view');
    const heading = element('h1', 'dashboard-heading', STRINGS.escalations);
    const filters = element('div', 'cluster escalation-filters');
    filters.setAttribute('role', 'group');
    filters.setAttribute('aria-label', STRINGS.filtersLabel);
    ['open', 'resolved', 'all'].forEach((filter) => {
      const button = element('button', `btn ${filter === activeFilter ? 'btn-primary' : 'btn-secondary'}`, STRINGS.escalationFilters[filter]);
      button.type = 'button';
      button.setAttribute('aria-pressed', String(filter === activeFilter));
      button.addEventListener('click', () => renderEscalations(filter));
      filters.append(button);
    });
    if (!response.escalations.length) { view.replaceChildren(heading, filters, element('p', 'dashboard-state', STRINGS.emptyEscalations)); return; }
    const cards = element('div', 'escalation-list');
    [...response.escalations].sort((first, second) => new Date(second.created_at) - new Date(first.created_at)).forEach((escalation) => cards.append(escalationCard(escalation, activeFilter)));
    view.replaceChildren(heading, filters, cards);
  } catch (error) { showError(error); }
}

async function refreshEscalationBadge() {
  try {
    const response = await CareLoopAPI.listEscalations({ status: 'open' });
    const badge = document.getElementById('escalation-count');
    if (badge) { badge.textContent = String(response.escalations.length); badge.setAttribute('aria-label', STRINGS.escalationCount(response.escalations.length)); }
  } catch (error) { /* A route render will show request errors in context. */ }
}

function closeModal() {
  document.getElementById('patient-modal')?.remove();
  document.querySelector('.app-shell')?.removeAttribute('inert');
  modalReturnFocus?.focus();
  modalReturnFocus = null;
}

function showAddPatientModal() {
  modalReturnFocus = document.activeElement;
  const backdrop = element('div', 'modal-backdrop');
  backdrop.id = 'patient-modal';
  const modal = element('section', 'modal dashboard-modal');
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'patient-modal-title');
  const heading = element('h2', 'dashboard-heading', STRINGS.modal.title);
  heading.id = 'patient-modal-title';
  const close = element('button', 'btn btn-ghost modal-close', STRINGS.modal.close);
  close.type = 'button';
  close.addEventListener('click', closeModal);
  const modalHeader = element('div', 'modal-header');
  modalHeader.append(heading, close);
  const form = element('form', 'stack');
  const fields = [
    ['name', STRINGS.modal.name, 'text'], ['phone', STRINGS.modal.phone, 'tel']
  ];
  fields.forEach(([id, labelText, type]) => {
    const field = element('div', 'field');
    const label = element('label', '', labelText);
    label.htmlFor = `patient-${id}`;
    const input = element('input', 'input');
    input.id = `patient-${id}`;
    input.name = id;
    input.type = type;
    if (id === 'phone') input.value = '+2348000000000';
    field.append(label, input);
    form.append(field);
  });
  const languageField = element('div', 'field');
  const languageLabel = element('label', '', STRINGS.modal.language);
  languageLabel.htmlFor = 'patient-language';
  const language = element('select', 'select');
  language.id = 'patient-language';
  language.name = 'language';
  ['English', 'Pidgin', 'Hausa', 'Yoruba', 'Igbo'].forEach((value) => { const option = element('option', '', value === 'Pidgin' ? `${value} (${STRINGS.beta})` : value); option.value = value; language.append(option); });
  languageField.append(languageLabel, language);
  const languageBeta = element('span', 'status-chip status-beta', STRINGS.beta);
  languageBeta.hidden = language.value !== 'Pidgin';
  languageField.append(languageBeta);
  language.addEventListener('change', () => { languageBeta.hidden = language.value !== 'Pidgin'; });
  const readingField = element('div', 'field');
  const readingLabel = element('label', '', STRINGS.modal.reading);
  readingLabel.htmlFor = 'patient-reading';
  const reading = element('select', 'select');
  reading.id = 'patient-reading';
  reading.name = 'reading';
  ['basic', 'standard', 'caregiver'].forEach((value) => { const option = element('option', '', value); option.value = value; reading.append(option); });
  readingField.append(readingLabel, reading);
  const caregiverRow = element('div', 'checkbox-row');
  const caregiver = element('input', 'checkbox');
  caregiver.id = 'patient-caregiver';
  caregiver.name = 'caregiver';
  caregiver.type = 'checkbox';
  const caregiverLabel = element('label', 'checkbox-label', STRINGS.modal.caregiver);
  caregiverLabel.htmlFor = caregiver.id;
  caregiverRow.append(caregiver, caregiverLabel);
  const sampleField = element('div', 'field');
  const sampleLabel = element('label', '', STRINGS.modal.sample);
  sampleLabel.htmlFor = 'patient-sample';
  const sample = element('select', 'select');
  sample.id = 'patient-sample';
  const placeholder = element('option', '', STRINGS.modal.chooseSample);
  placeholder.value = '';
  sample.append(placeholder);
  SAMPLE_NOTES.forEach((item, index) => { const option = element('option', '', item.title); option.value = String(index); sample.append(option); });
  sampleField.append(sampleLabel, sample);
  const noteField = element('div', 'field');
  const noteLabel = element('label', '', STRINGS.modal.note);
  noteLabel.htmlFor = 'patient-note';
  const note = element('textarea', 'textarea');
  note.id = 'patient-note';
  note.name = 'note';
  noteField.append(noteLabel, note);
  sample.addEventListener('change', () => { if (sample.value) note.value = SAMPLE_NOTES[Number(sample.value)].text; });
  const error = element('p', 'dashboard-error');
  error.hidden = true;
  error.setAttribute('role', 'alert');
  const actions = element('div', 'flow-actions');
  const cancel = element('button', 'btn btn-ghost', STRINGS.modal.cancel);
  cancel.type = 'button';
  cancel.addEventListener('click', closeModal);
  const submit = element('button', 'btn btn-primary', STRINGS.modal.submit);
  submit.type = 'submit';
  actions.append(cancel, submit);
  form.append(languageField, readingField, caregiverRow, sampleField, noteField, error, actions);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const nameInput = form.elements.namedItem('name');
    const phoneInput = form.elements.namedItem('phone');
    if (!nameInput.value.trim() || !note.value.trim()) { error.textContent = STRINGS.modal.required; error.hidden = false; return; }
    submit.disabled = true;
    submit.textContent = STRINGS.modal.creating;
    error.hidden = true;
    try {
      const patientResponse = await CareLoopAPI.createPatient({ name: nameInput.value.trim(), phone_e164: phoneInput.value.trim(), language: language.value, literacy_level: reading.value, caregiver_mode: caregiver.checked });
      await CareLoopAPI.createPlan({ patient_id: patientResponse.patient.id, source_note: note.value.trim(), status: 'needs_review', verifier_issues: [], medications: [], appointments: [], tests: [], symptoms_to_watch: [], reminder_times: [] });
      closeModal();
      showToast(STRINGS.toast);
      window.location.hash = `#plan/${encodeURIComponent(patientResponse.patient.id)}`;
    } catch (requestError) {
      error.textContent = `${STRINGS.errorPrefix}${requestError.message}`;
      error.hidden = false;
      submit.disabled = false;
      submit.textContent = STRINGS.modal.submit;
    }
  });
  modal.append(modalHeader, form);
  backdrop.append(modal);
  app.append(backdrop);
  document.querySelector('.app-shell')?.setAttribute('inert', '');
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeModal(); });
  modal.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault(); closeModal(); return; }
    if (event.key !== 'Tab') return;
    const focusable = [...modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]')];
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!modal.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
    else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  form.elements.namedItem('name').focus();
}

function renderRoute() {
  renderShell();
  const route = currentRoute();
  const rendered = route.name === 'plan' ? renderPlan(route.patientId) : route.name === 'escalations' ? renderEscalations() : renderPatients();
  rendered.then(() => {
    const heading = document.querySelector('#dashboard-view h1');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  });
  refreshEscalationBadge();
}

function start() {
  document.title = STRINGS.pageTitle;
  if (!window.location.hash) window.location.hash = '#patients';
  window.addEventListener('hashchange', renderRoute);
  renderRoute();
  refreshEscalationBadge();
  escalationTimer = window.setInterval(refreshEscalationBadge, 15000);
}

start();
