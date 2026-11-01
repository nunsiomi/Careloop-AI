const FOOTER_TEXT = 'This is an AI assistant. If you feel very unwell, go to the nearest hospital now.';

export function SafetyFooter() {
  return <footer className="safety-footer">{FOOTER_TEXT}</footer>;
}

export function LogoMark() {
  return <span className="logo-mark" aria-hidden="true" />;
}

export { default as LoopArt } from '../shared/LoopArt.jsx';
