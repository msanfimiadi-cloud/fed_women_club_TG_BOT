import type { PropsWithChildren } from 'react';
import type { PageId } from '../App';
import { BottomNav } from './BottomNav';

interface AppShellProps extends PropsWithChildren {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  onHiddenDiagnosticsGesture?: () => void;
}

export function AppShell({ activePage, onNavigate, children, onHiddenDiagnosticsGesture }: AppShellProps) {
  return (
    <div className="app-shell">
      <button className="app-shell__diagnostic-hotspot" type="button" aria-label="Bloom diagnostics hidden entry" onClick={onHiddenDiagnosticsGesture}>Bloom</button>
      <main className="app-shell__content">
        {children}
      </main>
      <BottomNav activePage={activePage} onNavigate={onNavigate} />
    </div>
  );
}
