// "Remember this phone": lets a patient come back with their PIN instead of a new code.
// Stores the account's email address and first name only, never health details. "Not you?" clears it.
import { maskEmail } from '../shared/format.js';

const DEVICE_KEY = 'careloop-device';

export function rememberedDevice() {
  try {
    const device = JSON.parse(window.localStorage.getItem(DEVICE_KEY) || 'null');
    return device?.email ? device : null; // phones remembered by number (before email sign-in) sign in with a code once
  } catch { return null; }
}

export function rememberDevice(session) {
  if (!session.email) return;
  window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ email: session.email, masked_email: maskEmail(session.email), first_name: session.user_name.split(' ')[0] }));
}

export function forgetDevice() {
  window.localStorage.removeItem(DEVICE_KEY);
}
