import { useEffect, useRef } from 'react';
import { ArrowLeft } from 'lucide-react';
import { LogoMark, SafetyFooter } from './parts.jsx';

/* Privacy notice (Nigeria Data Protection Act 2023) and terms of use, in plain words. Reachable signed in or out:
   #/privacy and #/terms. To be checked by the care facility's data protection officer before launch. */

const PRIVACY = {
  title: 'How CareLoop uses your information',
  updated: '3 November 2026',
  sections: [
    ['Who is responsible', [
      'Your care facility (the hospital, clinic, pharmacy or care home that invited you) decides how your information is used. CareLoop runs this service for them.',
      'Questions about your information go to your care team, who will pass them to the facility\'s data protection officer.'
    ]],
    ['What we keep', [
      'Your name, phone number, email address (if you gave one), language and how you like to read.',
      'The care plan your care team approved: medicines, tests and visits.',
      'What you tell Tomi in chat or on calls, written down as text. We do not keep recordings of your voice.',
      'Which reminders were sent, whether they arrived, and what you reported.',
      'Your PIN, stored so that no one, not even your care team, can read it.'
    ]],
    ['Why we use it', [
      'To remind you about your plan and to tell your care team how you are getting on. You agree to each way we contact you, and you can turn each one off in your account.',
      'To alert your care team quickly if something you say sounds urgent. We may do this even without your consent if your life may be at risk.',
      'We never sell your information or use it for advertising.'
    ]],
    ['Who sees it', [
      'Your care team at your facility, and the family helper you invited (only if you invited one).',
      'Companies that help run the service: for sending emails, for understanding and speaking your language, and for phone calls. Some of them are outside Nigeria. They may only use your information to provide this service, and must keep it safe.',
      'Messages and emails never name your medicine, illness or test, so they are safe if someone else sees your phone or inbox.'
    ]],
    ['How long we keep it', [
      'While your care team is following up with you. After that it is deleted, or kept as part of your health record under your facility\'s rules.'
    ]],
    ['Your rights', [
      'You can ask to see your information, to correct it, or to have it deleted. You can withdraw your consent at any time; this does not affect what happened before.',
      'You can object to how we use your information, or ask for a copy to take elsewhere.',
      'If you are not happy with the answer, you can complain to the Nigeria Data Protection Commission (NDPC), or to the data protection authority where you live.'
    ]]
  ]
};

const TERMS = {
  title: 'Terms of use',
  updated: '3 November 2026',
  sections: [
    ['What CareLoop is', [
      'CareLoop helps you follow the plan your care team gave you when you went home. Tomi is an AI assistant, not a doctor or a nurse.',
      'Tomi only repeats what your care team wrote down. Tomi never gives new medical advice and cannot change your medicines.'
    ]],
    ['It is not an emergency service', [
      'If you feel very unwell, go to the nearest hospital now, or call your local emergency number. Do not wait for a reply in the app.',
      'CareLoop tells your care team when something sounds urgent, but it does not send an ambulance.'
    ]],
    ['Keeping your account safe', [
      'Keep your PIN and sign-in codes to yourself. Your care team will never ask for them.',
      'A family helper sees what you allow, and you can remove them at any time.'
    ]],
    ['Using the service', [
      'Tell Tomi the truth about how you are doing, so your care team can help.',
      'The service may sometimes be unavailable. If you cannot reach Tomi, contact your care team directly.',
      'Your care facility may change these terms. If the change matters to you, we will tell you in the app.'
    ]]
  ]
};

export default function LegalScreen({ doc, go, signedIn }) {
  const content = doc === 'terms' ? TERMS : PRIVACY;
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); }, [doc]);
  const back = () => (window.history.length > 1 ? window.history.back() : go(signedIn ? 'account' : 'welcome'));

  return (
    <main className="patient-page legal-page">
      <div className="legal-bar">
        <button type="button" className="auth-back legal-back" onClick={back}><ArrowLeft aria-hidden="true" size={20} />Back</button>
        <span className="onboard-brand"><LogoMark /><span>CareLoop</span></span>
      </div>
      <article className="legal-card">
        <h1 ref={headingRef} tabIndex={-1} className="onboard-title">{content.title}</h1>
        <p className="hint">Last updated {content.updated}</p>
        {content.sections.map(([heading, paragraphs]) => (
          <section key={heading}>
            <h2 className="legal-heading">{heading}</h2>
            <ul className="legal-list">{paragraphs.map((text) => <li key={text}>{text}</li>)}</ul>
          </section>
        ))}
        <p className="legal-switch">
          {doc === 'terms' ? <a href="#/privacy">How CareLoop uses your information</a> : <a href="#/terms">Terms of use</a>}
        </p>
      </article>
      <SafetyFooter />
    </main>
  );
}

export function LegalLinks() {
  return (
    <p className="legal-links"><a href="#/privacy">How we use your information</a><a href="#/terms">Terms of use</a></p>
  );
}
