import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Check, Lock, ShieldCheck } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { clock, CodeInput, IncomingMessage, PasswordField, PresenterNote, useCountdown } from '../shared/auth-ui.jsx';
import LoopArt from '../shared/LoopArt.jsx';
import { ErrorNote, LoadingBlock, useAsync, useDialogFocus } from '../shared/ui.jsx';

// What the care team does at each point of the loop. Describes the product, not anyone's care.
const FIRST_WEEK = [
  { day: 'Day 0', title: 'You approve the plan', text: 'Tomi drafts it from the discharge note. Nothing reaches the patient until you say yes.' },
  { day: 'Day 1', title: 'Tomi checks in', text: 'In Hausa, Yoruba, Igbo or English, by chat, phone call or text.', tomi: true },
  { day: 'Day 3', title: 'A problem comes back to you', text: 'Could not buy the medicine, or no way to get to clinic. It lands in your queue with what Tomi already tried.' },
  { day: 'Day 7', title: 'The visit happens', text: 'A text goes out the evening before. You see who confirmed and who needs a call.' }
];

/* Split frame: purple panel that says what this place is, paper panel with one task on it. */
function AuthFrame({ title, lede, children, back }) {
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); }, [title]);
  return (
    <div className="staff-auth">
      <aside className="staff-auth-side">
        <p className="staff-auth-brand"><span className="logo-mark" aria-hidden="true" />CareLoop <span>for care teams</span></p>
        <LoopArt />
        <section className="staff-week" aria-labelledby="staff-week-title">
          <h2 id="staff-week-title">A patient's first week home</h2>
          <ol>
            {FIRST_WEEK.map((item) => (
              <li key={item.day} className={item.tomi ? 'is-tomi' : ''}>
                <span className="staff-week-day">{item.day}</span>
                <strong>{item.title}</strong>
                <span>{item.text}</span>
              </li>
            ))}
          </ol>
        </section>
        <p className="staff-auth-foot">For doctors, nurses and pharmacists at hospitals that use CareLoop. Patients and families use the CareLoop app on their phones.</p>
      </aside>
      <main className="staff-auth-main">
        <div className="staff-auth-card">
          {back && <Link className="back-link" to={back.to}><ArrowLeft aria-hidden="true" size={18} />{back.label}</Link>}
          <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
          {lede && <p className="staff-auth-lede">{lede}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}

/* ---------- Sign in: password, then a code by email ---------- */

export function SignIn({ onSignedIn }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState(location.state?.email || '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const from = location.state?.from || '/';
  const notice = location.state?.notice;

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await CareLoopAPI.staffSignIn({ email, password });
      navigate('/sign-in/verify', { state: { ...response, email, from } });
    } catch (requestError) { setError(requestError.message); setPassword(''); setBusy(false); }
  };

  return (
    <AuthFrame title="Sign in" lede="Use the email address you signed up with.">
      {notice && <p className="staff-notice" role="status">{notice}</p>}
      <form className="staff-form" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input input-lg" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={Boolean(error) || undefined} aria-describedby={error ? 'signin-error' : undefined} autoFocus={!email} />
        </div>
        <PasswordField id="password" label="Password" value={password} onChange={setPassword} invalid={Boolean(error)} describedBy={error ? 'signin-error' : undefined} autoFocus={Boolean(email)} />
        {error && <p id="signin-error" className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !email || !password}>{busy ? 'Checking…' : 'Continue'}</button>
      </form>
      <p className="staff-links"><Link to="/forgot-password" state={{ email }}>Forgot your password?</Link></p>
      <p className="staff-switch">New to CareLoop? <Link to="/sign-up">Create an account</Link></p>
      <PresenterNote items={[['Email', 'ada.okafor@kestrelgeneral.ng'], ['Password', 'Blue-ward-morning-24'], ['New staff invite', <Link key="j" to="/join/join-7f3k">Open Bisi Ola's invite</Link>]]} />
    </AuthFrame>
  );
}

export function VerifyMfa({ onSignedIn }) {
  const navigate = useNavigate();
  const { state } = useLocation();
  const [code, setCode] = useState('');
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [email, setEmail] = useState({ message: state?.demo_message, resendIn: state?.resend_in || 0, sent: 0 });
  const resendLeft = useCountdown(email.resendIn, email.sent);

  useEffect(() => { if (!state?.mfa_token) navigate('/sign-in', { replace: true }); }, [state, navigate]);
  if (!state?.mfa_token) return null;

  const verify = async (value) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { session } = await CareLoopAPI.verifyStaffMfa({ mfa_token: state.mfa_token, code: value, remember_device: remember });
      onSignedIn(session, state.from);
    } catch (requestError) {
      if (requestError.status === 410 || requestError.status === 429) { navigate('/sign-in', { replace: true, state: { email: state.email, notice: requestError.message } }); return; }
      setError(requestError.message);
      setCode('');
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      const response = await CareLoopAPI.resendStaffMfaEmail({ mfa_token: state.mfa_token });
      setEmail((current) => ({ message: response.demo_message, resendIn: response.resend_in, sent: current.sent + 1 }));
      setCode('');
    } catch (requestError) { setError(requestError.message); }
  };

  return (
    <AuthFrame title="Check your email" lede={`We sent a 6-digit code to ${state.masked_email}. It works for 15 minutes.`} back={{ to: '/sign-in', label: 'Use a different account' }}>
      <form className="staff-form" onSubmit={(event) => { event.preventDefault(); verify(code); }}>
        <CodeInput id="mfa-code" label="Code from the email" value={code} onChange={(value) => { setCode(value); if (value.length === 6) verify(value); }} invalid={Boolean(error)} describedBy={error ? 'mfa-error' : undefined} autoFocus />
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          <span>Do not ask for a code on this computer for 30 days. Only tick this on a computer that is yours alone.</span>
        </label>
        {error && <p id="mfa-error" className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || code.length < 6}>{busy ? 'Checking…' : 'Sign in'}</button>
      </form>
      <p className="staff-links">
        <button type="button" className="link-button" onClick={resend} disabled={resendLeft > 0}>{resendLeft > 0 ? `Send a new code in ${clock(resendLeft)}` : 'Send a new code'}</button>
      </p>
      <p className="hint">Nothing arrived? Check your spam folder. If you can no longer use this email address, ask your hospital's CareLoop admin to change it.</p>
      <IncomingMessage message={email.message} />
    </AuthFrame>
  );
}

/* ---------- Forgot and reset password ---------- */

export function ForgotPassword() {
  const { state } = useLocation();
  const [email, setEmail] = useState(state?.email || '');
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try { setSent(await CareLoopAPI.requestPasswordReset({ email })); } catch (requestError) { setError(requestError.message); }
    setBusy(false);
  };

  if (sent) {
    return (
      <AuthFrame title="Check your email" lede={`If ${email} has a CareLoop account, we have sent it a link to choose a new password. The link works for 30 minutes.`} back={{ to: '/sign-in', label: 'Back to sign in' }}>
        <p className="hint">Nothing arrived after a few minutes? Check spam, or ask your hospital's CareLoop admin to confirm the address on your account.</p>
        <button type="button" className="btn btn-secondary btn-lg" onClick={() => setSent(null)}>Send it again</button>
        <IncomingMessage message={sent.demo_message} />
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="Reset your password" lede="Enter the email address you signed up with. We will send you a link to choose a new password." back={{ to: '/sign-in', label: 'Back to sign in' }}>
      <form className="staff-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="reset-email">Email</label>
          <input id="reset-email" className="input input-lg" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} autoFocus />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !email.includes('@')}>{busy ? 'Sending…' : 'Send reset link'}</button>
      </form>
    </AuthFrame>
  );
}

function PasswordRules({ password, email }) {
  const local = (email || '').split('@')[0].toLowerCase();
  const rules = [
    ['At least 12 characters', password.length >= 12],
    ['Not your email address', !password || !local || local.length < 4 || !password.toLowerCase().includes(local)]
  ];
  return (
    <ul className="pw-rules" aria-label="Password rules">
      {rules.map(([label, met]) => <li key={label} className={met ? 'is-met' : ''}><Check aria-hidden="true" size={16} />{label}<span className="sr-only">{met ? ', done' : ', not yet'}</span></li>)}
      <li className="pw-tip">A short phrase is easier to remember than random symbols, for example four unrelated words.</li>
    </ul>
  );
}

export function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const check = useAsync(() => CareLoopAPI.checkResetToken(token), [token]);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    if (password !== confirm) { setError('The two passwords are different.'); return; }
    setBusy(true);
    setError(null);
    try {
      await CareLoopAPI.resetPassword(token, { password });
      navigate('/sign-in', { replace: true, state: { notice: 'Password changed. You have been signed out everywhere, so sign in again.' } });
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  if (check.loading && !check.data) return <AuthFrame title="Checking your link"><LoadingBlock /></AuthFrame>;
  if (check.error) {
    return (
      <AuthFrame title="This link does not work" back={{ to: '/sign-in', label: 'Back to sign in' }}>
        <ErrorNote error={check.error} />
        <Link className="btn btn-primary btn-lg" to="/forgot-password">Send a new link</Link>
      </AuthFrame>
    );
  }
  return (
    <AuthFrame title="Choose a new password" lede={`For ${check.data.email_masked}. You will be signed out on every other computer.`}>
      <form className="staff-form" onSubmit={submit}>
        <PasswordField id="new-password" label="New password" value={password} onChange={setPassword} autoComplete="new-password" describedBy="pw-rules" autoFocus />
        <div id="pw-rules"><PasswordRules password={password} email="" /></div>
        <PasswordField id="confirm-password" label="Type it again" value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={Boolean(confirm) && confirm !== password} />
        {error && <p className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || password.length < 12 || !confirm}>{busy ? 'Saving…' : 'Save new password'}</button>
      </form>
    </AuthFrame>
  );
}

/* ---------- Create an account: details with the hospital code, then confirm email ---------- */

const SIGN_UP_STEPS = [['details', 'Your details'], ['email', 'Confirm email']];

function SetupSteps({ steps, current }) {
  const index = steps.findIndex(([id]) => id === current);
  return (
    <ol className="join-steps" aria-label="Sign-up steps" style={{ '--steps': steps.length }}>
      {steps.map(([id, label], position) => <li key={id} aria-current={current === id ? 'step' : undefined} className={index > position ? 'is-done' : ''}>{label}</li>)}
    </ol>
  );
}

export function SignUp({ onSignedIn }) {
  const options = useAsync(() => CareLoopAPI.listFacilities(), []);
  const [stage, setStage] = useState('details');
  const [form, setForm] = useState({ name: '', email: '', facility_id: '', join_code: '', role: '', password: '', confirmed: false });
  const [signup, setSignup] = useState(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const resendLeft = useCountdown(signup?.resend_in || 0, signup?.sent);
  const set = (field) => (value) => setForm((current) => ({ ...current, [field]: value }));
  const progress = <SetupSteps steps={SIGN_UP_STEPS} current={stage} />;

  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await CareLoopAPI.staffSignUp(form);
      setSignup({ ...response, sent: 0 });
      setStage('email');
    } catch (requestError) {
      setError({ message: requestError.message, field: requestError.field });
      if (requestError.field === 'join_code') document.getElementById('signup-join-code')?.focus();
    }
    setBusy(false);
  };

  const verify = async (value) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { session } = await CareLoopAPI.verifySignUpEmail({ signup_token: signup.signup_token, code: value });
      onSignedIn(session, '/');
    } catch (requestError) {
      if (requestError.status === 410) { setStage('details'); setSignup(null); }
      setError({ message: requestError.message });
      setCode('');
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      const response = await CareLoopAPI.resendSignUpCode({ signup_token: signup.signup_token });
      setSignup((current) => ({ ...current, ...response, sent: current.sent + 1 }));
      setCode('');
    } catch (requestError) { setError({ message: requestError.message }); }
  };

  if (stage === 'email') {
    return (
      <AuthFrame title="Confirm your email" lede={`We sent a 6-digit code to ${signup.masked_email}. It works for 15 minutes.`}>
        {progress}
        <form className="staff-form" onSubmit={(event) => { event.preventDefault(); verify(code); }}>
          <CodeInput id="signup-code" label="Code from the email" value={code} onChange={(value) => { setCode(value); if (value.length === 6) verify(value); }} invalid={Boolean(error)} describedBy={error ? 'signup-code-error' : undefined} autoFocus />
          {error && <p id="signup-code-error" className="field-error" role="alert">{error.message}</p>}
          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || code.length < 6}>{busy ? 'Checking…' : 'Confirm and open CareLoop'}</button>
        </form>
        <p className="staff-links">
          <button type="button" className="link-button" onClick={resend} disabled={resendLeft > 0}>{resendLeft > 0 ? `Send a new code in ${clock(resendLeft)}` : 'Send a new code'}</button>
          <button type="button" className="link-button" onClick={() => { setStage('details'); setCode(''); setError(null); }}>Change email address</button>
        </p>
        <p className="hint">Nothing arrived? Check your spam folder.</p>
        <IncomingMessage message={signup.demo_message} />
      </AuthFrame>
    );
  }

  const facilities = options.data?.facilities || [];
  const roles = options.data?.roles || [];
  const chosen = facilities.find((item) => item.id === form.facility_id);
  const codeError = error?.field === 'join_code';
  const ready = form.name.trim() && form.email.includes('@') && form.facility_id && form.join_code.trim().length >= 4 && form.role && form.password.length >= 12 && form.confirmed;

  return (
    <AuthFrame title="Create your account" lede="You need your hospital's code to sign up. Your hospital's CareLoop admin gives it to staff.">
      {progress}
      <form className="staff-form" onSubmit={create} noValidate>
        <div className="field">
          <label htmlFor="signup-name">Full name</label>
          <input id="signup-name" className="input input-lg" autoComplete="name" value={form.name} onChange={(event) => set('name')(event.target.value)} aria-describedby="signup-name-hint" autoFocus />
          <p id="signup-name-hint" className="hint">As patients and colleagues know you, such as Dr. Amina Bello.</p>
        </div>
        <div className="field">
          <label htmlFor="signup-email">Email</label>
          <input id="signup-email" className="input input-lg" type="email" autoComplete="email" value={form.email} onChange={(event) => set('email')(event.target.value)} aria-describedby="signup-email-hint" />
          <p id="signup-email-hint" className="hint">Any address you check often. Your sign-in codes go here.</p>
        </div>
        <div className="field">
          <label htmlFor="signup-facility">Hospital</label>
          <select id="signup-facility" className="select input-lg" value={form.facility_id} onChange={(event) => set('facility_id')(event.target.value)} disabled={!facilities.length}>
            <option value="" disabled>{options.loading ? 'Loading hospitals…' : 'Choose your hospital'}</option>
            {facilities.map((item) => <option key={item.id} value={item.id}>{item.name}, {item.city}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="signup-join-code">Hospital code</label>
          <input id="signup-join-code" className="input input-lg mono-ish" value={form.join_code} onChange={(event) => set('join_code')(event.target.value.toUpperCase().slice(0, 12))} autoComplete="off" spellCheck={false} placeholder="ABC-1234" aria-invalid={codeError || undefined} aria-describedby={codeError ? 'signup-join-code-error' : 'signup-join-code-hint'} />
          {codeError
            ? <p id="signup-join-code-error" className="field-error" role="alert">{error.message}</p>
            : <p id="signup-join-code-hint" className="hint">Only staff with this code can join {chosen ? chosen.name : 'your hospital'}.</p>}
        </div>
        <div className="field">
          <label htmlFor="signup-role">Your role</label>
          <select id="signup-role" className="select input-lg" value={form.role} onChange={(event) => set('role')(event.target.value)} disabled={!roles.length}>
            <option value="" disabled>Choose your role</option>
            {roles.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
        </div>
        <PasswordField id="signup-password" label="Choose a password" value={form.password} onChange={set('password')} autoComplete="new-password" describedBy="signup-rules" />
        <div id="signup-rules"><PasswordRules password={form.password} email={form.email} /></div>
        <label className="check check-top">
          <input type="checkbox" checked={form.confirmed} onChange={(event) => set('confirmed')(event.target.checked)} />
          <span>I work at {chosen ? chosen.name : 'this hospital'} and will only open the records of patients in my care.</span>
        </label>
        <ErrorNote error={options.error} onRetry={options.reload} />
        {error && !codeError && <p className="field-error" role="alert">{error.message}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !ready}>{busy ? 'Creating account…' : 'Create account'}</button>
      </form>
      <p className="staff-switch">Already have an account? <Link to="/sign-in">Sign in</Link></p>
      <PresenterNote items={[['Kestrel General', 'KGH-4821'], ['Egret Teaching', 'ETH-3067'], ['Hornbill Specialist', 'HSH-5914'], ['Weaverbird Medical Centre', 'WMC-2738'], ['Heron Bay General', 'HBG-6409']]} />
    </AuthFrame>
  );
}

/* ---------- Join from a staff invite: choose a password and go in ---------- */

export function JoinInvite({ onSignedIn }) {
  const { token } = useParams();
  const query = useAsync(() => CareLoopAPI.getStaffInvite(token), [token]);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const invite = query.data?.invite;

  const savePassword = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { session } = await CareLoopAPI.acceptStaffInvite(token, { password });
      onSignedIn(session, '/');
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  if (query.loading && !invite) return <AuthFrame title="Opening your invite"><LoadingBlock /></AuthFrame>;
  if (query.error) {
    return (
      <AuthFrame title="This invite does not work" back={{ to: '/sign-in', label: 'Go to sign in' }}>
        <ErrorNote error={query.error} />
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title={`Welcome, ${invite.name.split(' ')[0]}`} lede={`${invite.invited_by} invited you to join ${invite.facility} as ${invite.role.toLowerCase()}. Choose a password to finish. Each time you sign in, we will also email you a code.`}>
      <form className="staff-form" onSubmit={savePassword}>
        <div className="field">
          <label htmlFor="join-email">Email</label>
          <input id="join-email" className="input input-lg" value={invite.email} readOnly autoComplete="username" />
        </div>
        <PasswordField id="join-password" label="Choose a password" value={password} onChange={setPassword} autoComplete="new-password" describedBy="join-rules" autoFocus />
        <div id="join-rules"><PasswordRules password={password} email={invite.email} /></div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || password.length < 12}>{busy ? 'Saving…' : 'Open CareLoop'}</button>
      </form>
    </AuthFrame>
  );
}

/* ---------- Idle lock: keeps the page, hides it, asks for the password ---------- */

export function LockScreen({ user, onUnlock, onSignOut }) {
  const ref = useRef(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useDialogFocus(ref, () => {}, '#unlock-password');

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try { await CareLoopAPI.unlockStaffSession({ password }); onUnlock(); } catch (requestError) { setError(requestError.message); setPassword(''); setBusy(false); }
  };

  return createPortal(
    <div className="lock-screen">
      <section ref={ref} className="lock-card" role="dialog" aria-modal="true" aria-labelledby="lock-title" aria-describedby="lock-copy">
        <span className="lock-icon" aria-hidden="true"><Lock size={26} /></span>
        <h2 id="lock-title">Screen locked</h2>
        <p id="lock-copy">Patient details are hidden because this computer was left alone for {user.idle_minutes} minutes, or someone locked it. Enter your password to pick up where you left off.</p>
        <p className="lock-user"><span className="dash-avatar" aria-hidden="true">{user.initials}</span><span><strong>{user.name}</strong><span>{user.email}</span></span></p>
        <form className="staff-form" onSubmit={submit}>
          <PasswordField id="unlock-password" label="Password" value={password} onChange={setPassword} invalid={Boolean(error)} describedBy={error ? 'unlock-error' : undefined} />
          {error && <p id="unlock-error" className="field-error" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || !password}>{busy ? 'Checking…' : 'Unlock'}</button>
        </form>
        <button type="button" className="link-button" onClick={onSignOut}>Not {user.name}? Sign out</button>
      </section>
    </div>,
    document.body
  );
}

export function MfaBadge() {
  return <span className="badge badge-green"><ShieldCheck aria-hidden="true" />Code by email at each sign-in</span>;
}
