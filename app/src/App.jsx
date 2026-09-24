import { useCallback, useEffect, useRef, useState } from 'react';
import { Trees, Wifi, WifiOff } from 'lucide-react';
import { api, getSession, isOnline } from './api.js';
import TabBar from './components/TabBar.jsx';
import Toast from './components/Toast.jsx';
import DemoBanner from './components/DemoBanner.jsx';
import Plots from './views/Plots.jsx';
import Monitor from './views/Monitor.jsx';
import Verdict from './views/Verdict.jsx';
import Wallet from './views/Wallet.jsx';
import Site from './views/Site.jsx';
import Queue from './views/Queue.jsx';
import Settings from './views/Settings.jsx';
import Privacy from './views/Privacy.jsx';
import Login from './views/Login.jsx';

const VIEWS = {
  '#/plots': Plots,
  '#/monitor': Monitor,
  '#/verdict': Verdict,
  '#/site': Site,
  '#/wallet': Wallet,
  '#/queue': Queue,
  '#/settings': Settings,
  '#/privacy': Privacy,
  '#/login': Login,
};

const TITLES = {
  '#/plots': 'Viwanja',
  '#/monitor': 'Ufuatiliaji',
  '#/verdict': 'Uamuzi',
  '#/site': 'Eneo',
  '#/wallet': 'Pochi',
  '#/queue': 'Foleni',
  '#/settings': 'Mipangilio',
  '#/privacy': 'Taarifa zangu',
  '#/login': 'Ingia',
};

// Reachable without signing in: the sign in screen itself, and Settings, which
// is where a phone is pointed at the right backend before anyone can sign in.
const PUBLIC = new Set(['#/login', '#/settings']);

function useSession() {
  const [session, set] = useState(getSession);
  useEffect(() => {
    const on = () => set(getSession());
    window.addEventListener('blueproof:session', on);
    return () => window.removeEventListener('blueproof:session', on);
  }, []);
  return session;
}

function useHashRoute() {
  const [hash, setHash] = useState(() => (VIEWS[location.hash] ? location.hash : '#/plots'));
  useEffect(() => {
    const onChange = () => setHash(VIEWS[location.hash] ? location.hash : '#/plots');
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return hash;
}

export default function App() {
  const routed = useHashRoute();
  const session = useSession();
  const hash = session || PUBLIC.has(routed) ? routed : '#/login';
  const View = VIEWS[hash];
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(true);

  const notify = useCallback((message, tone) => setToast({ message, tone, key: Date.now() }), []);
  const checkOnline = useCallback(async () => setOnline(await isOnline()), []);

  useEffect(() => {
    checkOnline();
    window.addEventListener('online', checkOnline);
    window.addEventListener('offline', checkOnline);
    return () => {
      window.removeEventListener('online', checkOnline);
      window.removeEventListener('offline', checkOnline);
    };
  }, [checkOnline]);

  // Asked once, on arrival. If the backend is unreachable the banner simply
  // does not render: an unproven claim is worth removing, an unanswerable
  // question is not worth alarming anyone about.
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.meta().then(
      (m) => { if (!cancelled) setMeta(m); },
      () => {},
    );
    return () => { cancelled = true; };
  }, []);

  const mainRef = useRef(null);
  const firstRender = useRef(true);

  // A hash route swap replaces the whole view but leaves focus on the tab that
  // was pressed, so a keyboard or screen reader user is told nothing changed.
  // Moving focus to the new view is what a real page load would have done.
  // The first render is skipped: stealing focus on arrival is its own defect.
  useEffect(() => {
    document.title = `${TITLES[hash] ?? ''} \u00b7 BlueProof`;
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus();
  }, [hash]);

  const ctx = { notify, busy, setBusy, online, refreshOnline: checkOnline, session };

  return (
    <div className="app">
      {/* href stays for semantics, but the default must be prevented: this is a
          hash routed app, so letting the browser set location.hash to "#main"
          would unmatch the route table and throw the user back to the default
          view. The link moves focus itself instead. */}
      <a
        className="skip"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Rukia maudhui makuu
      </a>
      <header className="topbar">
        <div className="brand">
          <Trees size={22} strokeWidth={2.2} color="var(--accent)" aria-hidden="true" />
          <strong>BLUEPROOF</strong>
        </div>
        {session?.user && <span className="whoami">{session.user.public_ref}</span>}
        <span className="chip" data-tone={online ? 'on' : 'off'}>
          {online ? <Wifi size={13} aria-hidden="true" /> : <WifiOff size={13} aria-hidden="true" />}
          {online ? 'Mtandao upo' : 'Hakuna mtandao'}
        </span>
      </header>

      <DemoBanner meta={meta} />

      <main id="main" ref={mainRef} tabIndex={-1}>
        <View ctx={ctx} />
      </main>

      {session ? (
        <TabBar active={hash} />
      ) : hash === '#/login' ? (
        <p style={{ textAlign: 'center' }}>
          <a href="#/settings">Mipangilio ya seva</a>
        </p>
      ) : (
        <p style={{ textAlign: 'center' }}>
          <a href="#/login">Rudi kuingia</a>
        </p>
      )}
      {toast && (
        <Toast key={toast.key} message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />
      )}
    </div>
  );
}
