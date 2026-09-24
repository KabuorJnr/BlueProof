import { useState } from 'react';
import { KeyRound, LogIn, ShieldCheck, UserPlus } from 'lucide-react';
import { api, setSession } from '../api.js';

/**
 * Sign in with phone and PIN, or enrol.
 *
 * Enrolment is where consent is taken, so the consent wording is on this
 * screen in Swahili and the box is not pre-ticked. A self-enrolled account can
 * sign in and submit straight away, but is not paid until a CFA lead confirms
 * the person is a member of the group; the app says so rather than letting the
 * first unpaid submission explain it.
 */
export default function Login({ ctx }) {
  const [mode, setMode] = useState('login');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [name, setName] = useState('');
  const [cfa, setCfa] = useState('');
  const [consent, setConsent] = useState(false);
  const [minor, setMinor] = useState(false);
  const [gName, setGName] = useState('');
  const [gPhone, setGPhone] = useState('');
  const [error, setError] = useState('');

  const normPhone = (v) => {
    const d = v.replace(/\D/g, '');
    if (d.startsWith('0') && d.length === 10) return `254${d.slice(1)}`;
    return d;
  };

  async function signIn(e) {
    e.preventDefault();
    setError('');
    ctx.setBusy(true);
    try {
      const res = await api.login(normPhone(phone), pin);
      setSession({ token: res.token, user: res.user });
      location.hash = '#/plots';
    } catch (err) {
      setError(err.message.replace(/^\d+\s*/, '') || 'Imeshindikana.');
    } finally {
      ctx.setBusy(false);
    }
  }

  async function enrol(e) {
    e.preventDefault();
    setError('');
    ctx.setBusy(true);
    try {
      const res = await api.enrol({
        name: name.trim(),
        phone: normPhone(phone),
        pin,
        cfa: cfa.trim() || null,
        consent_given: consent,
        is_minor: minor,
        guardian_name: minor ? gName.trim() : null,
        guardian_phone: minor ? normPhone(gPhone) : null,
      });
      setSession({
        token: res.token,
        user: { id: res.user_id, name: name.trim(), public_ref: res.public_ref, role: 'monitor', active: res.active },
      });
      ctx.notify(res.active ? 'Umesajiliwa.' : 'Umesajiliwa. Kiongozi wa CFA atakuthibitisha.');
      location.hash = '#/plots';
    } catch (err) {
      setError(err.message.replace(/^\d+\s*/, '') || 'Imeshindikana.');
    } finally {
      ctx.setBusy(false);
    }
  }

  const pinInput = (
    <>
      <label htmlFor="pin">PIN (tarakimu 4 hadi 8)</label>
      <input
        id="pin"
        type="password"
        inputMode="numeric"
        autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
        required
        minLength={4}
      />
    </>
  );

  const phoneInput = (
    <>
      <label htmlFor="phone">Namba ya M-Pesa</label>
      <input
        id="phone"
        inputMode="tel"
        autoComplete="tel"
        placeholder="07XX XXX XXX"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        required
      />
    </>
  );

  return (
    <>
      <h2>{mode === 'login' ? 'Ingia' : 'Jisajili'}</h2>
      <p className="lede">
        {mode === 'login'
          ? 'Ingia kwa namba yako na PIN.'
          : 'Jisajili kama mfuatiliaji wa mikoko.'}
      </p>

      {mode === 'login' ? (
        <form className="glass card" onSubmit={signIn}>
          {phoneInput}
          {pinInput}
          {error && <p className="formerror" role="alert">{error}</p>}
          <button className="btn" type="submit" disabled={ctx.busy}>
            <LogIn size={19} aria-hidden="true" />
            Ingia
          </button>
          <button className="btn" data-variant="ghost" type="button" onClick={() => { setMode('enrol'); setError(''); }}>
            <UserPlus size={19} aria-hidden="true" />
            Sijasajiliwa bado
          </button>
          <p className="muted" style={{ marginBlockStart: 12 }}>
            <KeyRound size={14} aria-hidden="true" /> Umesahau PIN? Kiongozi wa CFA anaweza kuibadilisha.
          </p>
        </form>
      ) : (
        <form className="glass card" onSubmit={enrol}>
          <label htmlFor="name">Jina kamili</label>
          <input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
          {phoneInput}
          {pinInput}
          <label htmlFor="cfa">Kikundi cha CFA (hiari)</label>
          <input id="cfa" value={cfa} onChange={(e) => setCfa(e.target.value)} placeholder="mfano Tudor CFA" />

          <label className="check">
            <input type="checkbox" checked={minor} onChange={(e) => setMinor(e.target.checked)} />
            <span>Nina umri chini ya miaka 18</span>
          </label>
          {minor && (
            <>
              <label htmlFor="gname">Jina la mzazi au mlezi</label>
              <input id="gname" value={gName} onChange={(e) => setGName(e.target.value)} required />
              <label htmlFor="gphone">Namba ya mzazi au mlezi</label>
              <input id="gphone" inputMode="tel" value={gPhone} onChange={(e) => setGPhone(e.target.value)} required />
            </>
          )}

          <div className="note" style={{ marginBlockStart: 14 }}>
            <ShieldCheck size={17} aria-hidden="true" />
            <span>
              Tunashikilia jina lako na namba yako ili tukulipe tu. Kumbukumbu ya
              umma inatumia namba ya siri, si jina lako. Picha zako za viwanja
              zinahifadhiwa kama ushahidi. Unaweza kupakua au kufuta taarifa zako
              wakati wowote.{' '}
              <a href="./legal/privacy-policy.md">Soma zaidi</a>.
            </span>
          </div>
          <label className="check">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
            <span>{minor ? 'Mzazi au mlezi wangu amekubali, nami nakubali.' : 'Nakubali.'}</span>
          </label>

          {error && <p className="formerror" role="alert">{error}</p>}
          <button className="btn" type="submit" disabled={ctx.busy || !consent}>
            <UserPlus size={19} aria-hidden="true" />
            Jisajili
          </button>
          <button className="btn" data-variant="ghost" type="button" onClick={() => { setMode('login'); setError(''); }}>
            <LogIn size={19} aria-hidden="true" />
            Nina akaunti tayari
          </button>
        </form>
      )}
    </>
  );
}
