import { useState } from 'react';
import { KeyRound, LogOut, Monitor } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { PasswordField } from '../../shared/auth-ui.jsx';
import { relativeTime } from '../../shared/format.js';
import { ErrorNote, LoadingBlock, Modal, useAsync, useToast } from '../../shared/ui.jsx';
import { MfaBadge } from '../Auth.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

export default function Account() {
  const { user, signOut } = useDashboard();
  const sessions = useAsync(() => CareLoopAPI.listStaffSessions(), []);
  const [changing, setChanging] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);

  return (
    <div className="page account-page">
      <PageHeader title="Account and security" sub="Your sign-in details for CareLoop." />

      <div className="account-grid">
        <section className="panel" aria-labelledby="profile-title">
          <h2 id="profile-title">Profile</h2>
          <dl className="facts">
            <div><dt>Name</dt><dd>{user.name}</dd></div>
            <div><dt>Email</dt><dd>{user.email}</dd></div>
            <div><dt>Role</dt><dd>{user.role}</dd></div>
            <div><dt>Care facility</dt><dd>{user.facility}</dd></div>
          </dl>
          <p className="muted">To change your name, role, email or care facility, ask your facility's CareLoop admin.</p>
        </section>

        <section className="panel" aria-labelledby="security-title">
          <h2 id="security-title">Signing in</h2>
          <dl className="facts">
            <div><dt>Password</dt><dd><button type="button" className="btn btn-secondary" onClick={() => setChanging(true)}><KeyRound aria-hidden="true" size={18} />Change password</button></dd></div>
            <div><dt>Sign-in code</dt><dd className="inline-meta"><MfaBadge /><span className="muted">Sent to {user.email} each time you sign in</span></dd></div>
            <div><dt>Auto-lock</dt><dd>After 15 minutes with no activity</dd></div>
          </dl>
        </section>

        <section className="panel account-sessions" aria-labelledby="sessions-title">
          <div className="panel-head">
            <h2 id="sessions-title">Where you are signed in</h2>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmAll(true)}><LogOut aria-hidden="true" size={18} />Sign out everywhere</button>
          </div>
          {sessions.loading && !sessions.data && <LoadingBlock lines={2} />}
          <ErrorNote error={sessions.error} onRetry={sessions.reload} />
          <ul className="session-list">
            {(sessions.data?.sessions || []).map((item) => (
              <li key={item.id}>
                <Monitor aria-hidden="true" size={20} />
                <span><strong>{item.device}</strong>{item.current && <span className="badge badge-purple">This computer</span>}</span>
                <span className="muted">Signed in {relativeTime(item.signed_in_at)}, last active {relativeTime(item.last_seen_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {changing && <ChangePasswordDialog email={user.email} onClose={() => setChanging(false)} />}
      {confirmAll && (
        <Modal title="Sign out everywhere?" onClose={() => setConfirmAll(false)}>
          <p>This signs you out on every computer, including this one. Use it if you left CareLoop open on a ward computer.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setConfirmAll(false)}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={() => signOut({ everywhere: true, notice: 'You are signed out on every computer.' })}>Sign out everywhere</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ChangePasswordDialog({ email, onClose }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await CareLoopAPI.changePassword({ current, next });
      toast('Password changed. Other computers have been signed out.');
      onClose();
    } catch (requestError) { setError(requestError.message); setBusy(false); }
  };

  return (
    <Modal title="Change password" onClose={onClose}>
      <form className="staff-form" onSubmit={submit}>
        <input type="email" value={email} autoComplete="username" readOnly hidden />
        <PasswordField id="current-password" label="Current password" value={current} onChange={setCurrent} />
        <PasswordField id="next-password" label="New password" value={next} onChange={setNext} autoComplete="new-password" describedBy="next-hint" />
        <p id="next-hint" className="hint">At least 8 characters. A short phrase works well.</p>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy || !current || next.length < 8}>{busy ? 'Saving…' : 'Change password'}</button>
        </div>
      </form>
    </Modal>
  );
}
