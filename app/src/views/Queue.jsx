import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Hourglass, ImageIcon, RefreshCw } from 'lucide-react';
import { listQueue } from '../db.js';
import { flushQueue } from '../sync.js';

export default function Queue({ ctx }) {
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    setItems(await listQueue());
    setLoaded(true);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function retry() {
    ctx.setBusy(true);
    const res = await flushQueue();
    ctx.setBusy(false);
    if (res.signedOut) ctx.notify('Ingia kwanza, kisha foleni itatumwa.', 'err');
    else if (res.offline) ctx.notify('Bado hakuna mtandao.', 'err');
    else ctx.notify(`Zimetumwa ${res.sent}. Zimebaki ${res.failed}.`);
    load();
  }

  return (
    <>
      <h2>Foleni</h2>
      <p className="lede">Ripoti zilizohifadhiwa kwenye simu, zinasubiri mtandao.</p>

      <section className="glass card">
        {!loaded ? (
          <p className="muted">Inapakia…</p>
        ) : !items.length ? (
          <p className="muted">Foleni ni tupu. Kila kitu kimetumwa.</p>
        ) : (
          items.map((i) => {
            const stuck = (i.attempts || 0) >= 5;
            return (
              <div className="item" key={i.id}>
                <div>
                  <div className="title">Kiwanja #{i.payload?.plot_id ?? i.payload?.plotId ?? '—'}</div>
                  <div className="meta" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ImageIcon size={13} aria-hidden="true" />
                    {i.blob ? 'picha imehifadhiwa' : 'hakuna picha'} ·{' '}
                    {new Date(i.queuedAt).toLocaleString()} · majaribio {i.attempts || 0}
                  </div>
                </div>
                <span className="tag" data-tone={stuck ? 'wait' : undefined}>
                  {stuck ? <AlertTriangle size={13} aria-hidden="true" /> : <Hourglass size={13} aria-hidden="true" />}
                  {stuck ? 'imekwama' : 'inasubiri'}
                </span>
              </div>
            );
          })
        )}
      </section>

      <button className="btn" data-variant="ghost" onClick={retry} disabled={ctx.busy}>
        <RefreshCw size={19} aria-hidden="true" />
        Jaribu kutuma sasa
      </button>
    </>
  );
}
