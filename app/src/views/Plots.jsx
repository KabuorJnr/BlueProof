import { useEffect, useState } from 'react';
import { ChevronRight, CloudOff, MapPin, Sprout } from 'lucide-react';
import { api } from '../api.js';
import { cacheGet, cachePut } from '../db.js';

export default function Plots() {
  const [site, setSite] = useState(null);
  const [plots, setPlots] = useState(null);
  const [stale, setStale] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const sites = await api.sites();
        const first = sites[0];
        const rows = await api.plots(first.id);
        if (!alive) return;
        setSite(first);
        setPlots(rows);
        await cachePut('site', first);
        await cachePut('plots', rows);
      } catch {
        const [s, p] = await Promise.all([cacheGet('site'), cacheGet('plots')]);
        if (!alive) return;
        setSite(s);
        setPlots(p);
        setStale(true);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  function open(plot) {
    sessionStorage.setItem('blueproof.plot', JSON.stringify(plot));
    location.hash = '#/monitor';
  }

  if (!loaded) return <p className="muted">Inapakia…</p>;

  return (
    <>
      <h2>Viwanja vya kufuatilia</h2>
      <p className="lede">
        {site ? `${site.name}, ${site.county} · ${site.area_ha} hekta` : 'Chagua kiwanja kuanza.'}
      </p>

      {stale && (
        <div className="note">
          <CloudOff size={17} aria-hidden="true" />
          <span>Hakuna mtandao. Unaona orodha ya mwisho iliyohifadhiwa.</span>
        </div>
      )}

      <section className="glass card">
        {!plots?.length ? (
          <p className="muted">Hakuna viwanja bado.</p>
        ) : (
          plots.map((p) => (
            <button
              key={p.id}
              className="item"
              onClick={() => open(p)}
              style={{ inlineSize: '100%', background: 'none', border: 0, textAlign: 'start', cursor: 'pointer' }}
            >
              <div>
                <div className="title">{p.code}</div>
                <div className="meta" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Sprout size={13} aria-hidden="true" />
                  <i style={{ fontStyle: 'italic' }}>{p.species}</i> · {p.seedlings_planted} miche
                </div>
                <div className="meta" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MapPin size={13} aria-hidden="true" />
                  {p.lat.toFixed(4)}, {p.lon.toFixed(4)}
                </div>
              </div>
              <ChevronRight size={20} color="var(--accent)" aria-hidden="true" />
            </button>
          ))
        )}
      </section>
    </>
  );
}
