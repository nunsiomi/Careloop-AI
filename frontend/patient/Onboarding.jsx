import { useEffect, useRef, useState } from 'react';
import { CareLoopAPI } from '../shared/api.js';
import { CHANNELS, CONTACT_WINDOWS, LANGUAGES, READING_LEVELS } from '../shared/languages.js';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
import { BetaChip } from '../shared/ui.jsx';
import { LogoMark, SafetyFooter } from './parts.jsx';
import { preferredLanguage } from './Auth.jsx';

const STEPS = ['welcome', 'language', 'reading', 'contact', 'consent'];
const EDIT_STEPS = ['language', 'reading'];

export default function Onboarding({ patient, editing, onDone, onCancel }) {
  const steps = editing ? EDIT_STEPS : STEPS;
  const [index, setIndex] = useState(0);
  const [language, setLanguage] = useState((!editing && preferredLanguage()) || patient.language || null);
  const [reading, setReading] = useState(READING_LEVELS.some((level) => level.id === patient.literacy_level) ? patient.literacy_level : null);
  const [channels, setChannels] = useState(patient.channels?.length ? patient.channels : ['web']);
  const [contactWindow, setContactWindow] = useState(patient.contact_window || CONTACT_WINDOWS[0].id);
  const [pin, setPin] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [email, setEmail] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const headingRef = useRef(null);
  const step = steps[index];

  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); }, [index, declined]);

  const needsPin = channels.includes('voice') && !patient.pin_set;
  const pinValid = !needsPin || (/^\d{4}$/.test(pin) && pin === pinConfirm);
  const needsEmail = channels.includes('email') && !patient.email;
  const emailValid = !needsEmail || EMAIL_PATTERN.test(email.trim());
  const canContinue = {
    welcome: true,
    language: Boolean(language),
    reading: Boolean(reading),
    contact: channels.length > 0 && pinValid && emailValid,
    consent: agreed
  }[step];

  const back = () => {
    setError(null);
    if (index === 0) onCancel();
    else setIndex(index - 1);
  };

  const next = async () => {
    setError(null);
    if (index < steps.length - 1) { setIndex(index + 1); return; }
    setBusy(true);
    try {
      let response = await CareLoopAPI.updateProfile(patient.id, { language, literacy_level: reading, caregiver_mode: reading === 'caregiver' });
      if (!editing) {
        response = await CareLoopAPI.recordConsent(patient.id, { channels, scope: 'patient_follow_up', version: 'v1', contact_window: contactWindow, pin: needsPin ? pin : undefined, email: needsEmail ? email.trim() : undefined });
      }
      onDone(response.patient);
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    }
  };

  if (declined) {
    return (
      <main className="patient-page onboarding">
        <section className="onboard-card">
          <h1 ref={headingRef} tabIndex={-1} className="onboard-title">That is okay</h1>
          <p className="onboard-lede">We will not contact you. If you change your mind, sign in again or ask your care team to help.</p>
          <div className="onboard-actions">
            <button type="button" className="btn btn-quiet btn-lg" onClick={() => setDeclined(false)}>Go back</button>
            <button type="button" className="btn btn-secondary btn-lg" onClick={onCancel}>Sign out</button>
          </div>
        </section>
        <SafetyFooter />
      </main>
    );
  }

  const toggleChannel = (id) => setChannels((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  const isLast = index === steps.length - 1;

  return (
    <main className="patient-page onboarding">
      <div className="onboard-brand"><LogoMark /><span>CareLoop</span></div>
      <section className="onboard-card" aria-labelledby="onboard-title">
        {steps.length > 2 && (
          <div className="stepper">
            <p className="hint">Step {index + 1} of {steps.length}</p>
            <ol className="stepper-track" aria-hidden="true">
              {steps.map((name, position) => <li key={name} className={position <= index ? 'is-done' : ''} />)}
            </ol>
          </div>
        )}

        {step === 'welcome' && (
          <>
            <div className="welcome-orb" aria-hidden="true"><span /></div>
            <h1 id="onboard-title" ref={headingRef} tabIndex={-1} className="onboard-title">Hello, I am Tomi</h1>
            <p className="onboard-lede">I am here to help you follow the plan your care team gave you.</p>
            <ul className="promise-list">
              <li>I am an AI assistant, not a doctor or a nurse.</li>
              <li>I only repeat what your care team wrote down. I never give new medical advice.</li>
              <li>If something sounds urgent, I tell a real person on your care team straight away.</li>
              <li>You can talk to me here, type to me, or call me. I can also call you and send you short email reminders.</li>
            </ul>
          </>
        )}

        {step === 'language' && (
          <fieldset className="choice-group">
            <legend><h1 id="onboard-title" ref={headingRef} tabIndex={-1} className="onboard-title">Which language should Tomi use?</h1></legend>
            <p className="onboard-lede">You can change this any time.</p>
            <div className="choice-grid">
              {LANGUAGES.map((option) => (
                <label key={option.name} className="choice-card">
                  <input type="radio" name="language" value={option.name} checked={language === option.name} onChange={() => setLanguage(option.name)} />
                  <span className="choice-greeting" lang={option.name === 'English' ? 'en' : undefined}>{option.greeting}</span>
                  <span className="choice-title">{option.native}</span>
                  {option.beta && <BetaChip />}
                </label>
              ))}
            </div>
            <p className="hint">Languages marked Beta are still being checked by native speakers. Numbers and doses are always shown in English too.</p>
          </fieldset>
        )}

        {step === 'reading' && (
          <fieldset className="choice-group">
            <legend><h1 id="onboard-title" ref={headingRef} tabIndex={-1} className="onboard-title">How should Tomi write to you?</h1></legend>
            <p className="onboard-lede">This changes how much Tomi says, never what your plan says.</p>
            <div className="choice-list">
              {READING_LEVELS.map((option) => (
                <label key={option.id} className="choice-card choice-row">
                  <input type="radio" name="reading" value={option.id} checked={reading === option.id} onChange={() => setReading(option.id)} />
                  <span className="choice-title">{option.title}</span>
                  <span className="choice-detail">{option.detail}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        {step === 'contact' && (
          <>
            <h1 id="onboard-title" ref={headingRef} tabIndex={-1} className="onboard-title">How can Tomi reach you?</h1>
            <p className="onboard-lede">Tick each one you are happy with. You can turn any of them off later in your account.</p>
            <fieldset className="choice-group">
              <legend className="label">Ways to reach you</legend>
              <div className="choice-list">
                {CHANNELS.map((option) => {
                  const off = option.available === false && !channels.includes(option.id);
                  return (
                    <label key={option.id} className={`choice-card choice-row choice-check${off ? ' is-disabled' : ''}`}>
                      <input type="checkbox" checked={channels.includes(option.id)} disabled={off} onChange={() => toggleChannel(option.id)} />
                      <span className="choice-title">{option.title}</span>
                      <span className="choice-detail">{off ? option.unavailable : option.detail}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            {(channels.includes('voice') || channels.includes('sms')) && (
              <fieldset className="choice-group">
                <legend className="label">Best time to contact you</legend>
                <div className="segmented">
                  {CONTACT_WINDOWS.map((option) => (
                    <label key={option.id} className="segment">
                      <input type="radio" name="window" checked={contactWindow === option.id} onChange={() => setContactWindow(option.id)} />
                      <span><strong>{option.title}</strong><small>{option.detail}</small></span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            {needsEmail && (
              <div className="field">
                <label htmlFor="consent-email">Your email address</label>
                <input id="consent-email" className="input input-lg" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} aria-describedby="consent-email-hint" />
                <p id="consent-email-hint" className="hint">Reminders go here. They never say what your medicine is for.</p>
              </div>
            )}
            {needsPin && (
              <div className="pin-box">
                <p className="label">Make a 4-digit PIN for phone calls</p>
                <p className="hint">Tomi asks for it before sharing any details, in case someone else answers your phone.</p>
                <div className="pin-fields">
                  <div className="field">
                    <label htmlFor="pin">PIN</label>
                    <input id="pin" className="input pin-input" inputMode="numeric" autoComplete="off" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ''))} />
                  </div>
                  <div className="field">
                    <label htmlFor="pin-confirm">Type it again</label>
                    <input id="pin-confirm" className="input pin-input" inputMode="numeric" autoComplete="off" maxLength={4} value={pinConfirm} onChange={(event) => setPinConfirm(event.target.value.replace(/\D/g, ''))} aria-describedby="pin-status" />
                  </div>
                </div>
                <p id="pin-status" className="hint" aria-live="polite">{pinConfirm.length === 4 && pin !== pinConfirm ? 'The two PINs do not match.' : ''}</p>
              </div>
            )}
          </>
        )}

        {step === 'consent' && (
          <>
            <h1 id="onboard-title" ref={headingRef} tabIndex={-1} className="onboard-title">Check and agree</h1>
            <dl className="summary-list">
              <div><dt>Language</dt><dd>{LANGUAGES.find((item) => item.name === language)?.native}</dd></div>
              <div><dt>Reading</dt><dd>{READING_LEVELS.find((item) => item.id === reading)?.title}</dd></div>
              <div><dt>Contact by</dt><dd>{channels.map((id) => CHANNELS.find((item) => item.id === id)?.title).join(', ')}</dd></div>
              {(channels.includes('voice') || channels.includes('sms')) && <div><dt>Best time</dt><dd>{CONTACT_WINDOWS.find((item) => item.id === contactWindow)?.detail}</dd></div>}
            </dl>
            <label className="check consent-check">
              <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
              <span>I agree that CareLoop and Tomi can contact me in these ways about my care plan. Texts and emails will not say what my medicine is for.</span>
            </label>
          </>
        )}

        {error && <p className="error-text" role="alert">{error}</p>}

        <div className="onboard-actions">
          <button type="button" className="btn btn-quiet btn-lg" onClick={back}>{index === 0 ? (editing ? 'Cancel' : 'Sign out') : 'Back'}</button>
          {step === 'consent' && <button type="button" className="btn btn-quiet btn-lg" onClick={() => setDeclined(true)}>No, thanks</button>}
          <button type="button" className="btn btn-primary btn-lg" onClick={next} disabled={!canContinue || busy}>
            {busy ? 'Saving…' : isLast ? (editing ? 'Save' : 'I agree, start') : 'Continue'}
          </button>
        </div>
      </section>
      <SafetyFooter />
    </main>
  );
}
