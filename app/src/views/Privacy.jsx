import { useState } from 'react';
import { Download, FileText, ShieldCheck, Smartphone, Trash2 } from 'lucide-react';
import { api, setSession } from '../api.js';

/**
 * The screen where a monitor's rights over their own record are exercised.
 *
 * It is a screen rather than an email address on purpose. A right that requires
 * writing to a founder who may be in a lecture is a right on paper, and the
 * people this app is for are the least likely to chase it. Export and deletion
 * are one tap and one typed word respectively, in Swahili, on the same phone
 * they already have open.
 */
export default function Privacy({ ctx }) {
  const [phrase, setPhrase] = useState('');
  const [result, setResult] = useState(null);

  async function exportMe() {
    ctx.setBusy(true);
    try {
      const data = await api.exportMe(ctx.session.user.id);
      // Handed over as a file rather than shown on screen. It is theirs to
      // keep, and a screenful of JSON is not something anybody can keep.
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = 'taarifa-zangu-blueproof.json';
      a.click();
      URL.revokeObjectURL(url);
      ctx.notify('Taarifa zako zimepakuliwa.');
    } catch (e) {
      ctx.notify(`Imeshindikana: ${e.message}`, 'err');
    } finally {
      ctx.setBusy(false);
    }
  }

  async function deleteMe() {
    ctx.setBusy(true);
    try {
      const res = await api.deleteMe(ctx.session.user.id, phrase);
      setResult(res);
      setPhrase('');
      ctx.notify('Jina na namba yako zimefutwa.');
      // The account no longer exists; the session that pointed at it goes too.
      setTimeout(() => setSession(null), 6000);
    } catch (e) {
      ctx.notify(`Imeshindikana: ${e.message}`, 'err');
    } finally {
      ctx.setBusy(false);
    }
  }

  return (
    <>
      <h2>Taarifa zangu</h2>
      <p className="lede">Tunashikilia nini kukuhusu, na unachoweza kufanya nacho.</p>

      <section className="glass card">
        <div className="note">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>
            Tunashikilia jina lako, namba yako ya simu, na kumbukumbu kwamba
            ulikubali. Hatushikilii umri wako, namba yako ya kitambulisho, wala
            mahali ulipo wakati mwingine wowote.
          </span>
        </div>
        <div className="note">
          <Smartphone size={17} aria-hidden="true" />
          <span>
            Kumbukumbu ya umma inatumia namba ya siri kama BP-M-0007, si jina
            lako. Sisi tu ndio tunaweza kuiunganisha na wewe.
          </span>
        </div>
      </section>

      <section className="glass card">
        <h3 style={{ fontSize: '1.05rem', marginBlock: '0 8px' }}>Pakua taarifa zako</h3>
        <p className="muted" style={{ marginBlock: 0 }}>
          Kila kitu tunachoshikilia, pamoja na ripoti zisizopita ukaguzi.
        </p>
        <button className="btn" onClick={exportMe} disabled={ctx.busy}>
          <Download size={19} aria-hidden="true" />
          Pakua
        </button>
      </section>

      <section className="glass card">
        <h3 style={{ fontSize: '1.05rem', marginBlock: '0 8px' }}>Futa taarifa zako</h3>
        <p className="muted" style={{ marginBlock: 0 }}>
          Jina lako, namba yako, taarifa za mlezi, na picha zako zitafutwa kabisa. Kumbukumbu
          za kazi zitabaki chini ya namba ya siri, hazitakuelekeza tena kwako.
          Kumbukumbu za malipo hubaki miaka saba kwa sheria za fedha, hatuwezi
          kuzifuta.
        </p>
        <label htmlFor="futa" style={{ marginBlockStart: 12 }}>
          Andika FUTA kuthibitisha
        </label>
        <input
          id="futa"
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          autoCapitalize="characters"
          spellCheck="false"
        />
        <button
          className="btn"
          data-variant="ghost"
          onClick={deleteMe}
          disabled={ctx.busy || phrase.trim().toUpperCase() !== 'FUTA'}
        >
          <Trash2 size={19} aria-hidden="true" />
          Futa taarifa zangu
        </button>

        {result && (
          <div className="note" style={{ marginBlockStart: 12 }}>
            <ShieldCheck size={17} aria-hidden="true" />
            <span>
              {result.message}
              {result.kept_and_why?.length > 0 && (
                <>
                  {' '}
                  Kilichobaki: {result.kept_and_why.map((k) => k.what).join('; ')}.
                </>
              )}
            </span>
          </div>
        )}
      </section>

      <section className="glass card">
        <div className="note">
          <FileText size={17} aria-hidden="true" />
          <span>
            Soma kikamilifu:{' '}
            <a href="./legal/privacy-policy.md">taarifa ya faragha</a>,{' '}
            <a href="./legal/terms-of-service.md">masharti ya matumizi</a>,{' '}
            <a href="./legal/cookies-and-storage.md">kuki na hifadhi</a>.
          </span>
        </div>
      </section>
    </>
  );
}
