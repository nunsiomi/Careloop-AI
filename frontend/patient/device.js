// "Remember this phone": lets a patient come back with their PIN instead of a new code.
// Stores the phone number and first name only, never health details. "Not you?" clears it.
const DEVICE_KEY = 'careloop-device';

export function rememberedDevice() {
  try { return JSON.parse(window.localStorage.getItem(DEVICE_KEY) || 'null'); } catch { return null; }
}

export function rememberDevice(session) {
  const masked = `${session.phone_e164.slice(0, 4)} ••• ••• ${session.phone_e164.slice(-4)}`;
  window.localStorage.setItem(DEVICE_KEY, JSON.stringify({ phone_e164: session.phone_e164, masked_phone: masked, first_name: session.user_name.split(' ')[0] }));
}

export function forgetDevice() {
  window.localStorage.removeItem(DEVICE_KEY);
}
