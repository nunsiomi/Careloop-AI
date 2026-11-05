import { useEffect, useId, useState } from 'react';
import { ChevronDown, Delete, Eye, EyeOff, Mail, MessageSquareText, PhoneCall, X } from 'lucide-react';
import { USE_MOCKS } from './api.js';
import { PHONE_COUNTRIES } from './format.js';
import { PRESENTER } from './presenter.js';

/* One input for the whole code, so screen readers and SMS autofill see a single field.
   The boxes behind it are drawn from its value. */
export function CodeInput({ id, label, value, onChange, length = 6, invalid = false, describedBy, autoFocus = false }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className={`code-input${invalid ? ' is-invalid' : ''}`} style={{ '--cells': length }}>
        <input
          id={id}
          className="code-input-field"
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/\D/g, '').slice(0, length))}
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={length}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          autoFocus={autoFocus}
          spellCheck={false}
        />
        <span className="code-input-cells" aria-hidden="true">
          {Array.from({ length }, (_, index) => (
            <span key={index} className={`code-cell${index < value.length ? ' is-filled' : ''}${index === Math.min(value.length, length - 1) ? ' is-next' : ''}`}>{value[index] || ''}</span>
          ))}
        </span>
      </div>
    </div>
  );
}

/* PIN entry for patients: large dots and a keypad, so it works without the phone keyboard.
   Keyboard users can type digits and Backspace straight into the field. */
export function PinPad({ label, value, onChange, onComplete, disabled = false, describedBy, tone = 'dark' }) {
  const inputId = useId();
  const add = (digit) => {
    if (disabled || value.length >= 4) return;
    const next = value + digit;
    onChange(next);
    if (next.length === 4) onComplete?.(next);
  };
  return (
    <div className={`pinpad pinpad-${tone}`}>
      <label htmlFor={inputId} className="pinpad-label">{label}</label>
      <input
        id={inputId}
        className="pinpad-field"
        type="password"
        inputMode="none"
        autoComplete="off"
        maxLength={4}
        value={value}
        disabled={disabled}
        aria-describedby={describedBy}
        onChange={(event) => {
          const next = event.target.value.replace(/\D/g, '').slice(0, 4);
          onChange(next);
          if (next.length === 4) onComplete?.(next);
        }}
      />
      <span className="pinpad-dots" aria-hidden="true">
        {[0, 1, 2, 3].map((index) => <span key={index} className={index < value.length ? 'is-filled' : ''} />)}
      </span>
      <div className="pinpad-keys" role="group" aria-label="Keypad">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((digit) => (
          <button key={digit} type="button" className="pinpad-key" disabled={disabled} onClick={() => add(digit)}>{digit}</button>
        ))}
        <span />
        <button type="button" className="pinpad-key" disabled={disabled} onClick={() => add('0')}>0</button>
        <button type="button" className="pinpad-key pinpad-del" disabled={disabled || !value} onClick={() => onChange(value.slice(0, -1))} aria-label="Delete last number"><Delete aria-hidden="true" /></button>
      </div>
    </div>
  );
}

export function PasswordField({ id, label, value, onChange, autoComplete = 'current-password', describedBy, invalid = false, autoFocus = false }) {
  const [shown, setShown] = useState(false);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="password-field">
        <input id={id} className="input input-lg" type={shown ? 'text' : 'password'} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} aria-describedby={describedBy} aria-invalid={invalid || undefined} autoFocus={autoFocus} spellCheck={false} />
        <button type="button" className="btn btn-quiet btn-icon" onClick={() => setShown((current) => !current)} aria-pressed={shown} aria-label={shown ? 'Hide password' : 'Show password'}>
          {shown ? <EyeOff aria-hidden="true" size={20} /> : <Eye aria-hidden="true" size={20} />}
        </button>
      </div>
    </div>
  );
}

/* Country picker plus the number. The value is "+<dial> <number as typed>", or the typed text as-is when it
   starts with +, so numbers from countries not in the list still work. */
export function PhoneField({ id, label, value, onChange, describedBy, invalid = false, autoFocus = false }) {
  const [countryId, setCountryId] = useState(PHONE_COUNTRIES[0].id);
  const country = PHONE_COUNTRIES.find((item) => item.id === countryId);
  const prefix = `+${country.dial} `;
  const national = value.startsWith(prefix) ? value.slice(prefix.length) : value;
  const emit = (text, next = country) => onChange(!text ? '' : text.trim().startsWith('+') ? text : `+${next.dial} ${text}`);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="phone-field">
        <span className="phone-prefix">
          <span aria-hidden="true">+{country.dial}</span>
          <ChevronDown aria-hidden="true" size={16} />
          <select aria-label="Country" value={countryId} onChange={(event) => { const next = PHONE_COUNTRIES.find((item) => item.id === event.target.value); setCountryId(next.id); emit(national, next); }}>
            {PHONE_COUNTRIES.map((item) => <option key={item.id} value={item.id}>{item.name} (+{item.dial})</option>)}
          </select>
        </span>
        <input id={id} className="input input-lg" type="tel" inputMode="tel" autoComplete="tel-national" placeholder={country.example} value={national} onChange={(event) => emit(event.target.value.replace(/[^\d\s+]/g, '').slice(0, 18))} aria-describedby={describedBy} aria-invalid={invalid || undefined} autoFocus={autoFocus} />
      </div>
    </div>
  );
}

/* Counts down to zero once a second; restart by changing `from`. */
export function useCountdown(from, key) {
  const [left, setLeft] = useState(from);
  useEffect(() => {
    setLeft(from);
    if (!from) return undefined;
    const timer = window.setInterval(() => setLeft((value) => (value <= 1 ? (window.clearInterval(timer), 0) : value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [from, key]);
  return left;
}

export const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

/* Signs a person out after a quiet spell. Shared ward computers and family phones need it. */
export function useIdle(minutes, onIdle, enabled = true) {
  useEffect(() => {
    if (!enabled || !minutes) return undefined;
    let timer;
    const reset = () => { window.clearTimeout(timer); timer = window.setTimeout(onIdle, minutes * 60 * 1000); };
    const events = ['pointerdown', 'keydown', 'scroll', 'touchstart'];
    events.forEach((name) => window.addEventListener(name, reset, { passive: true }));
    reset();
    return () => { window.clearTimeout(timer); events.forEach((name) => window.removeEventListener(name, reset)); };
  }, [minutes, onIdle, enabled]);
}

/* Presenter mode only (?presenter=1): what to type on this screen. Nobody else sees it. */
export function PresenterNote({ items, open = false }) {
  if (!PRESENTER || !items?.length) return null;
  return (
    <details className="demo-hint" open={open}>
      <summary>Presenter notes</summary>
      <dl>{items.map(([term, value]) => <div key={term} style={{ display: 'contents' }}><dt>{term}</dt><dd>{value}</dd></div>)}</dl>
    </details>
  );
}

/* With in-browser data no real SMS, call or email goes out, so the message the person would receive
   appears at the top of the screen, the way a phone shows a new text. */
export function IncomingMessage({ message, onDismiss }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => { setHidden(false); }, [message?.text]);
  if (!USE_MOCKS || !message || hidden) return null;
  const Icon = message.channel === 'voice' ? PhoneCall : message.channel === 'email' ? Mail : MessageSquareText;
  return (
    <aside className="incoming" role="status" aria-label={`New ${message.channel === 'voice' ? 'call' : message.channel === 'email' ? 'email' : 'text message'}`}>
      <span className="incoming-icon" aria-hidden="true"><Icon size={18} /></span>
      <span className="incoming-body">
        <span className="incoming-from">{message.from}<span>now</span></span>
        <span className="incoming-text">{message.text}</span>
        {message.link && <a className="incoming-link" href={message.link.href}>{message.link.label}</a>}
      </span>
      <button type="button" className="incoming-close" aria-label="Dismiss" onClick={() => { setHidden(true); onDismiss?.(); }}><X aria-hidden="true" size={18} /></button>
    </aside>
  );
}
