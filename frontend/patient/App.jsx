import { useCallback, useEffect, useRef, useState } from 'react';
import { CalendarDays, ClipboardList, House, MessageCircle } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { PRESENTER } from '../shared/presenter.js';
import { useIdle } from '../shared/auth-ui.jsx';
import { languageInfo } from '../shared/languages.js';
import { ErrorNote, LoadingBlock, useAsync, useToast } from '../shared/ui.jsx';
import Onboarding from './Onboarding.jsx';
import { PlanScreen, TodayScreen, VisitsScreen } from './screens.jsx';
import ChatScreen from './Chat.jsx';
import VoiceSheet from './VoiceSheet.jsx';
import AccountScreen from './Account.jsx';
import { InviteScreen, PhoneSignIn, SetPinScreen, UnlockScreen, VerifyScreen, WelcomeScreen } from './Auth.jsx';
import { LogoMark, SafetyFooter } from './parts.jsx';
import { forgetDevice, rememberDevice, rememberedDevice } from './device.js';
import LegalScreen from './Legal.jsx';

const TABS = [
  { id: 'today', label: 'Today', icon: House },
  { id: 'chat', label: 'Chat', icon: MessageCircle },
  { id: 'plan', label: 'My plan', icon: ClipboardList },
  { id: 'visits', label: 'Visits', icon: CalendarDays }
];
const SIGNED_OUT_ROUTES = ['welcome', 'sign-in', 'verify', 'unlock', 'invite', 'forgot-pin'];
// Open to everyone, signed in or not.
const PUBLIC_ROUTES = ['privacy', 'terms'];

/* Hash routes: #/today, #/invite/CL-7K4Q. Kept tiny on purpose; the patient app has few screens. */
function useHashRoute() {
  const read = () => {
    const [name = '', ...params] = window.location.hash.replace(/^#\/?/, '').split('/');
    return { name, params: params.map(decodeURIComponent) };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onHash = () => setRoute(read());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  const go = useCallback((path, { replace = false } = {}) => {
    const hash = `#/${path}`;
    if (replace) { window.history.replaceState(null, '', hash); setRoute(read()); }
    else window.location.hash = hash;
  }, []);
  return [route, go];
}

export default function PatientApp() {
  const [route, go] = useHashRoute();
  const [session, setSession] = useState(undefined);
  const [challenge, setChallenge] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    CareLoopAPI.getPatientSession().then(({ session: current }) => setSession(current)).catch(() => setSession(null));
  }, []);

  const signedIn = useCallback((next, { forPinReset = false } = {}) => {
    rememberDevice(next);
    setSession(next);
    setChallenge(null);
    setNotice(null);
    go(forPinReset || !next.pin_set ? 'set-pin' : next.consent_needed ? 'start' : 'today', { replace: true });
  }, [go]);

  const signOut = useCallback(async ({ forget = false, reason = null } = {}) => {
    await CareLoopAPI.signOutPatient().catch(() => {});
    if (forget) forgetDevice();
    setSession(null);
    setNotice(reason);
    go(rememberedDevice() ? 'unlock' : 'welcome', { replace: true });
  }, [go]);

  // Family phones get passed around: after 10 quiet minutes, ask for the PIN again.
  const onIdle = useCallback(() => signOut({ reason: 'CareLoop locked itself because no one used it for a while. Enter your PIN to carry on.' }), [signOut]);
  useIdle(session?.idle_lock_minutes, onIdle, Boolean(session));

  // Route guard.
  useEffect(() => {
    if (session === undefined || PUBLIC_ROUTES.includes(route.name)) return;
    if (!session && !SIGNED_OUT_ROUTES.includes(route.name)) go(rememberedDevice() ? 'unlock' : 'welcome', { replace: true });
    if (!session && route.name === 'verify' && !challenge) go('sign-in', { replace: true });
    if (!session && route.name === 'unlock' && !rememberedDevice()) go('welcome', { replace: true });
    if (session && SIGNED_OUT_ROUTES.includes(route.name) && route.name !== 'invite') go(!session.pin_set ? 'set-pin' : session.consent_needed ? 'start' : 'today', { replace: true });
    if (session && !session.pin_set && route.name !== 'set-pin') go('set-pin', { replace: true });
  }, [session, route.name, go, challenge]);

  if (session === undefined) return <main className="auth-page"><LoadingBlock lines={3} /></main>;
  if (PUBLIC_ROUTES.includes(route.name)) return <LegalScreen doc={route.name} go={go} signedIn={Boolean(session)} />;

  if (!session) {
    const shared = { go, notice };
    if (route.name === 'sign-in' || route.name === 'forgot-pin') return <PhoneSignIn {...shared} purpose={route.name === 'forgot-pin' ? 'reset' : 'sign_in'} onChallenge={(next) => { setChallenge(next); go('verify'); }} />;
    if (route.name === 'verify' && challenge) return <VerifyScreen {...shared} challenge={challenge} onChallenge={setChallenge} onSignedIn={(next) => signedIn(next, { forPinReset: challenge.purpose === 'reset' })} />;
    if (route.name === 'unlock' && rememberedDevice()) return <UnlockScreen {...shared} device={rememberedDevice()} onSignedIn={signedIn} onForget={() => { forgetDevice(); go('welcome', { replace: true }); }} />;
    if (route.name === 'invite') return <InviteScreen {...shared} code={route.params[0]} onChallenge={(next) => { setChallenge(next); go('verify'); }} />;
    return <WelcomeScreen {...shared} />;
  }

  if (route.name === 'invite') return <InviteScreen go={go} signedInAs={session} onSignOut={() => signOut({ forget: true })} code={route.params[0]} />;
  if (!session.pin_set || route.name === 'set-pin') return <SetPinScreen session={session} onDone={(next) => { setSession(next); go(next.consent_needed ? 'start' : 'today', { replace: true }); }} />;

  return <SignedIn session={session} setSession={setSession} route={route} go={go} onSignOut={signOut} />;
}

function SignedIn({ session, setSession, route, go, onSignOut }) {
  const patientQuery = useAsync(() => CareLoopAPI.getPatient(session.patient_id), [session.patient_id]);
  const supportQuery = useAsync(() => CareLoopAPI.getSupportInfo(), []);
  const [patient, setPatient] = useState(null);
  useEffect(() => { if (patientQuery.data) setPatient(patientQuery.data.patient); }, [patientQuery.data]);

  const support = supportQuery.data;
  if (patientQuery.error) return <main className="auth-page"><ErrorNote error={patientQuery.error} onRetry={patientQuery.reload} /></main>;
  if (!patient || !support) return <main className="auth-page"><LoadingBlock lines={4} /></main>;

  const isCaregiver = session.kind === 'caregiver';
  if (!patient.consent_at && !isCaregiver) {
    return (
      <Onboarding
        patient={patient}
        support={support}
        onCancel={() => onSignOut()}
        onDone={async (updated) => {
          setPatient(updated);
          const { session: next } = await CareLoopAPI.refreshPatientSession();
          if (next) setSession(next);
          go('today', { replace: true });
        }}
      />
    );
  }
  if (route.name === 'preferences') {
    return <Onboarding patient={patient} support={support} editing onCancel={() => go('account')} onDone={(updated) => { setPatient(updated); go('account'); }} />;
  }
  return <Home session={session} patient={patient} onPatientChange={setPatient} support={support} route={route} go={go} onSignOut={onSignOut} />;
}

function Home({ session, patient, onPatientChange, support, route, go, onSignOut }) {
  const tab = route.name === 'account' ? 'account' : TABS.some((item) => item.id === route.name) ? route.name : 'today';
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const headingRef = useRef(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (!TABS.some((item) => item.id === route.name) && route.name !== 'account') go('today', { replace: true });
  }, [route.name, go]);

  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return; }
    headingRef.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [tab]);

  const refresh = () => setRefreshKey((value) => value + 1);
  const screenProps = { session, patient, onPatientChange, support, refreshKey, refresh, headingRef, onTalk: () => setVoiceOpen(true), goTo: (next) => go(next) };
  const language = languageInfo(patient.language);
  const userName = session.user_name;

  return (
    <div className={`patient-home tab-${tab}`}>
      <header className="patient-topbar">
        <a className="brand-link" href="#/today"><LogoMark /><span>CareLoop</span></a>
        <div className="topbar-actions">
          {PRESENTER && <PresenterMenu patient={patient} onChange={refresh} />}
          <a className="account-chip" href="#/account" aria-current={tab === 'account' ? 'page' : undefined}>
            <span className="account-initial" aria-hidden="true">{userName.charAt(0)}</span>
            <span className="sr-only">Your account, {userName}. Tomi speaks {language.native}{language.beta ? ' (beta)' : ''}.</span>
          </a>
        </div>
      </header>
      {session.kind === 'caregiver' && (
        <p className="helping-bar">You are helping <strong>{session.acting_for_name}</strong>. Anything you tell Tomi is marked as coming from you.</p>
      )}

      <nav className="tabbar" aria-label="Main">
        {TABS.map(({ id, label, icon: Icon }) => (
          <a key={id} href={`#/${id}`} className="tabbar-link" aria-current={tab === id ? 'page' : undefined}>
            <Icon aria-hidden="true" size={22} />
            <span>{label}</span>
          </a>
        ))}
      </nav>

      <main className="patient-main" id="main">
        {tab === 'today' && <TodayScreen {...screenProps} />}
        {tab === 'chat' && <ChatScreen {...screenProps} />}
        {tab === 'plan' && <PlanScreen {...screenProps} />}
        {tab === 'visits' && <VisitsScreen {...screenProps} />}
        {tab === 'account' && <AccountScreen {...screenProps} onSignOut={onSignOut} />}
        <SafetyFooter />
      </main>

      {voiceOpen && <VoiceSheet patient={patient} support={support} onClose={() => { setVoiceOpen(false); refresh(); }} />}
    </div>
  );
}

function PresenterMenu({ patient, onChange }) {
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') { setOpen(false); wrapRef.current?.querySelector('button')?.focus(); } };
    const onClick = (event) => { if (!wrapRef.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onClick); };
  }, [open]);

  const run = async (action) => {
    setOpen(false);
    try {
      if (action === 'reminder') {
        const response = await CareLoopAPI.sendNextReminder(patient.id);
        toast(response.message ? 'Tomi sent a reminder in chat.' : 'Nothing is due right now.');
        window.location.hash = '#/chat';
        onChange();
      } else {
        await CareLoopAPI.resetDemo();
        forgetDevice();
        window.location.hash = '#/welcome';
        window.location.reload();
      }
    } catch (error) { toast(error.message); }
  };

  return (
    <div className="demo-menu" ref={wrapRef}>
      <button type="button" className="demo-button" aria-expanded={open} aria-controls="presenter-panel" onClick={() => setOpen((value) => !value)}>Presenter</button>
      <div className="demo-panel" id="presenter-panel" hidden={!open}>
        <p className="hint">Only you can see these. Turn presenter mode off with ?presenter=0.</p>
        <button type="button" className="btn btn-secondary btn-block" onClick={() => run('reminder')}>Send a chat reminder now</button>
        <button type="button" className="btn btn-quiet btn-block" onClick={() => run('reset')}>Start the walkthrough again</button>
      </div>
    </div>
  );
}
