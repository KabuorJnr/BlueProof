/**
 * IndexedDB wrapper: the offline queue and a small read cache.
 *
 * A monitor on the creek edge frequently has no usable signal. If the app
 * refuses to record a submission when offline, they stop using
 * it. Everything is therefore written locally first and synced later.
 *
 * Deliberately hand written rather than pulling in a dependency: the surface we
 * need is small, and every kilobyte matters on a low end handset.
 */

const DB_NAME = 'blueproof';
const DB_VERSION = 1;
const QUEUE = 'queue';
const CACHE = 'cache';

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(QUEUE)) {
        db.createObjectStore(QUEUE, { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(CACHE)) {
        db.createObjectStore(CACHE, { keyPath: 'key' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(store, mode, fn) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const t = db.transaction(store, mode);
        const req = fn(t.objectStore(store));
        t.oncomplete = () => resolve(req && req.result);
        t.onerror = () => reject(t.error);
      })
  );
}

/** Queue a submission captured while offline, or one whose upload failed. */
export function enqueue(item) {
  return tx(QUEUE, 'readwrite', (s) =>
    s.add({ ...item, queuedAt: Date.now(), attempts: 0 })
  );
}

export function listQueue() {
  return tx(QUEUE, 'readonly', (s) => s.getAll()).then((r) => r || []);
}

export function removeFromQueue(id) {
  return tx(QUEUE, 'readwrite', (s) => s.delete(id));
}

export function markAttempt(item) {
  return tx(QUEUE, 'readwrite', (s) =>
    s.put({ ...item, attempts: (item.attempts || 0) + 1, lastTried: Date.now() })
  );
}

/** Cache the last good read so the wallet and history are not blank offline. */
export function cachePut(key, value) {
  return tx(CACHE, 'readwrite', (s) => s.put({ key, value, at: Date.now() }));
}

export function cacheGet(key) {
  return tx(CACHE, 'readonly', (s) => s.get(key)).then((r) => (r ? r.value : null));
}
