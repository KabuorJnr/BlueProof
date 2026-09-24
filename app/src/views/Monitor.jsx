import { useEffect, useRef, useState } from 'react';
import { Camera, CheckCircle2, MapPin, Send, Sun, Waves } from 'lucide-react';
import { api, isOnline, newClientRef } from '../api.js';
import { compress, getPosition } from '../components/camera.js';
import { enqueue } from '../db.js';

/**
 * The five shot protocol, from docs/field-photo-protocol.md.
 *
 * The published evidence says field performance is dominated by image
 * legibility rather than by the difficulty of telling species apart. Legibility
 * is something a protocol can fix, so the app guides the capture rather than
 * simply accepting whatever arrives. The close shot is the one submitted as
 * evidence, because it is the frame the species assessment depends on.
 */
const SHOTS = [
  { key: 'marker', name: 'Alama ya kiwanja', hint: 'Piga picha ya alama ili msimbo usomeke.' },
  { key: 'wide', name: 'Picha pana', hint: 'Simama mbali, kiwanja chote kionekane.' },
  { key: 'close', name: 'Picha ya karibu', hint: 'Mche mmoja ujaze fremu. Hii ndiyo inayotumika kuthibitisha.', evidence: true },
  { key: 'leaf', name: 'Majani', hint: 'Majani karibu na wazi. Geuza jani moja likiwezekana.' },
  { key: 'problem', name: 'Tatizo', hint: 'Ukataji, wadudu, taka. Hakuna tatizo? Piga mche bora zaidi.' },
];

export default function Monitor({ ctx }) {
  const [plot] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('blueproof.plot') || 'null');
    } catch {
      return null;
    }
  });
  const [step, setStep] = useState(0);
  const [shots, setShots] = useState({});
  const [survival, setSurvival] = useState('');
  const fileRef = useRef(null);
  const positionRef = useRef(null);

  useEffect(() => {
    // Requested up front so a fix is usually ready by submission. Never blocks.
    // A fix under mangrove canopy can take a while; the server escalates a
    // submission with no fix to a person, so it is worth waiting for.
    positionRef.current = getPosition(20000).catch(() => null);
  }, []);

  if (!plot) {
    return (
      <>
        <h2>Hakuna kiwanja</h2>
        <p className="lede">Chagua kiwanja kwanza.</p>
        <button className="btn" onClick={() => (location.hash = '#/plots')}>
          Rudi kwenye viwanja
        </button>
      </>
    );
  }

  const current = SHOTS[step];
  const captured = Object.keys(shots).length;
  const hasEvidence = Boolean(shots.close);

  async function onPick(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const blob = await compress(file);
    setShots((s) => ({ ...s, [current.key]: { blob, url: URL.createObjectURL(file) } }));
    if (step < SHOTS.length - 1) setStep(step + 1);
  }

  async function submit() {
    if (!hasEvidence) {
      ctx.notify('Picha ya karibu inahitajika kwa uthibitisho.', 'err');
      return;
    }
    ctx.setBusy(true);
    const blob = shots.close.blob;
    const markerBlob = shots.marker?.blob || null;
    let pos = await Promise.race([
      positionRef.current,
      new Promise((r) => setTimeout(() => r(null), 10000)),
    ]);
    if (!pos) {
      // One more short, fresh attempt before giving up.
      pos = await getPosition(5000).catch(() => null);
    }
    // Generated once, at capture. Every retry of this submission, online or
    // from the offline queue, carries the same reference.
    const args = {
      plotId: plot.id,
      species: plot.species,
      survival,
      pos,
      clientRef: newClientRef(),
    };
    try {
      if (await isOnline()) {
        const res = await api.submitPhoto({ ...args, blob, markerBlob });
        sessionStorage.setItem('blueproof.verdict', JSON.stringify({ ...res, plot }));
        location.hash = '#/verdict';
      } else {
        // The photograph is queued with the submission, so the eventual
        // verification still runs against the real image.
        await enqueue({ blob, markerBlob, payload: { ...args, plot_id: plot.id } });
        ctx.notify('Hakuna mtandao. Imehifadhiwa na picha yake.');
        location.hash = '#/queue';
      }
    } catch (err) {
      // Anything but a refusal from the server is worth keeping for later:
      // the same reference means a retry can never be paid twice.
      if (/^4\d\d/.test(err.message)) {
        ctx.notify(`Imekataliwa: ${err.message.replace(/^\d+\s*/, '')}`, 'err');
      } else {
        await enqueue({ blob, markerBlob, payload: { ...args, plot_id: plot.id } });
        ctx.notify('Imeshindikana kutuma. Imehifadhiwa kwenye foleni.', 'err');
        location.hash = '#/queue';
      }
    } finally {
      ctx.setBusy(false);
    }
  }

  return (
    <>
      <h2>{plot.code}</h2>
      <p className="lede">
        <i>{plot.species}</i> · piga picha tano kwa mpangilio.
      </p>

      {/* Decorative. aria-label on a plain div is not exposed by most assistive
          technology anyway, and the step is already stated in words below, so
          hiding the dots is honest rather than duplicating the announcement. */}
      <div className="steps" aria-hidden="true">
        {SHOTS.map((s, i) => (
          <i
            key={s.key}
            className="step"
            data-state={shots[s.key] ? 'done' : i === step ? 'now' : undefined}
          />
        ))}
      </div>

      <section className="glass card">
        {/* Live, because the step advances on its own after a photo is taken.
            A sighted monitor sees the dots move; without this nobody else does. */}
        <p className="shotname" role="status">
          {step + 1}/{SHOTS.length} · {current.name}
        </p>
        <p className="muted" style={{ marginBlock: '6px 0' }}>{current.hint}</p>

        {shots[current.key] ? (
          <img className="media" style={{ marginBlockStart: 12 }} src={shots[current.key].url} alt={current.name} />
        ) : null}

        <button className="btn" onClick={() => fileRef.current?.click()} disabled={ctx.busy}>
          <Camera size={19} aria-hidden="true" />
          {shots[current.key] ? 'Piga tena' : 'Piga picha'}
        </button>

        <div style={{ display: 'flex', gap: 10, marginBlockStart: 10 }}>
          <button
            className="btn"
            data-variant="ghost"
            onClick={() => setStep(Math.max(0, step - 1))}
            disabled={step === 0 || ctx.busy}
          >
            Nyuma
          </button>
          <button
            className="btn"
            data-variant="ghost"
            onClick={() => setStep(Math.min(SHOTS.length - 1, step + 1))}
            disabled={step === SHOTS.length - 1 || ctx.busy}
          >
            Mbele
          </button>
        </div>

        {/* Opened by the visible capture buttons, so it is removed from the tab
            order: a focusable control the user cannot see is a keyboard trap.
            It still needs an accessible name, because assistive technology can
            reach it even when tabbing cannot. */}
        <input
          ref={fileRef}
          className="sr-only"
          type="file"
          accept="image/*"
          capture="environment"
          tabIndex={-1}
          aria-label="Chagua picha ya kiwanja kutoka kwenye simu yako"
          onChange={onPick}
        />

        {captured > 0 && (
          <div className="thumbs">
            {SHOTS.filter((s) => shots[s.key]).map((s) => (
              <img key={s.key} src={shots[s.key].url} alt={s.name} />
            ))}
          </div>
        )}
      </section>

      <section className="glass card">
        <div className="note">
          <Sun size={17} aria-hidden="true" />
          <span>Piga asubuhi au jioni, si adhuhuri. Jua liwe nyuma yako.</span>
        </div>
        <div className="note">
          <Waves size={17} aria-hidden="true" />
          <span>Maji yakiwa yamepwa, mizizi na ardhi vionekane.</span>
        </div>
        <div className="note">
          <MapPin size={17} aria-hidden="true" />
          <span>Washa GPS na usimame kwenye kiwanja. Picha bila GPS hukaguliwa na mtu kabla ya malipo.</span>
        </div>

        <label htmlFor="survival">Miche hai uliyohesabu (hiari)</label>
        <input
          id="survival"
          inputMode="numeric"
          value={survival}
          onChange={(e) => setSurvival(e.target.value.replace(/\D/g, ''))}
          placeholder="mfano 38"
        />

        <button className="btn" onClick={submit} disabled={ctx.busy || !hasEvidence}>
          {hasEvidence ? <Send size={19} aria-hidden="true" /> : <CheckCircle2 size={19} aria-hidden="true" />}
          {hasEvidence ? 'Wasilisha kwa uthibitisho' : 'Picha ya karibu inahitajika'}
        </button>
      </section>
    </>
  );
}
