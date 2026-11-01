import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { languageInfo } from './languages.js';

/* ---------- badges ---------- */

export function Badge({ tone = 'neutral', icon: Icon, children, ...rest }) {
  return <span className={`badge badge-${tone}`} {...rest}>{Icon && <Icon aria-hidden="true" />}{children}</span>;
}

export function BetaChip() {
  return <Badge tone="beta" title="This language is still being checked by native speakers">Beta</Badge>;
}

export function LanguageTag({ language, native = false }) {
  const info = languageInfo(language);
  return (
    <span className="lang-tag">
      <span>{native ? info.native : info.name}</span>
      {info.beta && <BetaChip />}
    </span>
  );
}

const STATUS = {
  plan: {
    needs_review: ['Needs review', 'amber'], approved: ['Approved', 'green'], not_created: ['No plan yet', 'neutral'], archived: ['Archived', 'neutral']
  },
  task: {
    pending: ['Due', 'neutral'], patient_reported_done: ['Patient said done', 'green'], clinician_verified: ['Verified', 'green'],
    unable: ['Could not do', 'amber'], overdue: ['Overdue', 'amber'], cancelled: ['Cancelled', 'neutral']
  },
  appointment: {
    requested: ['Requested', 'neutral'], scheduled: ['Booked', 'neutral'], confirmed: ['Confirmed', 'green'], reschedule_requested: ['Move requested', 'amber'],
    rescheduled: ['Moved', 'purple'], attended: ['Attended', 'green'], no_show: ['Did not attend', 'amber'], cancelled: ['Replaced', 'neutral']
  },
  barrier: {
    open: ['Open', 'amber'], option_offered: ['Option offered', 'amber'], awaiting_response: ['Waiting for patient', 'amber'],
    resolved_patient_reported: ['Patient said resolved', 'green'], resolved_verified: ['Resolved', 'green'], escalated: ['Sent to care team', 'amber']
  },
  // Red only for escalations a human has not yet acknowledged.
  escalation: {
    created: ['Not acknowledged', 'red'], notification_attempted: ['Not acknowledged', 'red'], delivered: ['Not acknowledged', 'red'],
    acknowledged: ['Acknowledged', 'amber'], acted_on: ['Acted on', 'amber'], resolved: ['Resolved', 'green']
  },
  call: {
    initiated: ['Starting', 'purple'], ringing: ['Ringing', 'purple'], answered: ['Answered', 'purple'], verified: ['In call, verified', 'purple'],
    unverified: ['Not verified', 'amber'], disconnected: ['Disconnected', 'neutral'], completed: ['Completed', 'neutral'], failed: ['No answer', 'amber']
  },
  message: {
    scheduled: ['Scheduled', 'neutral'], sent: ['Sent', 'purple'], delivered: ['Delivered', 'green'], failed: ['Not delivered', 'amber'], cancelled: ['Cancelled', 'neutral']
  },
  verification: {
    self_reported: ['Patient said', 'tomi'], clinician_verified: ['Clinician verified', 'green'], system_recorded: ['System', 'neutral'], provider_status: ['Provider status', 'purple']
  }
};

export function StatusBadge({ kind, status }) {
  const [label, tone] = STATUS[kind]?.[status] || [status?.replaceAll('_', ' ') || 'Unknown', 'neutral'];
  return <Badge tone={tone}>{label}</Badge>;
}

export const statusLabel = (kind, status) => STATUS[kind]?.[status]?.[0] || status;

/* ---------- modal ---------- */

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useDialogFocus(dialogRef, onClose, initialFocus) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const root = document.getElementById('root');
    root?.setAttribute('inert', '');
    const dialog = dialogRef.current;
    const target = (initialFocus && dialog.querySelector(initialFocus)) || dialog.querySelector(FOCUSABLE);
    target?.focus();
    const onKey = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== 'Tab') return;
      const items = [...dialog.querySelectorAll(FOCUSABLE)];
      if (!items.length) return;
      const first = items[0];
      const last = items.at(-1);
      if (!dialog.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      root?.removeAttribute('inert');
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [dialogRef, initialFocus]);
}

export function Modal({ title, onClose, children, wide = false, initialFocus }) {
  const dialogRef = useRef(null);
  const titleId = useId();
  useDialogFocus(dialogRef, onClose, initialFocus);

  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={dialogRef} className={`modal${wide ? ' modal-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="btn btn-quiet btn-icon" onClick={onClose} aria-label="Close"><X aria-hidden="true" /></button>
        </div>
        {children}
      </section>
    </div>,
    document.body
  );
}

/* ---------- toasts ---------- */

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message) => {
    const toastId = Math.random().toString(36).slice(2);
    setToasts((current) => [...current, { id: toastId, message }]);
    window.setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== toastId)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      {createPortal(
        <div className="toast-region" role="status" aria-live="polite">
          {toasts.map((toast) => <div key={toast.id} className="toast">{toast.message}</div>)}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ---------- data hooks ---------- */

export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true }));
    loaderRef.current()
      .then((data) => { if (active) setState({ data, error: null, loading: false }); })
      .catch((error) => { if (active) setState({ data: null, error, loading: false }); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

export function useInterval(callback, ms, enabled = true) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  useEffect(() => {
    if (!enabled) return undefined;
    const timer = window.setInterval(() => callbackRef.current(), ms);
    return () => window.clearInterval(timer);
  }, [ms, enabled]);
}

/* ---------- states ---------- */

export function LoadingBlock({ lines = 3, label = 'Loading' }) {
  return (
    <div role="status" aria-label={label} className="loading-block">
      {Array.from({ length: lines }, (_, index) => <div key={index} className="skeleton" style={{ height: 16, width: `${90 - index * 15}%`, marginBottom: 10 }} />)}
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="empty" role="alert">
      <p className="error-text">{error.message}</p>
      {onRetry && <button type="button" className="btn btn-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}
