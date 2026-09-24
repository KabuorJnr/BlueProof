import { FlaskConical } from 'lucide-react';

/**
 * A standing, non-dismissible notice that the system is running on stubs.
 *
 * It exists because the most likely way this project misleads someone is not a
 * sentence in a paper. It is a demonstration: a phone is handed over, a plot is
 * photographed, a species and a confidence score appear in under a second, and
 * everyone in the room concludes that a vision model read the photograph.
 * Nothing on the screen contradicts them.
 *
 * For an attestation product that conclusion is not a small error. The whole
 * value of the ledger is that someone can believe it. So the disclosure goes
 * where the misunderstanding happens, it cannot be dismissed, and it disappears
 * on its own the moment the backend reports real endpoints.
 */
export default function DemoBanner({ meta }) {
  if (!meta) return null;

  const stubbed = [];
  if (meta.llama === 'mock') stubbed.push('verification');
  if (meta.satellite === 'mock') stubbed.push('satellite');
  if (meta.mpesa === 'mock') stubbed.push('payment');
  if (!stubbed.length) return null;

  return (
    <p className="demobanner" role="note">
      <FlaskConical size={15} aria-hidden="true" />
      <span>
        Demo mode: {stubbed.join(', ')} {stubbed.length > 1 ? 'are' : 'is'}{' '}
        simulated, not real. No model has read this photograph, and nothing here
        is evidence of anything.
      </span>
    </p>
  );
}
