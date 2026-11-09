import React from 'react';
import { RouteMeta } from '../../types';
import { ArrowRightIcon } from '../Icons';

interface PlannedViewProps {
  routeMeta: RouteMeta;
  onNavigateHome: () => void;
}

export const PlannedView: React.FC<PlannedViewProps> = ({ routeMeta, onNavigateHome }) => {
  return (
    <div style={{ maxWidth: '800px', margin: '40px auto' }}>
      <div className="sentinel-card" style={{ padding: '36px', textAlign: 'center' }}>
        <div style={{ display: 'inline-block', marginBottom: '16px' }}>
          <span className="badge-planned" style={{ fontSize: '12px', padding: '4px 10px' }}>
            {routeMeta.sprint || 'Future Sprint'} Development Roadmap
          </span>
        </div>

        <h2 style={{ fontSize: '22px', fontWeight: 600, marginBottom: '12px', color: 'var(--color-text-primary)' }}>
          {routeMeta.label} Module
        </h2>

        <p style={{ color: 'var(--color-text-secondary)', fontSize: '14px', lineHeight: 1.6, marginBottom: '24px', maxWidth: '600px', margin: '0 auto 24px auto' }}>
          {routeMeta.description}
        </p>

        <div style={{ textAlign: 'left', background: 'var(--color-bg-subtle)', padding: '20px', borderRadius: '6px', border: '1px solid var(--color-border)', marginBottom: '24px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', marginBottom: '10px' }}>
            Phase 1 Architectural Status
          </div>
          <ul style={{ fontSize: '13px', color: 'var(--color-text-secondary)', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <li>Navigation route, contract schemas, and UI shell registered in Kiro Crew manifest.</li>
            <li>Zero placeholder mock data rendered in accordance with Non-Negotiable Rule D.</li>
            <li>Scheduled for full implementation in {routeMeta.sprint || 'upcoming sprint'} per Master Plan v3.0.</li>
          </ul>
        </div>

        <button
          onClick={onNavigateHome}
          className="nav-item"
          style={{ width: 'auto', background: 'var(--color-accent)', color: '#FFFFFF', padding: '10px 20px', margin: '0 auto', fontSize: '13px' }}
        >
          <span>Return to Overview</span>
          <ArrowRightIcon size={14} />
        </button>
      </div>
    </div>
  );
};
