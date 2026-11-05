import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Building2, CalendarDays, Gauge, Lock, LogOut, MessageSquareText, Mic, PhoneCall, Settings, Siren, Users } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { PRESENTER } from '../shared/presenter.js';
import { useIdle } from '../shared/auth-ui.jsx';
import { LoadingBlock, useInterval, useToast } from '../shared/ui.jsx';
import Overview from './pages/Overview.jsx';
import Patients from './pages/Patients.jsx';
import PatientProfile from './pages/PatientProfile.jsx';
import PlanReview from './pages/PlanReview.jsx';
import Appointments from './pages/Appointments.jsx';
import Escalations from './pages/Escalations.jsx';
import Calls from './pages/Calls.jsx';
import Account from './pages/Account.jsx';
import Reminders from './pages/Reminders.jsx';
import Admin from './pages/Admin.jsx';
import { ForgotPassword, JoinInvite, LockScreen, ResetPassword, SignIn, SignUp, VerifyMfa } from './Auth.jsx';
import { DashboardContext } from './shell.jsx';
import { AssistantPanel } from './Assistant.jsx';

function useCounts(enabled) {
  const [counts, setCounts] = useState({});
  const refreshCounts = useCallback(async () => {
    try {
      const [escalations, patients, requests, failed] = await Promise.all([
        CareLoopAPI.listEscalations({ status: 'open' }),
        CareLoopAPI.listPatients(),
        CareLoopAPI.listRescheduleRequests({ status: 'pending' }),
        CareLoopAPI.listNotifications({ status: 'problem' })
      ]);
      setCounts({
        unacknowledged: escalations.escalations.filter((item) => item.status !== 'acknowledged' && item.status !== 'acted_on').length,
        openEscalations: escalations.escalations.length,
        planReviews: patients.patients.filter((patient) => patient.plan_status === 'needs_review').length,
        reschedules: requests.requests.length,
        failedMessages: failed.notifications.filter((item) => !item.retried).length
      });
    } catch { /* Pages show request errors in context. */ }
  }, []);
  useEffect(() => { if (enabled) refreshCounts(); }, [enabled, refreshCounts]);
  useInterval(refreshCounts, 15000, enabled);
  return { counts, refreshCounts };
}

export default function ClinicianApp() {
  const [session, setSession] = useState(undefined);
  const navigate = useNavigate();

  useEffect(() => {
    CareLoopAPI.getStaffSession().then(({ session: current }) => setSession(current)).catch(() => setSession(null));
  }, []);

  const signedIn = useCallback((next, to = '/') => { setSession(next); navigate(to, { replace: true }); }, [navigate]);
  const signOut = useCallback(async ({ everywhere = false, notice } = {}) => {
    await CareLoopAPI.staffSignOut({ everywhere }).catch(() => {});
    setSession(null);
    navigate('/sign-in', { replace: true, state: { notice: notice || 'You are signed out.' } });
  }, [navigate]);

  if (session === undefined) return <main className="staff-loading"><LoadingBlock lines={3} /></main>;

  return (
    <Routes>
      <Route path="/sign-in" element={session ? <Navigate to="/" replace /> : <SignIn />} />
      <Route path="/sign-in/verify" element={session ? <Navigate to="/" replace /> : <VerifyMfa onSignedIn={signedIn} />} />
      <Route path="/sign-up" element={<SignUp onSignedIn={signedIn} />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:token" element={<ResetPassword />} />
      <Route path="/join/:token" element={<JoinInvite onSignedIn={signedIn} />} />
      <Route path="*" element={session ? <Dashboard session={session} onSignOut={signOut} /> : <RedirectToSignIn />} />
    </Routes>
  );
}

function RedirectToSignIn() {
  const location = useLocation();
  return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />;
}

function Dashboard({ session, onSignOut }) {
  const { counts, refreshCounts } = useCounts(true);
  const location = useLocation();
  const mainRef = useRef(null);
  const firstRoute = useRef(true);
  const [locked, setLocked] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const dataChanged = useCallback(() => setDataVersion((value) => value + 1), []);
  const launcherRef = useRef(null);
  const routePatientId = location.pathname.match(/^\/patients\/([^/]+)/)?.[1] || '';
  const user = session.user;
  const closeAssistant = useCallback(() => {
    setAssistantOpen(false);
    window.setTimeout(() => launcherRef.current?.focus(), 0);
  }, []);

  // Ward computers are shared: lock after a quiet spell, keep the page underneath.
  const lock = useCallback(() => setLocked(true), []);
  useIdle(session.idle_lock_minutes, lock, !locked);

  useEffect(() => {
    if (firstRoute.current) { firstRoute.current = false; return; }
    window.scrollTo(0, 0);
    // Move focus to the new page heading once it has rendered.
    const timer = window.setTimeout(() => mainRef.current?.querySelector('h1')?.focus({ preventScroll: true }), 60);
    return () => window.clearTimeout(timer);
  }, [location.pathname]);

  return (
    <DashboardContext.Provider value={{ counts, refreshCounts, user, signOut: onSignOut, dataVersion, dataChanged, openAssistant: () => setAssistantOpen(true) }}>
      <div className={`dash${locked ? ' is-locked' : ''}${assistantOpen ? ' has-assistant' : ''}`} aria-hidden={locked || undefined}>
        <aside className="dash-side">
          <a className="dash-brand" href="#/"><span className="logo-mark" aria-hidden="true" />CareLoop</a>
          <nav className="dash-nav" aria-label="Main">
            <NavLink to="/" end><Gauge aria-hidden="true" />Overview</NavLink>
            <NavLink to="/patients"><Users aria-hidden="true" />Patients{counts.planReviews > 0 && <span className="nav-count tone-amber" aria-label={`${counts.planReviews} plans to review`}>{counts.planReviews}</span>}</NavLink>
            <NavLink to="/appointments"><CalendarDays aria-hidden="true" />Appointments{counts.reschedules > 0 && <span className="nav-count tone-amber" aria-label={`${counts.reschedules} reschedule requests`}>{counts.reschedules}</span>}</NavLink>
            <NavLink to="/escalations"><Siren aria-hidden="true" />Escalations{counts.unacknowledged > 0 && <span className="nav-count tone-red" aria-label={`${counts.unacknowledged} not acknowledged`}>{counts.unacknowledged}</span>}</NavLink>
            <NavLink to="/calls"><PhoneCall aria-hidden="true" />Calls</NavLink>
            <NavLink to="/reminders"><MessageSquareText aria-hidden="true" />Reminders{counts.failedMessages > 0 && <span className="nav-count tone-amber" aria-label={`${counts.failedMessages} not delivered`}>{counts.failedMessages}</span>}</NavLink>
            {user.is_admin && <NavLink to="/admin"><Building2 aria-hidden="true" />Facility admin</NavLink>}
          </nav>
          <div className="dash-foot">
            <NavLink to="/account" className="dash-user">
              <span className="dash-avatar" aria-hidden="true">{user.initials}</span>
              <span className="dash-user-text"><strong>{user.name}</strong><span>{user.role}</span></span>
              <Settings aria-hidden="true" size={18} className="dash-user-icon" />
              <span className="sr-only">, account and security</span>
            </NavLink>
            <div className="dash-session">
              <button type="button" className="dash-signout" onClick={lock}><Lock aria-hidden="true" size={18} />Lock</button>
              <button type="button" className="dash-signout" onClick={() => onSignOut()}><LogOut aria-hidden="true" size={18} />Sign out</button>
            </div>
            {PRESENTER && <PresenterControls />}
          </div>
        </aside>
        <main className="dash-main" ref={mainRef}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/:patientId" element={<PatientProfile />} />
            <Route path="/patients/:patientId/review" element={<PlanReview />} />
            <Route path="/appointments" element={<Appointments />} />
            <Route path="/escalations" element={<Escalations />} />
            <Route path="/calls" element={<Calls />} />
            <Route path="/reminders" element={<Reminders />} />
            <Route path="/account" element={<Account />} />
            <Route path="/admin" element={user.is_admin ? <Admin /> : <Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        {assistantOpen
          ? <AssistantPanel onClose={closeAssistant} routePatientId={routePatientId} />
          : <button ref={launcherRef} type="button" className="assistant-launcher" onClick={() => setAssistantOpen(true)}><Mic aria-hidden="true" size={20} />Ask Tomi</button>}
      </div>
      {locked && <LockScreen user={{ ...user, idle_minutes: session.idle_lock_minutes }} onUnlock={() => setLocked(false)} onSignOut={() => { setLocked(false); onSignOut(); }} />}
    </DashboardContext.Provider>
  );
}

// Presenter mode only (?presenter=1): put every patient back to the start of the walkthrough.
function PresenterControls() {
  const toast = useToast();
  return (
    <div className="dash-demo-group" role="group" aria-label="Presenter tools">
      <button type="button" className="btn dash-demo" onClick={async () => {
        try { await CareLoopAPI.resetDemo(); window.location.hash = '#/'; window.location.reload(); } catch (error) { toast(error.message); }
      }}>Presenter: start the walkthrough again</button>
    </div>
  );
}
