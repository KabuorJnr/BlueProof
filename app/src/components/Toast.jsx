import { useEffect } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

export default function Toast({ message, tone, onDone, duration = 3600 }) {
  useEffect(() => {
    const t = setTimeout(onDone, duration);
    return () => clearTimeout(t);
  }, [onDone, duration]);

  const Icon = tone === 'err' ? AlertTriangle : CheckCircle2;
  return (
    <div className="toast" data-tone={tone} role="status" aria-live="polite">
      <Icon size={18} aria-hidden="true" />
      {message}
    </div>
  );
}
