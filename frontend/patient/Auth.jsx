import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Mail, PhoneCall } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { CodeInput, IncomingMessage, PhoneField, PinPad, PresenterNote, clock, useCountdown } from '../shared/auth-ui.jsx';
import { LANGUAGES } from '../shared/languages.js';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
import { BetaChip, ErrorNote, LoadingBlock, useAsync } from '../shared/ui.jsx';
import { LogoMark, LoopArt, SafetyFooter } from './parts.jsx';
import { LegalLinks } from './Legal.jsx';

const LANG_KEY = 'careloop-language';
export const preferredLanguage = () => window.localStorage.getItem(LANG_KEY);

/* Shared frame: a purple hero with the loop drawing, and a paper sheet for the form. */
function AuthShell({ title, lede, back, children, tone = 'sheet', art = true }) {
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); }, [title]);
  return (
    <div className={`auth-page auth-${tone}`}>
      <header className="auth-hero">
        <div className="auth-bar">
          {back ? <a className="auth-back" href={back.href}><ArrowLeft aria-hidden="true" size={20} />{back.label}</a> : <span className="auth-brand"><LogoMark />CareLoop</span>}
        </div>
        {art && <LoopArt />}
        <h1 ref={headingRef} tabIndex={-1} className="auth-title">{title}</h1>
        {lede && <p className="auth-lede">{lede}</p>}
      </header>
      <main className="auth-sheet">
        {children}
        <SafetyFooter />
      </main>
    </div>
  );
}

function Notice({ text }) {
  return text ? <p className="auth-notice" role="status">{text}</p> : null;
}

/* ---------- Welcome ---------- */

export function WelcomeScreen({ go, notice }) {
  const [language, setLanguage] = useState(preferredLanguage() || '');
  const choose = (name) => { setLanguage(name); window.localStorage.setItem(LANG_KEY, name); };

  return (
    <AuthShell title="Your care, once you are home" lede="Tomi reminds you about your medicines and visits in your own language, and lets your care team know when something is wrong.">
      <Notice text={notice} />
      <fieldset className="lang-picker">
        <legend className="label">Which language should Tomi speak?</legend>
        <div className="lang-options">
          {LANGUAGES.map((option) => (
            <label key={option.name} className="lang-option">
              <input type="radio" name="welcome-language" value={option.name} checked={language === option.name} onChange={() => choose(option.name)} />
              <span className="lang-greeting" lang={option.name === 'English' ? 'en' : undefined}>{option.greeting}</span>
              <span className="lang-name">{option.native}{option.beta && <BetaChip />}</span>
            </label>
          ))}
        </div>
        <p className="hint">Menus are in English for now. Languages marked Beta are still being checked by native speakers.</p>
      </fieldset>
      <div className="auth-actions">
        <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => go('sign-in')}>Sign in with my phone number</button>
        <button type="button" className="btn btn-secondary btn-lg btn-block" onClick={() => go('invite')}>I have an invite code</button>
      </div>
      <p className="hint">Looking after a family member? Use the invite code you were sent.</p>
      <LegalLinks />
    </AuthShell>
  );
}

/* ---------- Phone number ---------- */

export function PhoneSignIn({ go, purpose, onChallenge }) {
  const [phone, setPhone] = useState('');
  const [via, setVia] = useState('email');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const reset = purpose === 'reset';

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await CareLoopAPI.startPhoneSignIn({ phone, via });
      onChallenge({ ...response, purpose: reset ? 'reset' : 'sign_in', phone });
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  return (
    <AuthShell
      title={reset ? 'Make a new PIN' : 'Sign in'}
      lede={reset ? 'First, we need to check it is you. Enter the phone number you gave your care team.' : 'Enter the phone number you gave your care team. We will send a 6-digit code to the email address on your account.'}
      back={{ href: reset ? '#/unlock' : '#/welcome', label: 'Back' }}
      art={false}
    >
      <form className="auth-form" onSubmit={submit} noValidate>
        <PhoneField id="phone" label="Your phone number" value={phone} onChange={setPhone} invalid={Boolean(error)} describedBy={error ? 'phone-error' : undefined} autoFocus />
        <fieldset className="via-picker">
          <legend className="label">How should we send the code?</legend>
          <label className="via-option">
            <input type="radio" name="via" checked={via === 'email'} onChange={() => setVia('email')} />
            <Mail aria-hidden="true" size={22} />
            <span><strong>Email</strong><small>To the email address on your account</small></span>
          </label>
          <label className="via-option">
            <input type="radio" name="via" checked={via === 'voice'} onChange={() => setVia('voice')} />
            <PhoneCall aria-hidden="true" size={22} />
            <span><strong>Phone call</strong><small>Tomi calls and reads the code out</small></span>
          </label>
        </fieldset>
        {error && <p id="phone-error" className="field-error" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || phone.replace(/\D/g, '').length < 10}>{busy ? 'Sending…' : 'Send my code'}</button>
      </form>
      <PresenterNote items={[['Zainab (patient)', '0800 000 0101'], ['Tola (patient)', '0800 000 0102'], ['Hadiza (helps Zainab)', '0800 000 0201'], ['The code', 'Arrives as an email at the top of the screen']]} />
    </AuthShell>
  );
}

/* ---------- Code ---------- */

export function VerifyScreen({ go, challenge, onChallenge, onSignedIn }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sentAt, setSentAt] = useState(Date.now());
  const expiresIn = useCountdown(challenge.expires_in, sentAt);
  const resendIn = useCountdown(challenge.resend_in, sentAt);

  const verify = async (value) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { session } = await CareLoopAPI.verifyCode({ challenge_id: challenge.challenge_id, code: value });
      onSignedIn(session);
    } catch (requestError) { setError(requestError.message); setCode(''); setBusy(false); }
  };

  const resend = async (via) => {
    setError(null);
    try {
      const next = await CareLoopAPI.resendCode(challenge.challenge_id, { via });
      onChallenge({ ...challenge, ...next });
      setSentAt(Date.now());
      setCode('');
    } catch (requestError) { setError(requestError.message); }
  };

  const byCall = challenge.via === 'voice';
  return (
    <AuthShell
      title="Enter your code"
      lede={byCall ? `Tomi is calling ${challenge.masked_phone} to read out a 6-digit code.` : challenge.masked_email ? `We sent a 6-digit code by email to ${challenge.masked_email}.` : `If ${challenge.masked_phone} has a CareLoop account with an email address, we sent a 6-digit code there.`}
      back={{ href: challenge.invite_code ? `#/invite/${challenge.invite_code}` : challenge.purpose === 'reset' ? '#/forgot-pin' : '#/sign-in', label: 'Change number' }}
      art={false}
    >
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); verify(code); }}>
        <CodeInput id="code" label="6-digit code" value={code} onChange={(value) => { setCode(value); if (value.length === 6) verify(value); }} invalid={Boolean(error)} describedBy="code-status" autoFocus />
        <p id="code-status" className={error ? 'field-error' : 'hint'} role={error ? 'alert' : undefined} aria-live="polite">
          {error || (expiresIn > 0 ? `The code works for ${clock(expiresIn)} more.` : 'This code has expired. Ask for a new one.')}
        </p>
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || code.length < 6}>{busy ? 'Checking…' : 'Continue'}</button>
      </form>
      <div className="resend">
        <p className="label">No code yet?</p>
        {resendIn > 0 ? <p className="hint">You can ask for another in {clock(resendIn)}.</p> : (
          <div className="resend-actions">
            <button type="button" className="btn btn-secondary" onClick={() => resend('email')}><Mail aria-hidden="true" size={18} />Email me again</button>
            <button type="button" className="btn btn-secondary" onClick={() => resend('voice')}><PhoneCall aria-hidden="true" size={18} />Call me instead</button>
          </div>
        )}
        {!byCall && !challenge.masked_email && <p className="hint">No email address on your account? Choose a phone call, or ask your care team to add one.</p>}
      </div>
      <IncomingMessage message={challenge.demo_message} />
    </AuthShell>
  );
}

/* ---------- PIN unlock on a remembered phone ---------- */

export function UnlockScreen({ go, device, notice, onSignedIn, onForget }) {
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (value) => {
    setBusy(true);
    setError(null);
    try {
      const { session } = await CareLoopAPI.signInWithPin({ phone_e164: device.phone_e164, pin: value });
      onSignedIn(session);
    } catch (requestError) {
      setPin('');
      setBusy(false);
      if (requestError.locked) { go('forgot-pin'); return; }
      setError(requestError.message);
    }
  };

  return (
    <AuthShell tone="dark" title={`Welcome back, ${device.first_name}`} lede={`Enter your 4-digit PIN for ${device.masked_phone}.`}>
      <Notice text={notice} />
      <PinPad label="Your PIN" value={pin} onChange={setPin} onComplete={submit} disabled={busy} describedBy="pin-error" />
      <p id="pin-error" className="field-error" role={error ? 'alert' : undefined}>{error}</p>
      <div className="unlock-links">
        <a className="link-button" href="#/forgot-pin">I forgot my PIN</a>
        <button type="button" className="link-button" onClick={onForget}>Not {device.first_name}? Use another number</button>
      </div>
      <PresenterNote items={[['PIN', '1234 (Zainab, Tola and Hadiza)']]} />
    </AuthShell>
  );
}

/* ---------- Invite links (patients and family helpers) ---------- */

export function InviteScreen({ go, code, onChallenge, signedInAs, onSignOut }) {
  if (!code) return <InviteCodeEntry go={go} />;
  return <InviteDetails go={go} code={code} onChallenge={onChallenge} signedInAs={signedInAs} onSignOut={onSignOut} />;
}

function InviteCodeEntry({ go }) {
  const [value, setValue] = useState('');
  return (
    <AuthShell title="Enter your invite code" lede="Your care team or a family member gave it to you, by email or in person. It looks like this: CL-7K4Q." back={{ href: '#/welcome', label: 'Back' }} art={false}>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); go(`invite/${value.trim().toUpperCase()}`); }}>
        <div className="field">
          <label htmlFor="invite-code">Invite code</label>
          <input id="invite-code" className="input input-lg invite-input" value={value} onChange={(event) => setValue(event.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 9))} autoComplete="off" autoCapitalize="characters" spellCheck={false} autoFocus />
        </div>
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={value.trim().length < 6}>Continue</button>
      </form>
      <PresenterNote items={[['New patient (Chidi)', 'CL-7K4Q'], ['Family helper for Tola', 'CG-3M9D']]} />
    </AuthShell>
  );
}

function InviteDetails({ go, code, onChallenge, signedInAs, onSignOut }) {
  const query = useAsync(() => CareLoopAPI.getInvite(code), [code]);
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const invite = query.data?.invite;

  const send = async (via) => {
    setBusy(true);
    setError(null);
    try {
      const response = await CareLoopAPI.startInviteSignIn(code, { via, phone, email: via === 'email' ? email.trim() : undefined });
      onChallenge({ ...response, purpose: 'invite', invite_code: code });
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  if (query.loading && !invite) return <AuthShell title="Checking your invite" art={false}><LoadingBlock /></AuthShell>;
  if (query.error) {
    return (
      <AuthShell title="This invite does not work" back={{ href: '#/invite', label: 'Try another code' }} art={false}>
        <ErrorNote error={query.error} />
        <button type="button" className="btn btn-secondary btn-lg btn-block" onClick={() => go('sign-in')}>Sign in with my phone number</button>
      </AuthShell>
    );
  }

  const forHelper = invite.kind === 'caregiver';
  const title = forHelper ? `Help ${invite.patient_first_name} with their care` : `Welcome, ${invite.patient_first_name}`;
  const lede = forHelper
    ? `${invite.invited_by} has asked you to help. You will see ${invite.patient_first_name}'s plan, medicines and visits, and you can tell Tomi how things are going. ${invite.patient_first_name} can remove you at any time.`
    : `${invite.facility} has set up CareLoop for you. Tomi will help you follow the plan your care team gave you.`;

  if (signedInAs) {
    return (
      <AuthShell title={title} lede={lede} art={false}>
        <p className="auth-notice">You are signed in as {signedInAs.user_name}. To use this invite, sign out first.</p>
        <button type="button" className="btn btn-primary btn-lg btn-block" onClick={onSignOut}>Sign out</button>
        <a className="btn btn-quiet btn-lg btn-block" href="#/today">Stay signed in</a>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={title} lede={lede} back={{ href: '#/welcome', label: 'Back' }}>
      <dl className="invite-facts">
        <div><dt>From</dt><dd>{invite.facility}</dd></div>
        <div><dt>Invite code</dt><dd>{invite.code}</dd></div>
      </dl>
      {forHelper ? (
        <PhoneField id="helper-phone" label="Your own phone number" value={phone} onChange={setPhone} invalid={Boolean(error)} describedBy={error ? 'invite-error' : undefined} />
      ) : (
        <p>To check it is you, we will email you a code, or Tomi can call the number your care team has for you: <strong>{invite.masked_phone}</strong>.</p>
      )}
      <div className="field">
        <label htmlFor="invite-email">Your email address</label>
        <input id="invite-email" className="input input-lg" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-describedby="invite-email-hint" />
        <p id="invite-email-hint" className="hint">We send your sign-in codes and reminders here. They never say what your medicine is for.</p>
      </div>
      {error && <p id="invite-error" className="field-error" role="alert">{error}</p>}
      <div className="auth-actions">
        <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy || !EMAIL_PATTERN.test(email.trim()) || (forHelper && phone.replace(/\D/g, '').length < 10)} onClick={() => send('email')}><Mail aria-hidden="true" size={20} />Email me a code</button>
        <button type="button" className="btn btn-secondary btn-lg btn-block" disabled={busy || (forHelper && phone.replace(/\D/g, '').length < 10)} onClick={() => send('voice')}><PhoneCall aria-hidden="true" size={20} />Call me with a code</button>
      </div>
      {!forHelper && <p className="hint">Not {invite.patient_first_name}? Please stop here and let your care team know.</p>}
      <PresenterNote items={[...(forHelper ? [['Any new number', '0800 000 0301']] : []), ['Email', 'Any address; the code appears at the top of the screen']]} />
    </AuthShell>
  );
}

/* ---------- Create PIN ---------- */

export function SetPinScreen({ session, onDone }) {
  const [first, setFirst] = useState('');
  const [second, setSecond] = useState('');
  const [stage, setStage] = useState('first');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const confirm = async (value) => {
    if (value !== first) {
      setError('The two PINs were different. Start again.');
      setFirst(''); setSecond(''); setStage('first');
      return;
    }
    setBusy(true);
    try {
      const { session: next } = await CareLoopAPI.setPin({ pin: value });
      onDone(next);
    } catch (requestError) {
      setError(requestError.message);
      setFirst(''); setSecond(''); setStage('first'); setBusy(false);
    }
  };

  return (
    <AuthShell
      tone="dark"
      title={stage === 'first' ? (session.pin_set ? 'Choose a new PIN' : 'Make a 4-digit PIN') : 'Enter the same PIN again'}
      lede={stage === 'first' ? 'You will use it to open CareLoop on this phone. Tomi also asks for it on phone calls, in case someone else picks up.' : 'Just to be sure you typed it the way you meant.'}
    >
      {stage === 'first'
        ? <PinPad key="first" label="New PIN" value={first} onChange={(value) => { setFirst(value); setError(null); }} onComplete={() => window.setTimeout(() => setStage('second'), 180)} describedBy="set-pin-error" />
        : <PinPad key="second" label="New PIN again" value={second} onChange={setSecond} onComplete={confirm} disabled={busy} describedBy="set-pin-error" />}
      <p id="set-pin-error" className="field-error" role={error ? 'alert' : undefined}>{error}</p>
      <p className="hint">Avoid easy PINs like 1111 or your birth year. Keep it to yourself; your care team will never ask for it.</p>
    </AuthShell>
  );
}
