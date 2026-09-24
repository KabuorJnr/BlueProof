import { useState } from 'react';
import { Link2, LogOut, PlugZap, ShieldCheck } from 'lucide-react';
import { api, getApiBase, setApiBase, setSession } from '../api.js';

export default function Settings({ ctx }) {
  const [url, setUrl] = useState(getApiBase());
  const [result, setResult] = useState('');

  async function saveAndTest() {
    const clean = url.trim();
    if (!clean) return;
    setApiBase(clean);
    setResult('Inajaribu…');
    ctx.setBusy(true);
    try {
      const meta = await api.meta();
      setResult(
        `Imeunganishwa: ${meta.app} · Llama ${meta.llama} · setilaiti ${meta.satellite} · M-Pesa ${meta.mpesa}`
      );
      ctx.notify('Imeunganishwa.');
      ctx.refreshOnline();
    } catch (e) {
      setResult(`Imeshindikana: ${e.message}`);
      ctx.notify('Imeshindikana kuunganisha.', 'err');
    } finally {
      ctx.setBusy(false);
    }
  }

  return (
    <>
      <h2>Mipangilio</h2>
      <p className="lede">Mahali app hii inapotuma taarifa.</p>

      <section className="glass card">
        <label htmlFor="base">Backend URL</label>
        <input
          id="base"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          inputMode="url"
          autoCapitalize="off"
          spellCheck="false"
        />
        <div className="note">
          <Link2 size={17} aria-hidden="true" />
          <span>
            Kwenye simu, <code>localhost</code> ni simu yenyewe. Tumia URL yako
            iliyowekwa mtandaoni, au anwani ya laptop kwenye wifi moja.
          </span>
        </div>
        <button className="btn" onClick={saveAndTest} disabled={ctx.busy}>
          <PlugZap size={19} aria-hidden="true" />
          Hifadhi na jaribu
        </button>
        {result && <p className="muted" style={{ marginBlockStart: 12 }}>{result}</p>}
      </section>

      {ctx.session?.user && (
        <section className="glass card">
          <p className="muted" style={{ marginBlock: 0 }}>
            Umeingia kama {ctx.session.user.name} ({ctx.session.user.public_ref}).
          </p>
          <button
            className="btn"
            data-variant="ghost"
            onClick={() => {
              setSession(null);
              location.hash = '#/login';
            }}
          >
            <LogOut size={19} aria-hidden="true" />
            Toka
          </button>
        </section>
      )}

      {ctx.session && (
      <>
      {/* Reachable from Settings rather than the tab bar. A sixth tab on a
          390px phone costs legibility on the five screens people use daily,
          and this one is used once. It is one tap from a place people already
          go looking for "my account" things. */}
      <section className="glass card">
        <div className="note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>
            Taarifa zako: unachoshikiliwa, kupakua, au kufuta kabisa.
          </span>
        </div>
        <button
          className="btn"
          data-variant="ghost"
          onClick={() => (location.hash = '#/privacy')}
        >
          <ShieldCheck size={19} aria-hidden="true" />
          Taarifa zangu
        </button>
      </section>
      </>
      )}
    </>
  );
}
