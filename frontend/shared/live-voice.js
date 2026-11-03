// Live Tomi in the browser: joins the LiveKit room from createVoiceSession, sends the microphone, plays Tomi,
// and reports Tomi's state, captions and escalations. Like api.js, this is network code, so components use it
// instead of touching livekit-client. Loaded only when a live session starts, to keep the app bundle small.

const AGENT_STATES = { initializing: 'connecting', listening: 'listening', thinking: 'thinking', speaking: 'speaking' };

/**
 * @param session  { url, token } from CareLoopAPI.createVoiceSession (mode "livekit")
 * @param on       { phase(name), caption({ key, speaker, transcript }), escalation(), needsTap(bool), ended() }
 * @returns        { disconnect(), startAudio() }
 */
export async function connectLiveVoice(session, on) {
  const { Room, RoomEvent, Track } = await import('livekit-client');
  const room = new Room({ adaptiveStream: true, dynacast: true });
  const audioElements = new Set();
  let closed = false;

  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind !== Track.Kind.Audio) return;
    const element = track.attach();
    element.dataset.tomiAudio = '';
    document.body.appendChild(element);
    audioElements.add(element);
  });
  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    track.detach().forEach((element) => { element.remove(); audioElements.delete(element); });
  });
  room.on(RoomEvent.AudioPlaybackStatusChanged, () => on.needsTap(!room.canPlaybackAudio));
  room.on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
    if (participant === room.localParticipant) return;
    const state = changed['lk.agent.state'];
    if (state && AGENT_STATES[state]) on.phase(AGENT_STATES[state]);
    if (changed['careloop.escalation'] === 'open') on.escalation();
  });
  // Tomi leaving (end of call, PIN-free browser session closed by the worker) ends the conversation.
  room.on(RoomEvent.ParticipantDisconnected, () => { if (!closed) on.ended(); });
  room.on(RoomEvent.Disconnected, () => { if (!closed) on.ended(); });

  // Captions: the worker streams both sides of the conversation as text.
  room.registerTextStreamHandler('lk.transcription', async (reader, participant) => {
    const ownTracks = new Set([...room.localParticipant.trackPublications.values()].map((pub) => pub.trackSid));
    const trackId = reader.info.attributes?.['lk.transcribed_track_id'];
    const speaker = participant.identity === room.localParticipant.identity || (trackId && ownTracks.has(trackId)) ? 'patient' : 'tomi';
    let transcript = '';
    for await (const chunk of reader) {
      transcript += chunk;
      on.caption({ key: reader.info.id, speaker, transcript });
    }
  });

  await room.connect(session.url, session.token);
  await room.localParticipant.setMicrophoneEnabled(true);
  await room.startAudio().catch(() => {});
  on.needsTap(!room.canPlaybackAudio);

  return {
    disconnect() {
      closed = true;
      room.disconnect();
      audioElements.forEach((element) => element.remove());
    },
    startAudio: () => room.startAudio()
  };
}
