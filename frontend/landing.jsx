import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Mail, Mic, Phone, PhoneIncoming } from 'lucide-react';
import LoopArt from './shared/LoopArt.jsx';
import './shared/fonts.js';
import './shared/base.css';
import './landing.css';

const FLOW = [
  ['A nurse or doctor adds the patient', 'They paste in the discharge note, the same one the patient goes home with.'],
  ['CareLoop drafts the plan, and checks it', 'One agent turns the note into medicines, visits and warning signs. A second agent compares every field with the note and flags anything unclear. Neither one makes up a dose.'],
  ['The clinician approves it', 'They fix anything flagged and approve. Until then, the patient receives nothing.'],
  ['The patient joins with an invite', 'A link arrives by email, or the care team hands over the invite code. They confirm it is them with a code, pick a language, choose how to be contacted and set a PIN.'],
  ['Tomi keeps in touch', 'An email before each dose, a call at the time they chose, and chat or voice in the app whenever they need it. Numbers and doses stay exactly as written, in Hausa, Yorùbá, Igbo or English.'],
  ['Problems reach a person', 'When a medicine runs out or a bus fare is too much, Tomi shares help the care team has approved. If something sounds urgent, a safety rule alerts the care team straight away, with a short factual summary.']
];

const CHANNELS = [
  [Mail, 'Email reminders', 'A short email before each dose and the evening before a visit. It never names the medicine or the illness, so it is safe in a shared inbox. Text messages are coming.'],
  [Phone, 'Tomi calls', 'At the time the patient chose. Tomi asks for their PIN before saying anything about their care.'],
  [PhoneIncoming, 'Call Tomi', 'From any phone, even without data. Press 1, 2 or 3 if speaking is hard.'],
  [Mic, 'Talk or chat in the app', 'Tap the middle of the day loop and speak, or type. Tomi answers in the patient\'s language.']
];

function Landing() {
  return (
    <>
      <header className="landing-hero">
        <p className="landing-brand"><span className="logo-mark" aria-hidden="true" />CareLoop</p>
        <LoopArt />
        <h1>Care that keeps going after the patient goes home</h1>
        <p className="landing-lede">Most patients leave a hospital, clinic or pharmacy with a plan: medicines, a check-up, a blood test. CareLoop helps them follow it at home. Tomi, an AI assistant, sends reminders and checks in by text, phone call or chat, in Hausa, Yorùbá, Igbo or English. Their care team approves every plan and sees every reply.</p>
        <nav className="landing-doors" aria-label="Sign in">
          <a className="door door-patient" href="/patient/">
            <span className="door-title">I am a patient or family helper</span>
            <span className="door-copy">Sign in with your phone number, or use the invite code your care team sent you.</span>
          </a>
          <a className="door" href="/clinician/">
            <span className="door-title">I work on a care team</span>
            <span className="door-copy">Sign in with your email and a code we send to it.</span>
          </a>
        </nav>
      </header>

      <main className="landing-main">
        <section className="landing-section" aria-labelledby="flow-title">
          <h2 id="flow-title">How it works</h2>
          <ol className="flow">
            {FLOW.map(([title, text]) => (
              <li key={title}><h3>{title}</h3><p>{text}</p></li>
            ))}
          </ol>
        </section>

        <section className="landing-section" aria-labelledby="channels-title">
          <h2 id="channels-title">Four ways Tomi stays in touch</h2>
          <ul className="channels">
            {CHANNELS.map(([Icon, title, text]) => (
              <li key={title} className="channel"><Icon aria-hidden="true" /><h3>{title}</h3><p>{text}</p></li>
            ))}
          </ul>
        </section>

        <p className="landing-note">Tomi is an AI assistant, not a doctor. In an emergency, go to the nearest hospital or call 112.</p>
        <p className="landing-note"><a href="patient/#/privacy">How CareLoop uses your information</a> and <a href="patient/#/terms">terms of use</a>.</p>
      </main>
    </>
  );
}

createRoot(document.getElementById('root')).render(<StrictMode><Landing /></StrictMode>);
