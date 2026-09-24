import { useEffect, useState } from 'react';
import { Bug, CloudOff, Coins, Hourglass, Send, UserCheck } from 'lucide-react';
import { api } from '../api.js';
import { cacheGet, cachePut } from '../db.js';

const STATUS = {
  verified: ['imethibitishwa', 'ok'],
  needs_human: ['inakaguliwa', 'wait'],
  rejected: ['haijalipwa', undefined],
  pending: ['inasubiri', 'wait'],
};

/**
 * The monitor's own money and own submissions. Not the project's totals: a
 * wallet that shows what everybody earned tells a person nothing about what
 * they are owed.
 */
export default function Wallet() {
  const [data, setData] = useState(null);
  const [stale, setStale] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [me, events] = await Promise.all([api.me(), api.myEvents()]);
        const fresh = { me, events: events.slice(0, 30) };
        if (!alive) return;
        setData(fresh);
        await cachePut('wallet', fresh);
      } catch {
        const cached = await cacheGet('wallet');
        if (!alive) return;
        setData(cached);
        setStale(true);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (!loaded) return <p className="muted">Inapakia…</p>;
  if (!data) {
    return (
      <>
        <h2>Pochi yangu</h2>
        <p className="lede">Hakuna taarifa bado. Unganisha mtandao mara moja.</p>
      </>
    );
  }

  const { me, events } = data;
  const awaiting = events.filter((e) => e.status === 'needs_human').length;
  const tiles = [
    [Coins, Math.round(me.earned_ksh || 0), 'KSh umelipwa'],
    [Hourglass, Math.round(me.pending_ksh || 0), 'KSh zinatumwa'],
    [Send, events.length, 'ripoti ulizotuma'],
    [UserCheck, awaiting, 'zinakaguliwa na mtu'],
  ];

  return (
    <>
      <h2>Pochi yangu</h2>
      <p className="lede">{me.public_ref} · kazi yako na malipo yako.</p>

      {stale && (
        <div className="note">
          <CloudOff size={17} aria-hidden="true" />
          <span>Hakuna mtandao. Unaona taarifa za mwisho.</span>
        </div>
      )}
      {!me.active && (
        <div className="note">
          <UserCheck size={17} aria-hidden="true" />
          <span>Akaunti yako inasubiri kuthibitishwa na kiongozi wa CFA. Ripoti zako zinahifadhiwa; malipo yataanza ukithibitishwa.</span>
        </div>
      )}

      <div className="stats">
        {tiles.map(([Icon, value, label]) => (
          <div className="glass stat" key={label}>
            <Icon className="ico" size={19} aria-hidden="true" />
            <b>{value}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <section className="glass card" style={{ marginBlockStart: 14 }}>
        {!events.length ? (
          <p className="muted">Bado hujatuma ripoti.</p>
        ) : (
          events.map((e) => {
            const [label, tone] = STATUS[e.status] || [e.status];
            return (
              <div className="item" key={e.id}>
                <div>
                  <div className="title">Kiwanja #{e.plot_id}</div>
                  <div className="meta">{new Date(e.created_at).toLocaleString()}</div>
                </div>
                <span className="tag" data-tone={tone}>{label}</span>
              </div>
            );
          })
        )}
      </section>

      <section className="glass card">
        <div className="note">
          <Bug size={17} aria-hidden="true" />
          <span>
            Unalipwa kwa ripoti iliyothibitishwa, si kwa mche ulioishi. Ripoti
            mche uliokufa kwa uaminifu; nayo ni kazi inayolipwa.
          </span>
        </div>
      </section>
    </>
  );
}
