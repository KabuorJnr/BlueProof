/**
 * Flush queued monitoring submissions when connectivity returns.
 *
 * Queued items carry their photograph as a Blob in IndexedDB, so an offline
 * submission is still verified against the real image when it eventually
 * reaches the backend. Each carries the reference it was given when it was
 * captured, so if a response is lost and the item is sent again, the server
 * returns the original outcome instead of recording (and paying) a second one.
 */
import { AuthError, api, getSession, isOnline } from './api.js';
import { listQueue, markAttempt, removeFromQueue } from './db.js';

const MAX_ATTEMPTS = 5;
let running = false;

export async function flushQueue() {
  if (running) return { skipped: true };
  if (!getSession()?.token) return { signedOut: true, sent: 0, failed: 0 };
  running = true;
  let sent = 0;
  let failed = 0;
  try {
    if (!(await isOnline())) return { offline: true, sent, failed };

    for (const item of await listQueue()) {
      if ((item.attempts || 0) >= MAX_ATTEMPTS) {
        failed += 1;
        continue;
      }
      try {
        // Items queued by an older build have no reference; derive a stable one.
        const clientRef = item.payload.clientRef || `legacy-${item.id}-${item.queuedAt}`;
        await api.submitPhoto({ ...item.payload, clientRef, blob: item.blob, markerBlob: item.markerBlob });
        await removeFromQueue(item.id);
        sent += 1;
      } catch (e) {
        // A signed-out phone is not a failed submission. Stop, keep everything.
        if (e instanceof AuthError) return { signedOut: true, sent, failed };
        await markAttempt(item);
        failed += 1;
      }
    }
    return { sent, failed };
  } finally {
    running = false;
  }
}

export function startAutoSync() {
  const attempt = () => flushQueue().catch(() => {});
  window.addEventListener('online', attempt);
  window.addEventListener('focus', attempt);
  window.addEventListener('blueproof:session', attempt);
  attempt();
}
