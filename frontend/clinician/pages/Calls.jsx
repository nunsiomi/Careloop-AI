import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { PhoneIncoming } from 'lucide-react';
import { CareLoopAPI } from '../../shared/api.js';
import { PRESENTER } from '../../shared/presenter.js';
import { dayLabel, duration, formatTime } from '../../shared/format.js';
import { ErrorNote, LanguageTag, LoadingBlock, StatusBadge, useAsync, useInterval, useToast } from '../../shared/ui.jsx';
import { Transcript, directionIcon } from '../components.jsx';
import { PageHeader } from '../shell.jsx';

const LIVE = ['initiated', 'ringing', 'answered', 'verified'];
const DIRECTION_LABEL = { outbound: 'Tomi called', inbound: 'Patient called Tomi', browser: 'Talked in the app' };

export default function Calls() {
  const query = useAsync(() => CareLoopAPI.listCalls(), []);
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const calls = query.data?.calls || [];
  const hasLive = calls.some((call) => LIVE.includes(call.status));
  useInterval(query.reload, hasLive ? 1500 : 15000);
  const selectedId = params.get('call') || calls[0]?.id;
  const selected = calls.find((call) => call.id === selectedId);

  const simulateInbound = async () => {
    try {
      const response = await CareLoopAPI.simulateInboundCall({ patient_id: 'p-zainab' });
      setParams({ call: response.call.id });
      query.reload();
      toast('Zainab Musa is calling Tomi.');
    } catch (error) { toast(error.message); }
  };

  return (
    <div className="page">
      <PageHeader title="Calls" sub="Every phone call with Tomi and every time a patient talked to Tomi in the app. A call can be answered without the patient being verified.">
        {PRESENTER && <button type="button" className="btn btn-secondary" onClick={simulateInbound}><PhoneIncoming aria-hidden="true" size={18} />Presenter: play an incoming call</button>}
      </PageHeader>
      {query.loading && !query.data && <LoadingBlock lines={6} />}
      <ErrorNote error={query.error} onRetry={query.reload} />
      {query.data && !calls.length && <p className="empty">No calls yet. To call a patient, open their record and choose Call now.</p>}
      {calls.length > 0 && (
        <div className="calls-grid">
          <ul className="call-index" aria-label="Calls">
            {calls.map((call) => {
              const Icon = directionIcon(call.direction);
              return (
                <li key={call.id}>
                  <button type="button" className="call-index-item" aria-current={call.id === selectedId ? 'true' : undefined} onClick={() => setParams({ call: call.id })}>
                    <Icon aria-hidden="true" size={18} />
                    <span className="call-index-main">
                      <strong>{call.patient_name}</strong>
                      <span className="muted">{DIRECTION_LABEL[call.direction]}, {dayLabel(call.started_at)} {formatTime(call.started_at)}</span>
                    </span>
                    <StatusBadge kind="call" status={call.status} />
                  </button>
                </li>
              );
            })}
          </ul>
          {selected && (
            <section className="panel call-panel" aria-labelledby="call-title" aria-live={LIVE.includes(selected.status) ? 'polite' : undefined}>
              <div className="split-head">
                <h2 id="call-title"><Link to={`/patients/${selected.patient_id}`}>{selected.patient_name}</Link></h2>
                <StatusBadge kind="call" status={selected.status} />
              </div>
              <dl className="facts">
                <div><dt>Type</dt><dd>{DIRECTION_LABEL[selected.direction]}</dd></div>
                <div><dt>Language</dt><dd><LanguageTag language={selected.language} /></dd></div>
                <div><dt>Identity</dt><dd>{selected.verification_state === 'verified' ? 'PIN verified' : selected.verification_state === 'pending' ? 'Checking' : selected.verification_state === 'not_reached' ? 'Not reached' : 'Not verified, so no details were shared'}</dd></div>
                <div><dt>Length</dt><dd>{duration(selected.started_at, selected.ended_at) || 'In progress'}</dd></div>
                {selected.outcome && <div><dt>Outcome</dt><dd>{selected.outcome}</dd></div>}
              </dl>
              <h3 className="section-title">Transcript</h3>
              <p className="muted">Written from speech recognition, with the English meaning underneath. Lines Tomi was unsure of are marked. Audio is not kept.</p>
              <Transcript call={selected} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}
