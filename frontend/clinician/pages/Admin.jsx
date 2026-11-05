import { useState } from 'react';
import { KeyRound, UserMinus } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { formatDate, relativeTime } from '../../shared/format.js';
import { Badge, ErrorNote, LoadingBlock, Modal, useAsync, useToast } from '../../shared/ui.jsx';
import { PageHeader, useDashboard } from '../shell.jsx';

const NEW_FOR_DAYS = 14;
const isNew = (iso) => iso && Date.now() - new Date(iso).getTime() < NEW_FOR_DAYS * 864e5;

// For the care facility's CareLoop admin: the staff join code, and who has an account here.
export default function Admin() {
  const { user } = useDashboard();
  const query = useAsync(() => CareLoopAPI.getAdminFacility(), []);
  const [confirmCode, setConfirmCode] = useState(false);
  const [removing, setRemoving] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const data = query.data;
  const newCount = (data?.staff || []).filter((member) => isNew(member.joined_at) && member.id !== user.id).length;

  const makeCode = async () => {
    setBusy(true);
    try {
      const { join_code: code } = await CareLoopAPI.newJoinCode();
      toast(`New join code: ${code}. The old one no longer works.`);
      setConfirmCode(false);
      query.reload();
    } catch (error) { toast(error.message); }
    setBusy(false);
  };
  const remove = async () => {
    setBusy(true);
    try {
      await CareLoopAPI.removeStaff(removing.id);
      toast(`${removing.name} can no longer sign in.`);
      setRemoving(null);
      query.reload();
    } catch (error) { toast(error.message); }
    setBusy(false);
  };

  return (
    <div className="page admin-page">
      <PageHeader title="Facility admin" sub={data ? data.facility.name : 'Your care facility'} />
      {query.loading && !data && <LoadingBlock lines={4} />}
      <ErrorNote error={query.error} onRetry={query.reload} />

      {data && (
        <div className="admin-grid">
          <section className="panel" aria-labelledby="code-title">
            <h2 id="code-title">Staff join code</h2>
            <p className="join-code" aria-label={`Join code ${data.facility.join_code.split('').join(' ')}`}>{data.facility.join_code}</p>
            <p className="muted">Give it only to staff at {data.facility.name}. Anyone with this code and the facility name can create an account here.</p>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmCode(true)}><KeyRound aria-hidden="true" size={18} />Make a new code</button>
          </section>

          <section className="panel admin-team" aria-labelledby="team-title">
            <div className="panel-head">
              <h2 id="team-title">Care team</h2>
              {newCount > 0 && <Badge tone="purple">{newCount} new in the last {NEW_FOR_DAYS} days</Badge>}
            </div>
            <div className="table-wrap" role="region" aria-label="Care team" tabIndex={0}>
              <table className="table">
                <caption className="sr-only">Care team at {data.facility.name}, newest first</caption>
                <thead>
                  <tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Email</th><th scope="col">Joined</th><th scope="col">Last active</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
                </thead>
                <tbody>
                  {data.staff.map((member) => (
                    <tr key={member.id}>
                      <td>
                        <span className="inline-meta">
                          <strong>{member.name}</strong>
                          {member.id === user.id && <Badge tone="neutral">You</Badge>}
                          {member.is_admin && <Badge tone="purple">Admin</Badge>}
                          {isNew(member.joined_at) && member.id !== user.id && <Badge tone="amber">New</Badge>}
                        </span>
                      </td>
                      <td>{member.role}</td>
                      <td>{member.email}</td>
                      <td>{member.joined_at ? formatDate(member.joined_at) : <span className="muted">Before records began</span>}</td>
                      <td>{member.last_seen_at ? relativeTime(member.last_seen_at) : <span className="muted">Not yet</span>}</td>
                      <td>
                        {member.id !== user.id && (
                          <button type="button" className="btn btn-quiet" onClick={() => setRemoving(member)}>
                            <UserMinus aria-hidden="true" size={18} />Remove<span className="sr-only"> {member.name}</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Someone you do not recognise? Remove them, then make a new join code.</p>
          </section>
        </div>
      )}

      {confirmCode && (
        <Modal title="Make a new join code?" onClose={() => setConfirmCode(false)}>
          <p>The current code stops working at once. Staff who already have an account are not affected. Give the new code to anyone who still needs to join.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setConfirmCode(false)}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={makeCode} disabled={busy}>Make a new code</button>
          </div>
        </Modal>
      )}
      {removing && (
        <Modal title={`Remove ${removing.name}?`} onClose={() => setRemoving(null)}>
          <p>They are signed out everywhere and can no longer sign in to {data.facility.name}. Patients they lead become unassigned. Their past notes stay on the timeline.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setRemoving(null)}>Keep</button>
            <button type="button" className="btn btn-primary" onClick={remove} disabled={busy}>Remove</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
