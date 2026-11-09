import React from 'react';
import { RouteId, BackendHealthState } from '../types';
import { StatusBadge } from './StatusBadge';
import { ROUTES } from './Navigation';

interface HeaderProps {
  currentRoute: RouteId;
  health: BackendHealthState;
  onRefreshHealth: () => void;
  isChecking: boolean;
}

export const Header: React.FC<HeaderProps> = ({ 
  currentRoute, 
  health, 
  onRefreshHealth, 
  isChecking 
}) => {
  const currentMeta = ROUTES.find((r) => r.id === currentRoute) || ROUTES[0];

  return (
    <header className="sentinel-header" role="banner">
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <h1 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          {currentMeta.label}
        </h1>
        {currentMeta.planned && (
          <span className="badge-planned" style={{ fontSize: '11px', padding: '3px 8px' }}>
            {currentMeta.sprint} Roadmap
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <StatusBadge
          state={health.state}
          appVersion={health.data?.version}
          onRefresh={onRefreshHealth}
          isChecking={isChecking}
        />
      </div>
    </header>
  );
};
