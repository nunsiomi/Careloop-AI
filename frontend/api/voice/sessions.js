// POST /api/voice/sessions: a short-lived LiveKit token so the patient app can talk to Tomi in the browser.
// Runs as a Vercel function on the team preview, and inside Vite during `npm run dev` (vite.config.js).
// It stands in for the backend route of the same name (docs/api_shapes.md) until FastAPI exists; it signs the
// token itself, so it needs no npm package. Without LIVEKIT_* settings it answers 503 and the app falls back to
// the scripted voice demo.
//
// No real patient data passes through here: the sample patient's id goes to the Tomi worker, which loads the
// plan from its own mock. The real backend must check the patient's session before issuing a token.
import { createHmac, randomBytes } from 'node:crypto';

const AGENT_NAME = 'tomi';
const TOKEN_SECONDS = 15 * 60;

const base64url = (value) => Buffer.from(value).toString('base64url');

function signToken(claims, secret) {
  const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = base64url(JSON.stringify(claims));
  const signature = createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url');
  return `${header}.${payload}.${signature}`;
}

async function readBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  } catch {
    return {};
  }
}

function send(res, status, data) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(data));
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { detail: 'Use POST.' });
  const { LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET } = process.env;
  if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) return send(res, 503, { detail: 'Voice is not set up here.' });

  const body = await readBody(req);
  const patientId = String(body.patient_id || '');
  if (!/^p-[a-z0-9-]{1,40}$/.test(patientId)) return send(res, 400, { detail: 'Unknown patient.' });
  const language = typeof body.language === 'string' ? body.language.slice(0, 20) : '';

  const room = `voice-${randomBytes(6).toString('hex')}`;
  const identity = `patient-${randomBytes(4).toString('hex')}`;
  const now = Math.floor(Date.now() / 1000);
  const token = signToken({
    iss: LIVEKIT_API_KEY,
    sub: identity,
    nbf: now - 10,
    exp: now + TOKEN_SECONDS,
    name: 'Patient',
    video: { room, roomJoin: true, canPublish: true, canSubscribe: true, canPublishData: true },
    attributes: { 'careloop.patient_id': patientId },
    // Asks LiveKit to send the Tomi worker into this new room, with the patient and language as job metadata.
    roomConfig: {
      maxParticipants: 2,
      emptyTimeout: 60,
      agents: [{ agentName: AGENT_NAME, metadata: JSON.stringify({ patient_id: patientId, language }) }]
    }
  }, LIVEKIT_API_SECRET);

  return send(res, 200, { session: { id: room, mode: 'livekit', url: LIVEKIT_URL, token, language } });
}
