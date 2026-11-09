import React from 'react';
import { BackendHealthState, RouteId } from '../../types';
import { ArrowRightIcon, ShieldIcon, CheckIcon, AlertCircleIcon, RefreshIcon } from '../Icons';

interface OverviewViewProps {
  health: BackendHealthState;
  onRefreshHealth: () => void;
  isChecking: boolean;
  onNavigate: (route: RouteId) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  health,
  onRefreshHealth,
  isChecking,
  onNavigate,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Product Banner */}
      <section className="sentinel-card" aria-labelledby="banner-heading">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '20px' }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: 'var(--color-accent)', marginBottom: '8px' }}>
              <ShieldIcon size={16} />
              <span style={{ fontSize: '12px', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Proof-Carrying Defensive Investigation
              </span>
            </div>
            <h2 id="banner-heading" style={{ fontSize: '20px', fontWeight: 600, marginBottom: '8px' }}>
              Welcome to Project Sentinel
            </h2>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: '14px', maxWidth: '800px', lineHeight: 1.6 }}>
              Sentinel turns approved security logs into an evidence-linked investigation that a human can understand, replay, challenge and review. It detects explainable patterns, preserves immutable source provenance, and refuses to present AI-generated claims unless structured evidence checks pass (**Claim Guard**).
            </p>
          </div>
        </div>
      </section>

      {/* Backend Engine Status Banner */}
      <section className="sentinel-card" aria-labelledby="engine-status-heading">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 id="engine-status-heading" style={{ fontSize: '14px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)' }}>
            Investigation Engine Connectivity
          </h3>
          <button
            onClick={onRefreshHealth}
            disabled={isChecking}
            className="nav-item"
            style={{ width: 'auto', padding: '6px 12px', margin: 0, fontSize: '12px', border: '1px solid var(--color-border)' }}
          >
            <RefreshIcon size={14} className={isChecking ? 'animate-spin' : ''} />
            <span>Check Connectivity</span>
          </button>
        </div>

        {health.state === 'connected' && health.data && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
            <div style={{ background: 'var(--color-bg-subtle)', padding: '14px', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Application</div>
              <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-text-primary)' }}>{health.data.app}</div>
            </div>
            <div style={{ background: 'var(--color-bg-subtle)', padding: '14px', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Service Status</div>
              <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckIcon size={16} />
                <span>Operational</span>
              </div>
            </div>
            <div style={{ background: 'var(--color-bg-subtle)', padding: '14px', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Engine Version</div>
              <div style={{ fontSize: '15px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>v{health.data.version}</div>
            </div>
            <div style={{ background: 'var(--color-bg-subtle)', padding: '14px', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Last Verified</div>
              <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
                {health.lastChecked ? health.lastChecked.toLocaleTimeString() : 'Just now'}
              </div>
            </div>
          </div>
        )}

        {health.state === 'connecting' && (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-text-secondary)', background: 'var(--color-bg-subtle)', borderRadius: '6px' }}>
            <div style={{ display: 'inline-block', marginBottom: '8px' }}>
              <RefreshIcon size={20} />
            </div>
            <div>Querying backend service at configured endpoint...</div>
          </div>
        )}

        {health.state === 'disconnected' && (
          <div style={{ padding: '20px', background: 'var(--color-danger-bg)', border: '1px solid var(--color-danger)', borderRadius: '6px', color: 'var(--color-text-primary)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
              <AlertCircleIcon size={20} style={{ color: 'var(--color-danger)', marginTop: '2px' }} />
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Backend Engine Offline</div>
                <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
                  The application shell is running, but could not connect to the Sentinel backend service on <code style={{ color: '#F0F6FC' }}>127.0.0.1:8000/health</code>.
                </p>
                <div style={{ fontSize: '12px', background: 'rgba(0,0,0,0.3)', padding: '10px 12px', borderRadius: '4px', fontFamily: 'var(--font-mono)' }}>
                  Start backend with: python -m backend.api.server
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Genuine Empty State for Active Investigations */}
      <section className="sentinel-card" aria-labelledby="investigations-heading">
        <h3 id="investigations-heading" style={{ fontSize: '14px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', marginBottom: '16px' }}>
          Active Investigations
        </h3>
        
        <div style={{ textAlign: 'center', padding: '40px 20px', background: 'var(--color-bg-subtle)', borderRadius: '6px', border: '1px dashed var(--color-border)' }}>
          <div style={{ display: 'inline-flex', padding: '12px', borderRadius: '50%', background: 'var(--color-bg-muted)', color: 'var(--color-text-muted)', marginBottom: '12px' }}>
            <ShieldIcon size={28} />
          </div>
          <h4 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>
            No Active Investigations
          </h4>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '13px', maxWidth: '520px', margin: '0 auto 20px auto', lineHeight: 1.5 }}>
            Sentinel does not generate artificial alarms. Investigations are created when approved security logs are placed in the configured inbox and match deterministic detection criteria, or when a synthetic scenario is executed in the Replay Lab.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
            <button
              onClick={() => onNavigate('events')}
              className="nav-item"
              style={{ width: 'auto', background: 'var(--color-accent)', color: '#FFFFFF', padding: '8px 16px', margin: 0, fontSize: '13px' }}
            >
              <span>Inspect Canonical Events</span>
              <ArrowRightIcon size={14} />
            </button>
            <button
              onClick={() => onNavigate('sources')}
              className="nav-item"
              style={{ width: 'auto', background: 'transparent', border: '1px solid var(--color-border)', padding: '8px 16px', margin: 0, fontSize: '13px' }}
            >
              <span>View Ingestion Sources</span>
            </button>
          </div>
        </div>
      </section>

      {/* Architectural Pipeline Modules Overview */}
      <section aria-labelledby="pipeline-heading">
        <h3 id="pipeline-heading" style={{ fontSize: '14px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', marginBottom: '16px' }}>
          Investigation Lifecycle Architecture
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          <div className="sentinel-card">
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-accent)', marginBottom: '6px' }}>STAGE 1</div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>Approved Inbox Ingestion</h4>
            <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: 1.5, marginBottom: '12px' }}>
              Files from a single operator-confirmed directory are parsed with SHA-256 idempotency and automatic secret redaction.
            </p>
            <span className="badge-planned" style={{ marginLeft: 0 }}>Sprint 2 Delivery</span>
          </div>

          <div className="sentinel-card">
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-accent)', marginBottom: '6px' }}>STAGE 2</div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>Deterministic Detection</h4>
            <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: 1.5, marginBottom: '12px' }}>
              Versioned detection rules evaluate conditions against normalized event streams, emitting findings linked to supporting record IDs.
            </p>
            <span className="badge-planned" style={{ marginLeft: 0 }}>Sprint 4 Delivery</span>
          </div>

          <div className="sentinel-card">
            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-accent)', marginBottom: '6px' }}>STAGE 3</div>
            <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>Proof-Carrying Claim Guard</h4>
            <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: 1.5, marginBottom: '12px' }}>
              A deterministic verifier mathematically checks typed AI claim proposals against case evidence before rendering them as facts.
            </p>
            <span className="badge-planned" style={{ marginLeft: 0 }}>Sprint 6 Delivery</span>
          </div>
        </div>
      </section>
    </div>
  );
};
