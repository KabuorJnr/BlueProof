import { useEffect, useState } from 'react';
import { AlertTriangle, CloudOff, RefreshCw, Satellite } from 'lucide-react';
import { api } from '../api.js';
import { cacheGet, cachePut } from '../db.js';

export default function Site({ ctx }) {
  const [site, setSite] = useState(null);
  const [series, setSeries] = useState([]);
  const [stale, setStale] = useState(false);
  const [loaded, setLoaded] = useState(false);

  async function load() {
    try {
      const sites = await api.sites();
      const first = sites[0];
      const obs = await api.satellite(first.id);
      setSite(first);
      setSeries(obs);
      await cachePut('satellite', { site: first, obs });
      setStale(false);
    } catch {
      const cached = await cacheGet('satellite');
      setSite(cached?.site || null);
      setSeries(cached?.obs || []);
      setStale(true);
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function refresh() {
    ctx.setBusy(true);
    try {
      const res = await api.refreshSatellite(site.id);
      ctx.notify(`Picha ${res.observations}, zinazotumika ${res.usable_after_cloud}, onyo ${res.alerts}.`);
      await load();
    } catch {
      ctx.notify('Imeshindikana kupata picha za setilaiti.', 'err');
    } finally {
      ctx.setBusy(false);
    }
  }

  if (!loaded) return <p className="muted">Inapakia…</p>;

  const usable = series.filter((o) => o.cloud_fraction <= 0.4);
  const alerts = usable.filter((o) => o.alert);
  const latest = usable[usable.length - 1];

  return (
    <>
      <h2>Eneo</h2>
      <p className="lede">
        {site ? `${site.name}, ${site.county} · ${site.area_ha} hekta` : 'Hakuna taarifa za eneo.'}
      </p>

      {stale && (
        <div className="note">
          <CloudOff size={17} aria-hidden="true" />
          <span>Hakuna mtandao. Unaona taarifa za mwisho.</span>
        </div>
      )}

      <div className="stats">
        <div className="glass stat">
          <Satellite className="ico" size={19} aria-hidden="true" />
          <b>{series.length}</b>
          <span>picha za setilaiti</span>
        </div>
        <div className="glass stat">
          <CloudOff className="ico" size={19} aria-hidden="true" />
          <b>{series.length - usable.length}</b>
          <span>zimezuiwa na mawingu</span>
        </div>
        <div className="glass stat">
          <AlertTriangle className="ico" size={19} aria-hidden="true" />
          <b>{alerts.length}</b>
          <span>onyo la upotevu</span>
        </div>
        <div className="glass stat">
          <Satellite className="ico" size={19} aria-hidden="true" />
          <b>{latest ? latest.change_vs_baseline.toFixed(2) : '—'}</b>
          <span>mabadiliko ya NDVI</span>
        </div>
      </div>

      <section className="glass card" style={{ marginBlockStart: 14 }}>
        <p className="muted">
          Setilaiti huona mabadiliko ya kiwango cha hekta, si mche mmoja. Ukweli wa
          kiwanja unatoka kwenye picha zako za shambani.
        </p>
        <button className="btn" data-variant="ghost" onClick={refresh} disabled={ctx.busy || !site}>
          <RefreshCw size={19} aria-hidden="true" />
          Sasisha picha za setilaiti
        </button>
      </section>
    </>
  );
}
