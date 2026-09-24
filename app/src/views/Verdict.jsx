import { useState } from 'react';
import { AlertTriangle, Bug, CheckCircle2, Coins, Axe, Sprout, UserCheck } from 'lucide-react';

const HEALTH_SW = { healthy: 'nzuri', stressed: 'imedhoofika', dead: 'imekufa', unclear: 'haijabainika' };

export default function Verdict() {
  const [data] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('blueproof.verdict') || 'null');
    } catch {
      return null;
    }
  });

  if (!data) {
    return (
      <>
        <h2>Hakuna matokeo</h2>
        <p className="lede">Wasilisha kiwanja kwanza.</p>
        <button className="btn" onClick={() => (location.hash = '#/plots')}>Rudi kwenye viwanja</button>
      </>
    );
  }

  const e = data.event;
  const paid = data.payment && data.payment.status === 'success';
  const failed = data.payment && data.payment.status === 'failed';
  const needsHuman = e.status === 'needs_human';
  const rejected = e.status === 'rejected';
  const pct = Math.round((e.confidence || 0) * 100);
  const reasons = e.review_reasons || [];

  // A species disagreement is corroboration failing, not the monitor being
  // wrong. Say so plainly, because the person standing at the plot deserves
  // to know the machine is being overruled, not them.
  const dispute = e.species_consistent === 'no';

  return (
    <>
      <h2>{needsHuman ? 'Inahitaji ukaguzi' : rejected ? 'Imerekodiwa, haijalipwa' : 'Imethibitishwa'}</h2>
      {data.duplicate && <p className="muted">Hii ilishatumwa awali; haya ni matokeo yale yale.</p>}
      <p className="lede">
        {data.plot?.code} · uthibitisho wa picha uliyopiga.
      </p>

      <section className="glass card">
        <div className="verdictline">
          <Sprout size={17} color="var(--accent)" aria-hidden="true" />
          <span className="k">Aina uliyotaja</span>
          <span className="v" style={{ fontStyle: 'italic' }}>{e.reported_species || '—'}</span>
        </div>
        <div className="verdictline">
          <CheckCircle2 size={17} color="var(--accent)" aria-hidden="true" />
          <span className="k">Picha inakubaliana?</span>
          <span className="v">{{ yes: 'ndiyo', no: 'hapana', unclear: 'haijabainika' }[e.species_consistent] || '—'}</span>
        </div>
        <div className="verdictline">
          <CheckCircle2 size={17} color="var(--accent)" aria-hidden="true" />
          <span className="k">Miche inayoonekana</span>
          <span className="v">{e.seedlings_visible ?? '—'}</span>
        </div>
        <div className="verdictline">
          <CheckCircle2 size={17} color="var(--accent)" aria-hidden="true" />
          <span className="k">Hali</span>
          <span className="v">{HEALTH_SW[e.health] || e.health || '—'}</span>
        </div>
        {e.marker_sha256 && (
          <div className="verdictline">
            <CheckCircle2 size={17} color={e.marker_matches === false ? 'var(--warn)' : 'var(--accent)'} aria-hidden="true" />
            <span className="k">Alama ya kiwanja</span>
            <span className="v">
              {e.marker_code_read
                ? `${e.marker_code_read}${e.marker_matches ? ' ✓' : ' ✗'}`
                : 'haikusomeka'}
            </span>
          </div>
        )}
        {e.previous_event_id && (
          <div className="verdictline">
            <CheckCircle2 size={17} color={e.same_location === 'no' ? 'var(--warn)' : 'var(--accent)'} aria-hidden="true" />
            <span className="k">Ikilinganishwa na ziara iliyopita</span>
            <span className="v">
              {{ yes: 'mahali pale pale', no: 'mahali tofauti', unclear: 'haijabainika' }[e.same_location] || '—'}
              {e.change_vs_previous && e.change_vs_previous !== 'unclear'
                ? ` · ${{ improved: 'imeimarika', unchanged: 'haijabadilika', declined: 'imepungua' }[e.change_vs_previous]}`
                : ''}
            </span>
          </div>
        )}
        {e.evidence_of_cutting && (
          <div className="verdictline">
            <Axe size={17} color="var(--warn)" aria-hidden="true" />
            <span className="k">Onyo</span>
            <span className="v">Dalili za ukataji</span>
          </div>
        )}
        {e.pest_damage && (
          <div className="verdictline">
            <Bug size={17} color="var(--warn)" aria-hidden="true" />
            <span className="k">Onyo</span>
            <span className="v">Uharibifu wa wadudu</span>
          </div>
        )}

        <p className="muted" style={{ marginBlock: '14px 6px' }}>
          Kiwango cha uhakika: {pct}%
          {e.verifier_samples > 1 ? ` (majibu ${e.verifier_samples} ya modeli yalilinganishwa)` : ''}
        </p>
        <div className="meter"><i style={{ inlineSize: `${pct}%` }} /></div>
        {e.reasoning && <p className="muted" style={{ marginBlockStart: 10 }}>{e.reasoning}</p>}

        {/* Who answered. On a screen that tells a person their work has been
            verified and their money released, the identity of the verifier is
            not a technical detail. It is the claim. */}
        <p className="muted" style={{ marginBlockStart: 10, fontSize: '0.78rem' }}>
          Imekaguliwa na:{' '}
          {e.verification_source === 'mock'
            ? 'mfumo wa majaribio (si modeli halisi)'
            : e.verification_source?.startsWith('error')
              ? 'modeli haikupatikana; mtu atakagua'
              : e.verification_source || 'haijulikani'}
        </p>
      </section>

      {reasons.length > 0 && (
        <section className="glass card">
          <p className="muted" style={{ margin: 0 }}>Kwa nini:</p>
          <ul className="reasons">
            {reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </section>
      )}

      {rejected ? (
        <section className="glass card">
          <div className="note">
            <UserCheck size={17} aria-hidden="true" />
            <span>
              Taarifa yako imehifadhiwa na inahesabika, lakini kiwanja hiki
              kimeshalipwa katika kipindi hiki. Onyo lolote la ukataji au wadudu
              bado linafika kwa kikundi.
            </span>
          </div>
          <button className="btn" onClick={() => (location.hash = '#/plots')}>
            Endelea na kiwanja kingine
          </button>
        </section>
      ) : needsHuman ? (
        <section className="glass card">
          {dispute ? (
            <div className="note">
              <UserCheck size={17} aria-hidden="true" />
              <span>
                Ulisema <i>{data.plot?.species}</i>, picha imesomeka kama{' '}
                <i>{e.detected_species}</i>. Hatubadilishi jibu lako: wewe ndiye
                uliyesimama shambani. Mtu atakagua picha. Hakuna malipo bado.
              </span>
            </div>
          ) : (
            <div className="note">
              <UserCheck size={17} aria-hidden="true" />
              <span>
                Mtu atakagua picha yako kwa sababu zilizoonyeshwa hapo juu. Hakuna
                malipo bado. Hii si kosa lako: mfumo umeundwa kukataa badala ya
                kubahatisha.
              </span>
            </div>
          )}
          <button className="btn" data-variant="ghost" onClick={() => (location.hash = '#/plots')}>
            Endelea na kiwanja kingine
          </button>
        </section>
      ) : (
        <section className="glass card">
          <div className="note">
            <Coins size={17} aria-hidden="true" />
            <span>
              {paid
                ? `Umelipwa KSh ${Math.round(data.payment.amount)} kwa M-Pesa. Kumbukumbu imeandikwa.`
                : failed
                  ? 'Malipo yamekwama. Msimamizi atayatuma tena; kazi yako imethibitishwa.'
                  : `KSh ${Math.round(data.payment?.amount || 0)} zinatumwa kwa M-Pesa. Utapata ujumbe kutoka M-Pesa.`}
            </span>
          </div>
          {(e.evidence_of_cutting || e.pest_damage) && (
            <div className="note" style={{ borderColor: 'color-mix(in oklab, var(--warn) 30%, transparent)' }}>
              <AlertTriangle size={17} aria-hidden="true" />
              <span>Onyo lako limerekodiwa na litafikishwa kwa kikundi cha jamii.</span>
            </div>
          )}
          <button className="btn" onClick={() => (location.hash = '#/plots')}>
            Endelea na kiwanja kingine
          </button>
        </section>
      )}
    </>
  );
}
