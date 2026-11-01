// Presenter mode: shows sign-in details and live-demo tools to whoever is presenting, and hides them from everyone else.
// Turn it on with ?presenter=1 on any page and off with ?presenter=0. It is remembered on this browser.
// It only ever works on in-browser data (USE_MOCKS); against the real backend it is always off.
import { USE_MOCKS } from './api.js';

const KEY = 'careloop-presenter';
const flag = new URLSearchParams(window.location.search).get('presenter');
if (flag === '1') window.localStorage.setItem(KEY, 'on');
if (flag === '0') window.localStorage.removeItem(KEY);

export const PRESENTER = USE_MOCKS && window.localStorage.getItem(KEY) === 'on';
