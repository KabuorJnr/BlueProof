/**
 * BlueProof backend client.
 *
 * Base URL resolves: Settings override, then VITE_API_BASE at build time, then
 * localhost for development. On a phone, "localhost" means the phone.
 *
 * The session token lives in localStorage so a monitor signs in once per shift
 * rather than once per plot. It is a bearer token, never a cookie, so it is
 * sent only where this code sends it.
 */

const LS_KEY = 'blueproof.apiBase';
const TOKEN_KEY = 'blueproof.session';
const DEFAULT_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export function getApiBase() {
  try {
    return localStorage.getItem(LS_KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}

export function setApiBase(url) {
  try {
    localStorage.setItem(LS_KEY, url.replace(/\/+$/, ''));
  } catch {
    /* private mode: fall back to the default for this session */
  }
}

let memorySession = null;

export function getSession() {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? JSON.parse(raw) : memorySession;
  } catch {
    return memorySession;
  }
}

export function setSession(session) {
  memorySession = session;
  try {
    if (session) localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the in-memory copy lasts until the tab closes */
  }
  window.dispatchEvent(new Event('blueproof:session'));
}

export class AuthError extends Error {}

async function request(path, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const session = getSession();
  const headers = { ...(options.headers || {}) };
  if (session?.token) headers.Authorization = `Bearer ${session.token}`;
  try {
    const res = await fetch(getApiBase() + path, { ...options, headers, signal: controller.signal });
    if (res.status === 401) {
      // An expired session, not a failed submission. Sign out so the app asks
      // for the PIN again; queued work stays queued.
      if (session?.token) setSession(null);
      throw new AuthError('Ingia tena.');
    }
    if (!res.ok) {
      let detail = '';
      try {
        const body = await res.json();
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
      } catch {
        detail = await res.text().catch(() => '');
      }
      throw new Error(`${res.status} ${detail}`.trim());
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function json(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function submissionForm({ plotId, species, survival, pos, blob, markerBlob, clientRef }) {
  const fd = new FormData();
  fd.append('plot_id', String(plotId));
  fd.append('client_ref', clientRef);
  if (species) fd.append('reported_species', species);
  if (survival != null && survival !== '') fd.append('reported_survival', String(survival));
  if (pos) {
    fd.append('lat', String(pos.lat));
    fd.append('lon', String(pos.lon));
  }
  if (blob) fd.append('image', blob, 'plot.jpg');
  // Protocol shot 1. The server reads the plot code off it and checks it
  // against the plot, which answers what GPS cannot: is this THIS plot.
  if (markerBlob) fd.append('marker', markerBlob, 'marker.jpg');
  return fd;
}

export function newClientRef() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const api = {
  login: (phone, pin) => request('/auth/login', json('POST', { phone, pin })),
  enrol: (body) => request('/privacy/enrol', json('POST', body)),
  me: () => request('/auth/me'),

  exportMe: (userId) => request(`/privacy/export/${userId}`),
  deleteMe: (userId, phrase) =>
    request('/privacy/delete', json('POST', { user_id: userId, confirm_phrase: phrase })),
  meta: () => request('/'),
  sites: () => request('/sites'),
  plots: (siteId) => request(`/sites/${siteId}/plots`),
  myEvents: () => request('/monitoring/events'),
  impact: () => request('/impact/summary'),
  satellite: (siteId) => request(`/satellite/${siteId}`),
  refreshSatellite: (siteId) =>
    request(`/satellite/refresh/${siteId}`, { method: 'POST' }, 60000),

  /**
   * The evidence path: a monitoring event submitted WITH its photograph and a
   * reference generated on this phone, so a retry can never be paid twice.
   */
  submitPhoto: (args) =>
    request('/monitoring/submit-photo', { method: 'POST', body: submissionForm(args) }, 90000),
};

export async function isOnline() {
  if (!navigator.onLine) return false;
  try {
    await request('/', {}, 5000);
    return true;
  } catch (e) {
    return e instanceof AuthError;
  }
}
