import { Coins, MapPinned, Settings as Cog, Sprout, UploadCloud } from 'lucide-react';

const TABS = [
  ['#/plots', 'Viwanja', Sprout],
  ['#/site', 'Eneo', MapPinned],
  ['#/wallet', 'Pochi', Coins],
  ['#/queue', 'Foleni', UploadCloud],
  ['#/settings', 'Mipangilio', Cog],
];

export default function TabBar({ active }) {
  // The capture and verdict screens live under Viwanja, so keep that tab lit.
  const effective = active === '#/monitor' || active === '#/verdict' ? '#/plots' : active;

  return (
    <nav className="tabbar" aria-label="Menyu">
      {TABS.map(([href, label, Icon]) => {
        const current = effective === href;
        return (
          <button
            key={href}
            className="tab"
            aria-current={current ? 'page' : undefined}
            onClick={() => {
              location.hash = href;
            }}
          >
            <Icon size={21} strokeWidth={current ? 2.4 : 1.9} aria-hidden="true" />
            {label}
            <i className="dot" aria-hidden="true" />
          </button>
        );
      })}
    </nav>
  );
}
