import { useState } from 'react';
import { LegalLinks } from './Legal.jsx';
import { KeyRound, LogOut, Mail, MessageCircle, MessageSquareText, Phone, UserMinus, UserPlus } from 'lucide-react';
import { CareLoopAPI } from '../shared/api.js';
import { PhoneField } from '../shared/auth-ui.jsx';
import { CHANNELS, CONTACT_WINDOWS, READING_LEVELS } from '../shared/languages.js';
import { formatDateLong, whenLabel } from '../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, Modal, StatusBadge, useAsync, useToast } from '../shared/ui.jsx';

const RELATIONS = ['Daughter', 'Son', 'Wife', 'Husband', 'Sister', 'Brother', 'Mother', 'Father', 'Friend', 'Other family'];

export default function AccountScreen({ session, patient, headingRef, onSignOut, onPatientChange }) {
  const helper = session.kind === 'caregiver';
  const [confirmForget, setConfirmForget] = useState(false);
  const reading = READING_LEVELS.find((item) => item.id === patient.literacy_level);
  const contactWindow = CONTACT_WINDOWS.find((item) => item.id === patient.contact_window);

  return (
    <div className="screen account">
      <header className="account-head">
        <span className="account-avatar" aria-hidden="true">{session.user_name.charAt(0)}</span>
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="screen-title">{session.user_name}</h1>
          <p className="screen-sub">{helper ? `${session.relation || 'Helper'} of ${patient.name}` : 'Patient'}. Signed in on this phone.</p>
        </div>
      </header>

      <section className="settings-group" aria-labelledby="set-tomi">
        <h2 id="set-tomi" className="sheet-title">How Tomi talks {helper ? `to ${patient.name.split(' ')[0]}` : 'to you'}</h2>
        <dl className="settings-list">
          <div><dt>Language</dt><dd><LanguageTag language={patient.language} native /></dd></div>
          <div><dt>Reading</dt><dd>{reading?.title || 'Not set'}</dd></div>
          {contactWindow && <div><dt>Best time</dt><dd>{contactWindow.title}, {contactWindow.detail}</dd></div>}
        </dl>
        {!helper && <a className="btn btn-secondary btn-lg" href="#/preferences">Change language or reading</a>}
      </section>

      <ContactChoices patient={patient} helper={helper} onPatientChange={onPatientChange} />
      <RecentMessages patient={patient} helper={helper} />

      {!helper && <Helpers patient={patient} />}

      <section className="settings-group" aria-labelledby="set-security">
        <h2 id="set-security" className="sheet-title">PIN and signing out</h2>
        <p className="hint">Your PIN opens CareLoop on this phone{helper ? '' : ' and proves it is you when Tomi calls'}.</p>
        <div className="settings-actions">
          <a className="btn btn-secondary btn-lg" href="#/set-pin"><KeyRound aria-hidden="true" size={20} />Change my PIN</a>
          <button type="button" className="btn btn-secondary btn-lg" onClick={() => onSignOut()}><LogOut aria-hidden="true" size={20} />Sign out</button>
          <button type="button" className="btn btn-quiet btn-lg" onClick={() => setConfirmForget(true)}>Sign out and forget this phone</button>
        </div>
      </section>

      <section className="settings-group" aria-labelledby="set-legal">
        <h2 id="set-legal" className="sheet-title">Your information</h2>
        <p className="hint">You can ask your care team to show you, correct or delete what CareLoop keeps about you.</p>
        <LegalLinks />
      </section>

      {confirmForget && (
        <Modal title="Forget this phone?" onClose={() => setConfirmForget(false)}>
          <p>Use this if the phone is shared or not yours. Next time, CareLoop will send a new code to sign in instead of asking for your PIN.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setConfirmForget(false)}>Cancel</button>
            <button type="button" className="btn btn-primary" onClick={() => onSignOut({ forget: true })}>Sign out and forget</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

const CHANNEL_ICON = { web: MessageCircle, voice: Phone, sms: MessageSquareText, email: Mail };

/* Each channel is a separate choice the patient can withdraw at any time (doc v2, section 19). */
function ContactChoices({ patient, helper, onPatientChange }) {
  const [busy, setBusy] = useState(null);
  const toast = useToast();
  const first = patient.name.split(' ')[0];

  const toggle = async (channel) => {
    const on = patient.channels.includes(channel.id);
    const channels = on ? patient.channels.filter((item) => item !== channel.id) : [...patient.channels, channel.id];
    setBusy(channel.id);
    try {
      const { patient: updated } = await CareLoopAPI.updateConsent(patient.id, { channels });
      onPatientChange?.(updated);
      toast(on ? `${channel.title} turned off.` : `${channel.title} turned on.`);
    } catch (error) { toast(error.message); }
    setBusy(null);
  };

  return (
    <section className="settings-group" aria-labelledby="set-contact">
      <h2 id="set-contact" className="sheet-title">How we contact {helper ? first : 'you'}</h2>
      <p className="hint">{helper ? `Only ${first} can change these.` : 'You can turn any of these off at any time. Your care team will still see your plan.'}</p>
      <ul className="channel-switches">
        {CHANNELS.map((channel) => {
          const Icon = CHANNEL_ICON[channel.id];
          const on = patient.channels.includes(channel.id);
          const noEmail = channel.id === 'email' && !patient.email;
          const unavailable = channel.available === false && !on;
          return (
            <li key={channel.id}>
              <Icon aria-hidden="true" size={22} />
              <span className="channel-switch-text" id={`ch-${channel.id}`}>
                <strong>{channel.title}</strong>
                <span>{noEmail ? 'Ask your care team to add an email address first.' : unavailable ? channel.unavailable : channel.detail}</span>
              </span>
              {channel.id === 'web'
                ? <span className="switch-note">Always on</span>
                : (
                  <button type="button" role="switch" className="switch" aria-checked={on} aria-labelledby={`ch-${channel.id}`} disabled={helper || noEmail || unavailable || busy === channel.id} onClick={() => toggle(channel)}>
                    <span className="switch-knob" aria-hidden="true" />
                    <span className="switch-label" aria-hidden="true">{on ? 'On' : 'Off'}</span>
                  </button>
                )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function RecentMessages({ patient, helper }) {
  const query = useAsync(() => CareLoopAPI.listNotifications({ patient_id: patient.id }), [patient.id, patient.channels.join()]);
  const items = (query.data?.notifications || []).filter((item) => item.status !== 'cancelled').slice(0, 5);
  if (!patient.channels.some((channel) => ['sms', 'email'].includes(channel)) && !items.length) return null;
  return (
    <section className="settings-group" aria-labelledby="set-texts">
      <h2 id="set-texts" className="sheet-title">Texts and emails</h2>
      <p className="hint">Exactly what we sent. Texts never name a medicine or an illness, in case someone else reads the phone.</p>
      {query.loading && !query.data && <LoadingBlock lines={2} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !items.length && <p className="helper-empty">Nothing sent yet.</p>}
      <ul className="message-list">
        {items.map((item) => (
          <li key={item.id}>
            <p className="message-meta">
              <strong>{item.title}</strong>
              <span>{item.status === 'scheduled' ? 'Sends' : 'Sent'} {whenLabel(item.scheduled_for)} by {item.channel === 'sms' ? 'text' : 'email'}</span>
            </p>
            <p className="message-body">{item.body}</p>
            <StatusBadge kind="message" status={item.status} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Helpers({ patient }) {
  const query = useAsync(() => CareLoopAPI.listCaregivers(patient.id), [patient.id]);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState(null);
  const toast = useToast();

  const remove = async () => {
    try {
      await CareLoopAPI.removeCaregiver(patient.id, removing.id);
      toast(`${removing.name} can no longer see your care.`);
      setRemoving(null);
      query.reload();
    } catch (error) { toast(error.message); }
  };

  return (
    <section className="settings-group" aria-labelledby="set-helpers">
      <h2 id="set-helpers" className="sheet-title">People helping you</h2>
      <p className="hint">A helper can see your plan, tasks and visits and tell Tomi how you are doing. They cannot change your plan.</p>
      {query.loading && !query.data && <LoadingBlock lines={2} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && (
        <ul className="helper-list">
          {query.data.caregivers.map((helper) => (
            <li key={helper.id}>
              <span className="helper-initial" aria-hidden="true">{helper.name.charAt(0)}</span>
              <span className="helper-text"><strong>{helper.name}</strong><span>{helper.relation}, {helper.masked_phone}. Added {formatDateLong(helper.added_at)}.</span></span>
              <button type="button" className="btn btn-quiet" onClick={() => setRemoving(helper)}><UserMinus aria-hidden="true" size={18} />Remove<span className="sr-only"> {helper.name}</span></button>
            </li>
          ))}
          {query.data.invites.map((invite) => (
            <li key={invite.code} className="is-pending">
              <span className="helper-initial" aria-hidden="true">{invite.name.charAt(0)}</span>
              <span className="helper-text"><strong>{invite.name}</strong><span>Invited, has not joined yet. Code {invite.code}.</span></span>
              <button type="button" className="btn btn-quiet" onClick={() => setRemoving({ id: invite.code, name: invite.name })}>Cancel<span className="sr-only"> invite for {invite.name}</span></button>
            </li>
          ))}
          {!query.data.caregivers.length && !query.data.invites.length && <li className="helper-empty">No one yet.</li>}
        </ul>
      )}
      <button type="button" className="btn btn-secondary btn-lg" onClick={() => setAdding(true)}><UserPlus aria-hidden="true" size={20} />Invite someone to help</button>

      {adding && <InviteHelperDialog patient={patient} onClose={() => setAdding(false)} onDone={() => { setAdding(false); query.reload(); }} />}
      {removing && (
        <Modal title={`Remove ${removing.name}?`} onClose={() => setRemoving(null)}>
          <p>They will stop seeing your plan, tasks and visits straight away. You can invite them again later.</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setRemoving(null)}>Keep</button>
            <button type="button" className="btn btn-primary" onClick={remove}>Remove</button>
          </div>
        </Modal>
      )}
    </section>
  );
}

function InviteHelperDialog({ patient, onClose, onDone }) {
  const [name, setName] = useState('');
  const [relation, setRelation] = useState(RELATIONS[0]);
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(null);
  const toast = useToast();

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { invite } = await CareLoopAPI.inviteCaregiver(patient.id, { name, relation, phone, email });
      setSent(invite);
      toast(`Invite sent to ${invite.name}.`);
    } catch (requestError) { setError(requestError.message); }
    setBusy(false);
  };

  if (sent) {
    return (
      <Modal title="Invite sent" onClose={onDone}>
        <p>{sent.name} will get an email with a link and the code <strong>{sent.code}</strong>. You can also tell them the code yourself. It works once.</p>
        <div className="modal-actions"><button type="button" className="btn btn-primary" onClick={onDone}>Done</button></div>
      </Modal>
    );
  }

  return (
    <Modal title="Invite someone to help" onClose={onClose}>
      <form className="auth-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="helper-name">Their name</label>
          <input id="helper-name" className="input input-lg" value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor="helper-relation">They are your</label>
          <select id="helper-relation" className="select input-lg" value={relation} onChange={(event) => setRelation(event.target.value)}>
            {RELATIONS.map((item) => <option key={item}>{item}</option>)}
          </select>
        </div>
        <PhoneField id="helper-phone-new" label="Their phone number" value={phone} onChange={setPhone} invalid={Boolean(error)} describedBy={error ? 'helper-error' : undefined} />
        <div className="field">
          <label htmlFor="helper-email">Their email address</label>
          <input id="helper-email" className="input input-lg" type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} aria-describedby="helper-email-hint" />
          <p id="helper-email-hint" className="hint">We email them the invite and their sign-in codes.</p>
        </div>
        {error && <p id="helper-error" className="field-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Sending…' : 'Send invite'}</button>
        </div>
      </form>
    </Modal>
  );
}
