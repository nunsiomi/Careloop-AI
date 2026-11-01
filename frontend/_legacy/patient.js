const VALIDATED_LANGUAGES = ['simple-english', 'hausa', 'yoruba', 'igbo'];

const STRINGS = {
  pageTitle: 'CareLoop patient chat',
  loading: 'Loading…',
  errorPrefix: 'We could not continue: ',
  back: 'Back',
  next: 'Next',
  finish: 'I agree',
  language: {
    title: 'Choose your language',
    description: 'You can change this later.',
    options: [
      { id: 'simple-english', value: 'English', local: 'Simple English', english: 'Simple English' },
      { id: 'pidgin', value: 'Pidgin', local: 'Naija Pidgin', english: 'Nigerian Pidgin' },
      { id: 'hausa', value: 'Hausa', local: 'Hausa', english: 'Hausa' },
      { id: 'yoruba', value: 'Yoruba', local: 'Yorùbá', english: 'Yoruba' },
      { id: 'igbo', value: 'Igbo', local: 'Igbo', english: 'Igbo' }
    ]
  },
  reading: {
    title: 'Choose how you want to read',
    description: 'This helps CareLoop use the right amount of detail.',
    options: [
      { id: 'basic', title: 'Basic', description: 'Short, simple messages.' },
      { id: 'standard', title: 'Standard', description: 'Regular detail in clear language.' },
      { id: 'caregiver', title: 'Caregiver', description: 'For someone helping with care.' }
    ]
  },
  notice: {
    title: 'Before you begin',
    description: 'Please read this notice.',
    points: [
      'You are chatting with an AI assistant.',
      'It only repeats what your care team wrote.',
      'It does not give new medical advice.',
      'A human reviews urgent cases.'
    ]
  },
  consent: {
    title: 'Your consent',
    description: 'Please choose whether to start CareLoop chat.',
    checkbox: 'I agree to use CareLoop chat.',
    decline: 'No, thanks',
    channels: ['web']
  },
  declined: {
    title: 'That is okay',
    body: 'Nothing will be sent.',
    later: 'To change this later, ask your care team to help you start CareLoop chat.',
    home: 'Return home'
  },
  chat: {
    title: 'CareLoop',
    aiTag: 'AI assistant',
    languageChip: (language) => `Language: ${language}`,
    footer: 'This is an AI assistant. If you feel very unwell, go to the nearest hospital now.',
    messagesLabel: 'Conversation',
    changeLanguage: 'Change language',
    empty: 'No messages yet.',
    inputLabel: 'Your message',
    inputPlaceholder: 'Write a message',
    send: 'Send',
    sending: 'Sending…',
    typing: 'CareLoop is typing',
    welcome: 'Here is the care plan your team approved.',
    numberExact: 'Shown in English to keep your dose details exact.',
    plan: {
      medicines: 'Medicines',
      visits: 'Visits',
      tests: 'Tests',
      warningSigns: 'Warning signs',
      dose: 'Dose',
      when: 'When to take it',
      where: 'Where',
      date: 'Date',
      time: 'Time'
    },
    waitingTitle: 'Your care team is checking your plan',
    waitingCopy: 'We will show it here when it is ready.',
    reminder: {
      done: 'Done',
      notYet: 'Not yet',
      problem: 'Problem',
      cost: 'Cost',
      transport: 'Transport',
      stock: 'Medicine not in stock',
      understand: 'I do not understand',
      other: 'Other (free text)',
      otherLabel: 'Describe the problem',
      otherPlaceholder: 'Write your problem',
      otherSend: 'Send problem'
    },
    barrier: {
      attempt: (attempts) => `Attempt ${attempts} of 2`,
      detailLabel: (label) => `${label}: `,
      type: 'Type',
      price: 'Price',
      distance: 'Distance',
      phone: 'Phone',
      worked: 'It worked',
      didNotWork: 'It did not work'
    },
    escalation: {
      notified: 'A human reviewer has been notified',
      call: 'Call now'
    },
    demo: {
      menu: 'Menu',
      title: 'Demo controls',
      sendReminder: 'Send next reminder now',
      missedTask: 'Simulate missed task',
      reset: 'Reset demo'
    }
  },
  beta: 'Beta',
  step: (current) => `Step ${current} of 4`
};

const app = document.getElementById('app');
const requestedPatientId = new URLSearchParams(window.location.search).get('patient') || '1';
const demoEnabled = CareLoopAPI.USE_MOCKS || new URLSearchParams(window.location.search).get('demo') === '1';
const state = { patient: null, step: 1, language: null, readingLevel: null, consentAccepted: false, editingPreferences: false };
let planPoll = null;
let chatRenderId = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clearApp() {
  app.replaceChildren();
}

function isValidatedLanguage(language) {
  return STRINGS.language.options.some((option) => option.value === language && VALIDATED_LANGUAGES.includes(option.id));
}

function stopPlanPolling() {
  if (planPoll) window.clearTimeout(planPoll);
  planPoll = null;
}

function showError(error) {
  document.querySelector('.patient-error')?.remove();
  const message = element('p', 'patient-error', `${STRINGS.errorPrefix}${error.message}`);
  message.setAttribute('role', 'alert');
  (document.getElementById('chat-messages') || app).append(message);
}

function appendSafetyFooter() {
  app.append(element('footer', 'patient-footer', STRINGS.chat.footer));
}

function flowFrame(title, description) {
  stopPlanPolling();
  clearApp();
  const flow = element('section', 'patient-flow');
  const progress = element('p', 'patient-progress', STRINGS.step(state.step));
  const heading = element('h1', 'patient-heading', title);
  const copy = element('p', 'patient-copy', description);
  heading.tabIndex = -1;
  flow.append(progress, heading, copy);
  app.append(flow);
  appendSafetyFooter();
  heading.focus({ preventScroll: true });
  return flow;
}

function addActions(flow, nextLabel, onNext) {
  const actions = element('div', 'flow-actions');
  const back = element('button', 'btn btn-ghost', STRINGS.back);
  back.type = 'button';
  back.addEventListener('click', () => {
    if (state.step === 1 && state.editingPreferences) {
      state.editingPreferences = false;
      renderChat();
    } else if (state.step === 1) window.location.href = 'index.html';
    else { state.step -= 1; renderStep(); }
  });
  const next = element('button', 'btn btn-primary', nextLabel);
  next.type = 'button';
  next.addEventListener('click', onNext);
  actions.append(back, next);
  flow.append(actions);
  return next;
}

function renderLanguage() {
  const flow = flowFrame(STRINGS.language.title, STRINGS.language.description);
  const choices = element('fieldset', 'choice-list');
  choices.append(element('legend', 'sr-only', STRINGS.language.title));
  STRINGS.language.options.forEach((option) => {
    const input = element('input', 'choice-input');
    input.type = 'radio';
    input.name = 'language';
    input.id = `language-${option.id}`;
    input.value = option.value;
    input.checked = state.language === option.value;
    input.addEventListener('change', () => { state.language = option.value; });
    const label = element('label', 'choice-card');
    label.htmlFor = input.id;
    label.append(element('strong', '', option.local), element('span', '', option.english));
    if (!VALIDATED_LANGUAGES.includes(option.id)) label.append(element('span', 'status-chip status-beta', STRINGS.beta));
    choices.append(input, label);
  });
  flow.append(choices);
  const next = addActions(flow, STRINGS.next, () => {
    if (!state.language) return;
    state.step = 2;
    renderStep();
  });
  next.disabled = !state.language;
  choices.addEventListener('change', () => { next.disabled = !state.language; });
}

function renderReading() {
  const flow = flowFrame(STRINGS.reading.title, STRINGS.reading.description);
  const choices = element('fieldset', 'choice-list');
  choices.append(element('legend', 'sr-only', STRINGS.reading.title));
  STRINGS.reading.options.forEach((option) => {
    const input = element('input', 'choice-input');
    input.type = 'radio';
    input.name = 'reading-level';
    input.id = `reading-${option.id}`;
    input.value = option.id;
    input.checked = state.readingLevel === option.id;
    input.addEventListener('change', () => { state.readingLevel = option.id; });
    const label = element('label', 'choice-card');
    label.htmlFor = input.id;
    label.append(element('strong', '', option.title), element('span', '', option.description));
    choices.append(input, label);
  });
  flow.append(choices);
  const next = addActions(flow, STRINGS.next, () => {
    if (!state.readingLevel) return;
    if (state.editingPreferences) savePreferences();
    else { state.step = 3; renderStep(); }
  });
  next.disabled = !state.readingLevel;
  choices.addEventListener('change', () => { next.disabled = !state.readingLevel; });
}

function renderNotice() {
  const flow = flowFrame(STRINGS.notice.title, STRINGS.notice.description);
  const list = element('ul', 'notice-list');
  STRINGS.notice.points.forEach((point) => list.append(element('li', '', point)));
  flow.append(list);
  addActions(flow, STRINGS.next, () => { state.step = 4; renderStep(); });
}

function renderConsent() {
  const flow = flowFrame(STRINGS.consent.title, STRINGS.consent.description);
  const box = element('div', 'consent-box');
  const row = element('div', 'checkbox-row');
  const input = element('input', 'checkbox');
  input.type = 'checkbox';
  input.id = 'consent';
  input.checked = state.consentAccepted;
  const label = element('label', 'checkbox-label', STRINGS.consent.checkbox);
  label.htmlFor = input.id;
  row.append(input, label);
  box.append(row);
  flow.append(box);
  const finish = addActions(flow, STRINGS.finish, finishOnboarding);
  finish.disabled = !state.consentAccepted;
  input.addEventListener('change', () => { state.consentAccepted = input.checked; finish.disabled = !state.consentAccepted; });
  const decline = element('button', 'btn btn-ghost', STRINGS.consent.decline);
  decline.type = 'button';
  decline.addEventListener('click', renderDeclined);
  flow.querySelector('.flow-actions').prepend(decline);
}

async function finishOnboarding() {
  try {
    await CareLoopAPI.updateProfile(state.patient.id, {
      language: state.language,
      literacy_level: state.readingLevel,
      caregiver_mode: state.readingLevel === 'caregiver'
    });
    await CareLoopAPI.recordConsent(state.patient.id, { channels: STRINGS.consent.channels, scope: 'patient_chat', version: 'v1' });
    state.patient.consent_at = new Date().toISOString();
    renderChat();
  } catch (error) {
    showError(error);
  }
}

async function savePreferences() {
  try {
    const response = await CareLoopAPI.updateProfile(state.patient.id, {
      language: state.language,
      literacy_level: state.readingLevel,
      caregiver_mode: state.readingLevel === 'caregiver'
    });
    state.patient = response.patient;
    state.editingPreferences = false;
    renderChat();
  } catch (error) {
    showError(error);
  }
}

function renderDeclined() {
  stopPlanPolling();
  clearApp();
  const screen = element('section', 'patient-flow quiet-screen card');
  screen.append(element('h1', 'patient-heading', STRINGS.declined.title), element('p', 'patient-copy', STRINGS.declined.body), element('p', 'patient-copy', STRINGS.declined.later));
  const home = element('a', 'btn btn-secondary', STRINGS.declined.home);
  home.href = 'index.html';
  screen.append(home);
  app.append(screen);
  appendSafetyFooter();
}

function scrollChatToNewest() {
  const messages = document.getElementById('chat-messages');
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function appendTyping() {
  const messages = document.getElementById('chat-messages');
  const typing = element('div', 'typing-indicator');
  typing.setAttribute('role', 'status');
  typing.setAttribute('aria-label', STRINGS.chat.typing);
  typing.append(element('span'), element('span'), element('span'));
  messages.append(typing);
  scrollChatToNewest();
  return typing;
}

function disableBubbleButtons(container) {
  container.querySelectorAll('button').forEach((button) => { button.disabled = true; });
}

function addBarrierDetail(card, label, value) {
  if (value === undefined || value === null || value === '') return;
  const detail = element('p', 'barrier-detail');
  detail.append(element('strong', '', STRINGS.chat.barrier.detailLabel(label)), document.createTextNode(value));
  card.append(detail);
}

function addBarrierReply(barrier) {
  const messages = document.getElementById('chat-messages');
  const panel = element('section', 'barrier-panel');
  panel.append(element('p', 'barrier-attempt', STRINGS.chat.barrier.attempt(barrier.attempts)));
  barrier.options.forEach((option) => {
    const optionCard = element('article', 'barrier-option');
    const optionData = typeof option === 'string' ? { name: option } : option;
    optionCard.append(element('h3', '', optionData.name));
    addBarrierDetail(optionCard, STRINGS.chat.barrier.type, optionData.type);
    addBarrierDetail(optionCard, STRINGS.chat.barrier.price, optionData.price);
    addBarrierDetail(optionCard, STRINGS.chat.barrier.distance, optionData.distance);
    if (optionData.phone) {
      const phone = element('a', 'barrier-phone', optionData.phone);
      phone.href = `tel:${optionData.phone}`;
      const phoneDetail = element('p', 'barrier-detail');
      phoneDetail.append(element('strong', '', STRINGS.chat.barrier.detailLabel(STRINGS.chat.barrier.phone)), phone);
      optionCard.append(phoneDetail);
    }
    panel.append(optionCard);
  });
  const actions = element('div', 'bubble-actions');
  const worked = element('button', 'btn btn-success', STRINGS.chat.barrier.worked);
  const didNotWork = element('button', 'btn btn-secondary', STRINGS.chat.barrier.didNotWork);
  worked.type = 'button';
  didNotWork.type = 'button';
  worked.addEventListener('click', () => sendChatText(STRINGS.chat.barrier.worked, { container: actions, keepDisabled: true }));
  didNotWork.addEventListener('click', () => sendChatText(STRINGS.chat.barrier.didNotWork, { container: actions, keepDisabled: true }));
  actions.append(worked, didNotWork);
  panel.append(actions);
  messages.append(panel);
  scrollChatToNewest();
}

function pinEscalation(response) {
  if (!response.escalation) return;
  const existing = document.getElementById('chat-escalation');
  if (existing) existing.remove();
  const banner = element('aside', 'emergency-banner chat-escalation');
  banner.id = 'chat-escalation';
  banner.setAttribute('role', 'alert');
  const content = element('div');
  content.append(element('p', '', response.reply.original_text), element('p', '', STRINGS.chat.escalation.notified));
  const call = element('a', 'btn btn-secondary', STRINGS.chat.escalation.call);
  call.href = `tel:${response.escalation.call_number}`;
  banner.append(content, call);
  document.querySelector('.chat-form').before(banner);
}

function renderResponseExtras(response) {
  if (response.barrier) addBarrierReply(response.barrier);
  if (response.escalation) pinEscalation(response);
}

async function sendChatText(text, options = {}) {
  const container = options.container;
  if (container) disableBubbleButtons(container);
  const typing = appendTyping();
  try {
    const response = await CareLoopAPI.sendMessage(state.patient.id, { original_text: text, language: state.patient.language });
    addChatMessage({ direction: 'patient', original_text: text });
    addChatMessage({ direction: 'careloop', ...response.reply });
    renderResponseExtras(response);
    return response;
  } catch (error) {
    if (container && !options.keepDisabled) container.querySelectorAll('button').forEach((button) => { button.disabled = false; });
    showError(error);
    return null;
  } finally {
    typing.remove();
    if (container) document.getElementById('chat-messages')?.focus({ preventScroll: true });
  }
}

function showOtherProblemInput(choices) {
  choices.replaceChildren();
  const label = element('label', 'sr-only', STRINGS.chat.reminder.otherLabel);
  label.htmlFor = 'other-problem';
  const input = element('input', 'input');
  input.id = 'other-problem';
  input.type = 'text';
  input.placeholder = STRINGS.chat.reminder.otherPlaceholder;
  const send = element('button', 'btn btn-primary', STRINGS.chat.reminder.otherSend);
  send.type = 'button';
  send.addEventListener('click', () => {
    const text = input.value.trim();
    if (text) sendChatText(text, { container: choices.parentElement, keepDisabled: true });
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); send.click(); }
  });
  choices.append(label, input, send);
  input.focus();
}

function showProblemChoices(actions) {
  disableBubbleButtons(actions);
  const choicesPanel = element('div', 'problem-choices');
  const choices = [
    STRINGS.chat.reminder.cost,
    STRINGS.chat.reminder.transport,
    STRINGS.chat.reminder.stock,
    STRINGS.chat.reminder.understand,
    STRINGS.chat.reminder.other
  ];
  choices.forEach((choice) => {
    const button = element('button', 'btn btn-secondary', choice);
    button.type = 'button';
    button.addEventListener('click', () => {
      if (choice === STRINGS.chat.reminder.other) showOtherProblemInput(choicesPanel);
      else sendChatText(choice, { container: actions, keepDisabled: true });
    });
    choicesPanel.append(button);
  });
  actions.append(choicesPanel);
  choicesPanel.querySelector('button').focus();
}

function addReminderActions(bubble) {
  const actions = element('div', 'bubble-actions');
  const done = element('button', 'btn btn-success', STRINGS.chat.reminder.done);
  const notYet = element('button', 'btn btn-secondary', STRINGS.chat.reminder.notYet);
  const problem = element('button', 'btn btn-secondary', STRINGS.chat.reminder.problem);
  done.type = 'button';
  notYet.type = 'button';
  problem.type = 'button';
  done.addEventListener('click', () => sendChatText(STRINGS.chat.reminder.done, { container: actions, keepDisabled: true }));
  notYet.addEventListener('click', () => sendChatText(STRINGS.chat.reminder.notYet, { container: actions, keepDisabled: true }));
  problem.addEventListener('click', () => showProblemChoices(actions));
  actions.append(done, notYet, problem);
  bubble.append(actions);
}

async function runDemoAction(action) {
  try {
    if (action === 'reminder') {
      const response = await CareLoopAPI.sendNextReminder(state.patient.id);
      addChatMessage(response.message);
    } else if (action === 'missed') {
      const response = await CareLoopAPI.simulateMissedTask(state.patient.id);
      addChatMessage(response.message);
    } else {
      await CareLoopAPI.resetDemo();
      window.location.reload();
    }
  } catch (error) {
    showError(error);
  }
}

function createDemoDrawer() {
  const drawer = element('section', 'demo-drawer');
  drawer.hidden = true;
  drawer.setAttribute('aria-label', STRINGS.chat.demo.title);
  drawer.append(element('h2', '', STRINGS.chat.demo.title));
  const reminder = element('button', 'btn btn-secondary', STRINGS.chat.demo.sendReminder);
  const missed = element('button', 'btn btn-secondary', STRINGS.chat.demo.missedTask);
  const reset = element('button', 'btn btn-secondary', STRINGS.chat.demo.reset);
  reminder.type = 'button';
  missed.type = 'button';
  reset.type = 'button';
  reminder.addEventListener('click', () => runDemoAction('reminder'));
  missed.addEventListener('click', () => runDemoAction('missed'));
  reset.addEventListener('click', () => runDemoAction('reset'));
  drawer.append(reminder, missed, reset);
  return drawer;
}

function addChatMessage(message) {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;
  const direction = message.direction === 'patient' ? 'chat-patient' : 'chat-careloop';
  const bubble = element('div', `chat-bubble ${direction}`);
  bubble.append(element('p', '', message.original_text));
  if (message.direction !== 'patient' && message.number_check_passed === false) {
    bubble.append(element('p', 'chat-number-note', STRINGS.chat.numberExact));
  }
  if (message.task) addReminderActions(bubble);
  messages.append(bubble);
  scrollChatToNewest();
}

function addPlanDetail(card, label, value) {
  if (value === undefined || value === null || value === '') return;
  const detail = element('div', 'plan-detail');
  detail.append(element('strong', '', label), element('span', '', value));
  card.append(detail);
}

function addPlanGroup(messages, title, items, renderItem) {
  if (!items.length) return;
  const group = element('section', 'plan-group');
  group.dataset.planContent = 'true';
  group.append(element('h2', '', title));
  items.forEach((item) => group.append(renderItem(item)));
  messages.append(group);
}

function medicineCard(medicine) {
  const card = element('article', 'plan-item');
  card.append(element('h3', '', medicine.name));
  addPlanDetail(card, STRINGS.chat.plan.dose, medicine.dose);
  addPlanDetail(card, STRINGS.chat.plan.when, medicine.frequency);
  if (medicine.times?.length) {
    const pills = element('div', 'time-pills');
    medicine.times.forEach((time) => pills.append(element('span', 'time-pill', time)));
    card.append(pills);
  }
  return card;
}

function visitCard(appointment) {
  const card = element('article', 'plan-item');
  card.append(element('h3', '', appointment.what));
  addPlanDetail(card, STRINGS.chat.plan.where, appointment.where);
  addPlanDetail(card, STRINGS.chat.plan.date, appointment.date);
  addPlanDetail(card, STRINGS.chat.plan.time, appointment.time);
  return card;
}

function testCard(test) {
  const card = element('article', 'plan-item');
  card.append(element('h3', '', test.name));
  addPlanDetail(card, STRINGS.chat.plan.where, test.where);
  addPlanDetail(card, STRINGS.chat.plan.date, test.date);
  return card;
}

function warningCard(sign) {
  const card = element('article', 'plan-item plan-warning');
  card.append(element('p', '', sign));
  return card;
}

function clearPlanContent(messages) {
  messages.querySelectorAll('[data-plan-content="true"]').forEach((item) => item.remove());
}

function renderWaitingPlan(messages) {
  clearPlanContent(messages);
  messages.querySelector('.chat-empty')?.remove();
  const waiting = element('article', 'plan-item plan-waiting');
  waiting.dataset.planContent = 'true';
  waiting.append(element('h2', '', STRINGS.chat.waitingTitle), element('p', '', STRINGS.chat.waitingCopy));
  messages.append(waiting);
  scrollChatToNewest();
}

function renderApprovedPlan(messages, plan) {
  clearPlanContent(messages);
  messages.querySelector('.chat-empty')?.remove();
  const welcome = element('div', 'chat-bubble chat-careloop');
  welcome.dataset.planContent = 'true';
  welcome.append(element('p', '', STRINGS.chat.welcome));
  messages.append(welcome);
  addPlanGroup(messages, STRINGS.chat.plan.medicines, plan.medications || [], medicineCard);
  addPlanGroup(messages, STRINGS.chat.plan.visits, plan.appointments || [], visitCard);
  addPlanGroup(messages, STRINGS.chat.plan.tests, plan.tests || [], testCard);
  addPlanGroup(messages, STRINGS.chat.plan.warningSigns, plan.symptoms_to_watch || [], warningCard);
  scrollChatToNewest();
}

async function loadPlanForChat(renderId, messages) {
  try {
    const response = await CareLoopAPI.getPlan(state.patient.id);
    if (renderId !== chatRenderId) return;
    if (response.plan.status === 'needs_review') {
      renderWaitingPlan(messages);
      planPoll = window.setTimeout(() => loadPlanForChat(renderId, messages), 10000);
    } else {
      renderApprovedPlan(messages, response.plan);
    }
  } catch (error) {
    if (renderId === chatRenderId) showError(error);
  }
}

async function renderChat() {
  stopPlanPolling();
  const renderId = ++chatRenderId;
  clearApp();
  const shell = element('section', 'chat-shell');
  const header = element('header', 'chat-header');
  const headerMain = element('div', 'chat-header-main');
  headerMain.append(element('h1', '', STRINGS.chat.title), element('span', 'chat-ai-tag', STRINGS.chat.aiTag));
  const headerActions = element('div', 'chat-header-actions');
  const languageChip = element('button', 'chat-language-chip');
  languageChip.append(element('span', '', STRINGS.chat.languageChip(state.patient.language)));
  if (!isValidatedLanguage(state.patient.language)) languageChip.append(element('span', 'status-chip status-beta', STRINGS.beta));
  languageChip.append(element('span', 'sr-only', ` ${STRINGS.chat.changeLanguage}`));
  languageChip.type = 'button';
  languageChip.addEventListener('click', () => {
    state.editingPreferences = true;
    state.step = 1;
    state.language = state.patient.language;
    state.readingLevel = STRINGS.reading.options.some((option) => option.id === state.patient.literacy_level)
      ? state.patient.literacy_level
      : STRINGS.reading.options[0].id;
    renderStep();
  });
  headerActions.append(languageChip);
  const demoDrawer = demoEnabled ? createDemoDrawer() : null;
  if (demoDrawer) {
    const menu = element('button', 'chat-menu-button', STRINGS.chat.demo.menu);
    menu.type = 'button';
    menu.setAttribute('aria-expanded', 'false');
    menu.addEventListener('click', () => {
      demoDrawer.hidden = !demoDrawer.hidden;
      menu.setAttribute('aria-expanded', String(!demoDrawer.hidden));
    });
    headerActions.append(menu);
    shell.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !demoDrawer.hidden) {
        demoDrawer.hidden = true;
        menu.setAttribute('aria-expanded', 'false');
        menu.focus();
      }
    });
  }
  header.append(headerMain, headerActions);
  if (demoDrawer) header.append(demoDrawer);
  const messages = element('div', 'chat-messages');
  messages.id = 'chat-messages';
  messages.setAttribute('role', 'log');
  messages.setAttribute('aria-label', STRINGS.chat.messagesLabel);
  messages.tabIndex = 0;
  const form = element('form', 'chat-form');
  const inputLabel = element('label', 'sr-only', STRINGS.chat.inputLabel);
  inputLabel.htmlFor = 'chat-message';
  const input = element('input', 'input');
  input.id = 'chat-message';
  input.name = 'message';
  input.type = 'text';
  input.placeholder = STRINGS.chat.inputPlaceholder;
  input.autocomplete = 'off';
  const send = element('button', 'btn btn-primary', STRINGS.chat.send);
  send.type = 'submit';
  form.append(inputLabel, input, send);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const empty = messages.querySelector('.chat-empty');
    if (empty) empty.remove();
    send.disabled = true;
    send.textContent = STRINGS.chat.sending;
    try {
      const response = await sendChatText(text);
      if (response) input.value = '';
    } finally {
      send.disabled = false;
      send.textContent = STRINGS.chat.send;
      input.focus();
    }
  });
  shell.append(header);
  const footer = element('footer', 'chat-footer', STRINGS.chat.footer);
  shell.append(messages, footer, form);
  app.append(shell);

  try {
    const response = await CareLoopAPI.getMessages(state.patient.id);
    if (renderId !== chatRenderId) return;
    if (!response.messages.length && !messages.children.length) messages.append(element('p', 'chat-empty', STRINGS.chat.empty));
    else response.messages.forEach(addChatMessage);
    await loadPlanForChat(renderId, messages);
  } catch (error) {
    if (renderId === chatRenderId) showError(error);
  }
}

function renderStep() {
  if (state.step === 1) renderLanguage();
  else if (state.step === 2) renderReading();
  else if (state.step === 3) renderNotice();
  else renderConsent();
}

async function start() {
  document.title = STRINGS.pageTitle;
  clearApp();
  app.append(element('p', 'patient-flow patient-copy', STRINGS.loading));
  try {
    const response = await CareLoopAPI.getPatient(requestedPatientId);
    state.patient = response.patient;
    if (state.patient.consent_at) renderChat();
    else {
      state.language = state.patient.language || null;
      renderStep();
    }
  } catch (error) {
    clearApp();
    showError(error);
  }
}

start();
