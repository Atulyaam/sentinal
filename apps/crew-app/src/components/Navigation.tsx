import React from 'react';
import { RouteId, RouteMeta } from '../types';
import {
  DashboardIcon,
  InvestigationsIcon,
  FindingsIcon,
  EventsIcon,
  ReplayIcon,
  SourcesIcon,
  DigestsIcon,
  SettingsIcon,
  ShieldIcon,
} from './Icons';

export const ROUTES: RouteMeta[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: 'dashboard',
    description: 'System health, investigation status and workbench summary.',
  },
  {
    id: 'investigations',
    label: 'Investigations',
    icon: 'investigations',
    planned: true,
    sprint: 'Sprint 5',
    description: 'Active correlated cases, timeline graphs, and operator triage decisions.',
  },
  {
    id: 'findings',
    label: 'Findings',
    icon: 'findings',
    planned: true,
    sprint: 'Sprint 4',
    description: 'Deterministic rule detections with parameter thresholds and matched condition sets.',
  },
  {
    id: 'events',
    label: 'Events',
    icon: 'events',
    description: 'Canonical normalized security events, typed attributes, and immutable source provenance.',
  },
  {
    id: 'replay',
    label: 'Replay Lab',
    icon: 'replay',
    planned: true,
    sprint: 'Sprint 7',
    description: 'Deterministic scenario replay runner asserting verifiable detection outputs.',
  },
  {
    id: 'sources',
    label: 'Sources',
    icon: 'sources',
    description: 'Operator-approved local inbox configuration, path containment, and polling state.',
  },
  {
    id: 'digests',
    label: 'Digests',
    icon: 'digests',
    planned: true,
    sprint: 'Sprint 6',
    description: 'Kiro Crew scheduled summaries with deterministic Claim Guard verification audit.',
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: 'settings',
    planned: true,
    sprint: 'Sprint 9',
    description: 'Redaction definitions, backend connection URL, and privacy boundaries.',
  },
];

interface NavigationProps {
  currentRoute: RouteId;
  onNavigate: (route: RouteId) => void;
}

export const Navigation: React.FC<NavigationProps> = ({ currentRoute, onNavigate }) => {
  const getIcon = (iconName: string) => {
    switch (iconName) {
      case 'dashboard': return <DashboardIcon />;
      case 'investigations': return <InvestigationsIcon />;
      case 'findings': return <FindingsIcon />;
      case 'events': return <EventsIcon />;
      case 'replay': return <ReplayIcon />;
      case 'sources': return <SourcesIcon />;
      case 'digests': return <DigestsIcon />;
      case 'settings': return <SettingsIcon />;
      default: return <ShieldIcon />;
    }
  };

  return (
    <aside className="sentinel-sidebar" aria-label="Main Navigation">
      <div style={{ padding: '20px 16px', display: 'flex', alignItems: 'center', gap: '10px', borderBottom: '1px solid var(--color-border)' }}>
        <div style={{ color: 'var(--color-accent)' }}>
          <ShieldIcon size={24} />
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: '15px', letterSpacing: '-0.01em' }}>Project Sentinel</div>
          <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Defensive Workbench</div>
        </div>
      </div>

      <nav style={{ padding: '12px 0', flex: 1 }}>
        {ROUTES.map((route) => {
          const isActive = currentRoute === route.id;
          return (
            <button
              key={route.id}
              onClick={() => onNavigate(route.id)}
              className={`nav-item ${isActive ? 'active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
              title={route.description}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', color: isActive ? 'var(--color-accent)' : 'inherit' }}>
                {getIcon(route.icon)}
              </span>
              <span>{route.label}</span>
              {route.planned && (
                <span className="badge-planned" aria-label={`Scheduled for ${route.sprint}`}>
                  {route.sprint}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div style={{ padding: '16px', borderTop: '1px solid var(--color-border)', fontSize: '11px', color: 'var(--color-text-muted)' }}>
        <div>Kiroween 2026 Edition</div>
        <div style={{ marginTop: '2px', fontFamily: 'var(--font-mono)' }}>Phase 2 Pipeline</div>
      </div>
    </aside>
  );
};
