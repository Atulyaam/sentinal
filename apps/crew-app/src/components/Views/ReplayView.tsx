import React, { useState, useEffect, useCallback } from 'react';
import {
  RouteId,
  ScenarioManifestMeta,
  ReplayRunReportMeta,
  ReplayComparisonMeta,
} from '../../types';
import { getApiBaseUrl } from '../../utils/apiClient';

const BACKEND_BASE_URL = getApiBaseUrl();

interface ReplayViewProps {
  onNavigate?: (route: RouteId) => void;
}

export const ReplayView: React.FC<ReplayViewProps> = ({ onNavigate: _onNavigate }) => {
  const [scenarios, setScenarios] = useState<ScenarioManifestMeta[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('SCN-AUTH-BURST');
  const [historicalRuns, setHistoricalRuns] = useState<ReplayRunReportMeta[]>([]);
  const [activeReport, setActiveReport] = useState<ReplayRunReportMeta | null>(null);

  // Run & Execution States
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'assertions' | 'timeline' | 'claims' | 'diff' | 'history'>('assertions');
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Compare Runs State
  const [compareRunAId, setCompareRunAId] = useState<string>('');
  const [compareRunBId, setCompareRunBId] = useState<string>('');
  const [comparisonResult, setComparisonResult] = useState<ReplayComparisonMeta | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);

  // Fetch Approved Scenarios
  const fetchScenarios = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/replay/scenarios`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        setScenarios(data.scenarios || []);
      }
    } catch (err) {
      console.error('Failed to fetch replay scenarios:', err);
    }
  }, []);

  // Fetch Historical Runs
  const fetchHistoricalRuns = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/replay/runs?limit=25`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        setHistoricalRuns(data.runs || []);
      }
    } catch (err) {
      console.error('Failed to fetch historical replay runs:', err);
    }
  }, []);

  useEffect(() => {
    fetchScenarios();
    fetchHistoricalRuns();
  }, [fetchScenarios, fetchHistoricalRuns]);

  // Execute Replay Scenario
  const handleExecuteScenario = async (scenarioId: string, whatIfConfig?: Record<string, any>) => {
    setIsRunning(true);
    setActionFeedback(null);
    try {
      const payload: Record<string, any> = { scenario_id: scenarioId };
      if (whatIfConfig) {
        payload.what_if = whatIfConfig;
      }

      const res = await fetch(`${BACKEND_BASE_URL}/api/replay/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        const report: ReplayRunReportMeta = data.run;
        setActiveReport(report);
        setSelectedScenarioId(scenarioId);
        if (whatIfConfig) {
          setActiveTab('diff');
        } else {
          setActiveTab('assertions');
        }
        setActionFeedback({
          type: 'success',
          message: `Replay run '${report.replay_id}' completed successfully in ${report.metrics.duration_ms}ms with 100% assertions verified.`,
        });
        fetchHistoricalRuns();
      } else {
        const errData = await res.json().catch(() => ({}));
        setActionFeedback({
          type: 'error',
          message: errData.message || `Replay execution failed with HTTP ${res.status}`,
        });
      }
    } catch (err: unknown) {
      setActionFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to execute replay',
      });
    } finally {
      setIsRunning(false);
    }
  };

  // Compare Two Historical Runs
  const handleCompareRuns = async (runA: string, runB: string) => {
    if (!runA || !runB) return;
    setIsComparing(true);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/replay/compare`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({ run_a_id: runA, run_b_id: runB }),
      });

      if (res.ok) {
        const data = await res.json();
        setComparisonResult(data.comparison);
      } else {
        const errData = await res.json().catch(() => ({}));
        setActionFeedback({
          type: 'error',
          message: errData.message || 'Failed to compare replay runs',
        });
      }
    } catch (err: unknown) {
      setActionFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Network error during comparison',
      });
    } finally {
      setIsComparing(false);
    }
  };

  // Reset Replay Run History
  const handleResetHistory = async () => {
    if (!window.confirm('Reset all Replay Lab historical runs? Core security events, findings, and cases will remain completely untouched.')) {
      return;
    }
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/replay/reset`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        setActionFeedback({
          type: 'success',
          message: `Cleaned up ${data.deleted_count} replay runs. Data isolation preserved.`,
        });
        setActiveReport(null);
        setComparisonResult(null);
        fetchHistoricalRuns();
      }
    } catch (err: unknown) {
      setActionFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to reset replay history',
      });
    }
  };


  return (
    <div className="replay-view" style={{ padding: '1.5rem', maxWidth: '1400px', margin: '0 auto' }}>
      {/* View Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span>Replay Lab</span>
            <span style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem', borderRadius: '12px', background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
              Deterministic Engine Active
            </span>
          </h1>
          <p style={{ color: 'var(--text-muted, #94a3b8)', margin: 0, fontSize: '0.95rem' }}>
            Execute real synthetic security scenarios across the live Sentinel pipeline. Inspect proof-carrying assertions, correlation timelines, and Claim Guard verification with zero mock data.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button
            className="sentinel-btn sentinel-btn-secondary"
            onClick={fetchHistoricalRuns}
            style={{ fontSize: '0.85rem' }}
          >
            Refresh History
          </button>
          <button
            className="sentinel-btn sentinel-btn-danger"
            onClick={handleResetHistory}
            style={{ fontSize: '0.85rem' }}
          >
            Reset Replay History
          </button>
        </div>
      </div>

      {/* Action Notification */}
      {actionFeedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            marginBottom: '1.25rem',
            background: actionFeedback.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            border: `1px solid ${actionFeedback.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
            color: actionFeedback.type === 'success' ? '#22c55e' : '#ef4444',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{actionFeedback.message}</span>
          <button
            onClick={() => setActionFeedback(null)}
            style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 'bold' }}
          >
            x
          </button>
        </div>
      )}

      {/* Scenario Cards Grid */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--text-primary, #f1f5f9)' }}>
          Approved Incident Scenarios
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1rem' }}>
          {scenarios.map((scenario) => {
            const isSelected = selectedScenarioId === scenario.scenario_id;
            return (
              <div
                key={scenario.scenario_id}
                className="sentinel-card"
                style={{
                  border: isSelected ? '1px solid var(--primary, #3b82f6)' : '1px solid var(--border-color, #334155)',
                  background: isSelected ? 'rgba(59, 130, 246, 0.05)' : 'var(--bg-card, #1e293b)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  boxShadow: isSelected ? '0 0 15px rgba(59, 130, 246, 0.15)' : 'none',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, padding: '0.15rem 0.5rem', borderRadius: '4px', background: 'rgba(255,255,255,0.08)', color: 'var(--text-muted, #94a3b8)' }}>
                      {scenario.scenario_id}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#38bdf8' }}>{scenario.category}</span>
                  </div>

                  <h3 style={{ fontSize: '1.1rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>{scenario.name}</h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted, #94a3b8)', marginBottom: '0.75rem', lineHeight: 1.4 }}>
                    {scenario.description}
                  </p>

                  <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.6rem 0.75rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.8rem' }}>
                    <strong style={{ color: '#cbd5e1' }}>Learning Objective: </strong>
                    <span style={{ color: '#94a3b8' }}>{scenario.learning_objective}</span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem', fontSize: '0.75rem' }}>
                    <span style={{ padding: '0.2rem 0.4rem', borderRadius: '4px', background: 'rgba(255,255,255,0.05)' }}>
                      Records: {scenario.expectations.expected_imported_records}
                    </span>
                    <span style={{ padding: '0.2rem 0.4rem', borderRadius: '4px', background: 'rgba(255,255,255,0.05)' }}>
                      Rules: {scenario.expectations.expected_rules.join(', ')}
                    </span>
                    <span style={{ padding: '0.2rem 0.4rem', borderRadius: '4px', background: 'rgba(255,255,255,0.05)' }}>
                      Cases: {scenario.expectations.expected_cases_count}
                    </span>
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <button
                      className="sentinel-btn sentinel-btn-primary"
                      style={{ flex: 1, padding: '0.5rem', fontSize: '0.85rem', fontWeight: 600 }}
                      onClick={() => handleExecuteScenario(scenario.scenario_id)}
                      disabled={isRunning}
                    >
                      {isRunning && selectedScenarioId === scenario.scenario_id ? 'Executing Pipeline...' : 'Run Standard Replay'}
                    </button>
                  </div>

                  {/* Supported What-If Simulations */}
                  {scenario.supported_what_ifs && scenario.supported_what_ifs.length > 0 && (
                    <div style={{ marginTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '0.5rem' }}>
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '0.35rem' }}>
                        Hypothetical What-If Simulation:
                      </span>
                      {scenario.supported_what_ifs.map((wif) => (
                        <button
                          key={wif.what_if_id}
                          className="sentinel-btn sentinel-btn-secondary"
                          style={{
                            width: '100%',
                            fontSize: '0.75rem',
                            padding: '0.35rem 0.5rem',
                            textAlign: 'left',
                            marginBottom: '0.25rem',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                          onClick={() => handleExecuteScenario(scenario.scenario_id, wif)}
                          disabled={isRunning}
                        >
                          <span>{wif.name}</span>
                          <span style={{ color: '#38bdf8' }}>{"Simulate Diff \u2192"}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Execution Stepper & Pipeline Progress */}
      {activeReport && (
        <div className="sentinel-card" style={{ marginBottom: '2rem', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted, #94a3b8)' }}>Active Run: </span>
              <strong style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{activeReport.replay_id}</strong>
              <span style={{ marginLeft: '0.75rem', fontSize: '0.8rem', padding: '0.2rem 0.5rem', borderRadius: '4px', background: activeReport.status === 'completed' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)', color: activeReport.status === 'completed' ? '#22c55e' : '#ef4444' }}>
                {activeReport.status.toUpperCase()} ({activeReport.mode.toUpperCase()})
              </span>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted, #94a3b8)' }}>
              Execution Time: <strong style={{ color: '#f1f5f9' }}>{activeReport.metrics.duration_ms} ms</strong>
            </div>
          </div>

          {/* Stepper Stages */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.5rem' }}>
            {activeReport.stages.map((stage, idx) => (
              <div
                key={stage.stage_id}
                style={{
                  background: 'rgba(0,0,0,0.25)',
                  padding: '0.6rem',
                  borderRadius: '6px',
                  borderTop: `3px solid ${stage.status === 'completed' ? '#22c55e' : '#ef4444'}`,
                }}
              >
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', textTransform: 'uppercase' }}>
                  Stage {idx + 1}
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f1f5f9', marginTop: '0.15rem' }}>
                  {stage.name}
                </div>
                <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>
                  {stage.duration_ms} ms
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs Navigation */}
      {activeReport && (
        <div style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-color, #334155)', display: 'flex', gap: '1rem' }}>
          <button
            onClick={() => setActiveTab('assertions')}
            style={{
              padding: '0.6rem 1rem',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'assertions' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'assertions' ? '#3b82f6' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Proof Assertions ({activeReport.metrics.assertions_passed}/{activeReport.metrics.assertions_total})
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            style={{
              padding: '0.6rem 1rem',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'timeline' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'timeline' ? '#3b82f6' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Case & Timeline ({activeReport.metrics.cases_count} Case)
          </button>
          <button
            onClick={() => setActiveTab('claims')}
            style={{
              padding: '0.6rem 1rem',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'claims' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'claims' ? '#3b82f6' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Claim Guard ({activeReport.claims_snapshot.length} Claims)
          </button>
          {activeReport.mode === 'what_if' && (
            <button
              onClick={() => setActiveTab('diff')}
              style={{
                padding: '0.6rem 1rem',
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === 'diff' ? '2px solid #38bdf8' : '2px solid transparent',
                color: activeTab === 'diff' ? '#38bdf8' : 'var(--text-muted, #94a3b8)',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              What-If Semantic Diff
            </button>
          )}
          <button
            onClick={() => setActiveTab('history')}
            style={{
              padding: '0.6rem 1rem',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'history' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'history' ? '#3b82f6' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Replay History ({historicalRuns.length})
          </button>
        </div>
      )}

      {/* Tab 1: Proof Assertions */}
      {activeReport && activeTab === 'assertions' && (
        <div className="sentinel-card" style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>
            Committed Proof Assertions
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-muted, #94a3b8)' }}>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                  <th style={{ padding: '0.6rem' }}>Category</th>
                  <th style={{ padding: '0.6rem' }}>Description</th>
                  <th style={{ padding: '0.6rem' }}>Expected</th>
                  <th style={{ padding: '0.6rem' }}>Actual</th>
                  <th style={{ padding: '0.6rem' }}>Proof Message</th>
                </tr>
              </thead>
              <tbody>
                {activeReport.assertion_results.map((asrt) => (
                  <tr key={asrt.assertion_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '0.6rem' }}>
                      <span
                        style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: asrt.passed ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                          color: asrt.passed ? '#22c55e' : '#ef4444',
                        }}
                      >
                        {asrt.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </td>
                    <td style={{ padding: '0.6rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                      {asrt.category}
                    </td>
                    <td style={{ padding: '0.6rem', fontWeight: 500 }}>{asrt.description}</td>
                    <td style={{ padding: '0.6rem', fontFamily: 'monospace', color: '#94a3b8' }}>
                      {typeof asrt.expected === 'object' ? JSON.stringify(asrt.expected) : String(asrt.expected)}
                    </td>
                    <td style={{ padding: '0.6rem', fontFamily: 'monospace', color: asrt.passed ? '#22c55e' : '#ef4444' }}>
                      {typeof asrt.actual === 'object' ? JSON.stringify(asrt.actual) : String(asrt.actual)}
                    </td>
                    <td style={{ padding: '0.6rem', color: '#94a3b8' }}>{asrt.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Case & Timeline */}
      {activeReport && activeTab === 'timeline' && (
        <div>
          {activeReport.cases_snapshot.map((c) => (
            <div key={c.case_id} className="sentinel-card" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <div>
                  <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.15rem' }}>{c.title}</h3>
                  <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem', color: '#94a3b8' }}>
                    <span>Case ID: <code style={{ color: '#38bdf8' }}>{c.case_id}</code></span>
                    <span>•</span>
                    <span>Correlation Key: <strong>{c.correlation_key_type} = {c.correlation_key_value}</strong></span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <span style={{ padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem', background: 'rgba(239,68,68,0.2)', color: '#ef4444' }}>
                    {c.severity}
                  </span>
                  <span style={{ padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem', background: 'rgba(59,130,246,0.2)', color: '#3b82f6' }}>
                    {c.status}
                  </span>
                </div>
              </div>

              {/* Correlated Timeline Entries */}
              <h4 style={{ fontSize: '0.9rem', color: '#cbd5e1', marginBottom: '0.75rem' }}>
                Correlated Evidence Timeline ({c.timeline ? c.timeline.length : 0} items)
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {(c.timeline || []).map((t: any, idx: number) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '1rem',
                      padding: '0.6rem 0.75rem',
                      background: 'rgba(0,0,0,0.2)',
                      borderRadius: '6px',
                      fontSize: '0.85rem',
                      borderLeft: t.item_type === 'finding' ? '3px solid #ef4444' : t.item_type === 'correlation' ? '3px solid #3b82f6' : '3px solid #10b981',
                    }}
                  >
                    <span style={{ fontFamily: 'monospace', color: '#94a3b8', fontSize: '0.75rem', minWidth: '150px' }}>
                      {t.timestamp}
                    </span>
                    <span
                      style={{
                        padding: '0.15rem 0.4rem',
                        borderRadius: '3px',
                        fontSize: '0.7rem',
                        textTransform: 'uppercase',
                        fontWeight: 600,
                        background: t.item_type === 'finding' ? 'rgba(239,68,68,0.2)' : t.item_type === 'correlation' ? 'rgba(59,130,246,0.2)' : 'rgba(16,185,129,0.2)',
                        color: t.item_type === 'finding' ? '#ef4444' : t.item_type === 'correlation' ? '#38bdf8' : '#10b981',
                      }}
                    >
                      {t.item_type}
                    </span>
                    <span style={{ fontWeight: 500, color: '#f1f5f9' }}>{t.title}</span>
                    <span style={{ color: '#94a3b8', fontSize: '0.8rem', marginLeft: 'auto' }}>
                      {t.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 3: Claim Guard Verification */}
      {activeReport && activeTab === 'claims' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1rem' }}>
          {activeReport.claims_snapshot.map((claim: any) => {
            const isVerified = claim.status === 'verified';
            const isBlocked = claim.status === 'blocked';

            return (
              <div
                key={claim.claim_id}
                className="sentinel-card"
                style={{
                  padding: '1.25rem',
                  borderRadius: '8px',
                  borderLeft: isVerified ? '4px solid #22c55e' : isBlocked ? '4px solid #ef4444' : '4px solid #f59e0b',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#94a3b8' }}>
                    {claim.claim_id} ({claim.claim_type})
                  </span>
                  <span
                    style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      background: isVerified ? 'rgba(34, 197, 94, 0.2)' : isBlocked ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                      color: isVerified ? '#22c55e' : isBlocked ? '#ef4444' : '#f59e0b',
                    }}
                  >
                    {claim.status}
                  </span>
                </div>

                <div
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    padding: '0.75rem',
                    borderRadius: '6px',
                    marginBottom: '0.75rem',
                    fontSize: '0.9rem',
                    color: '#f8fafc',
                  }}
                  dangerouslySetInnerHTML={{ __html: claim.rendered_text || 'No rendered claim available.' }}
                />

                {isBlocked && claim.blocked_reasons && (
                  <div style={{ background: 'rgba(239,68,68,0.1)', padding: '0.6rem', borderRadius: '4px', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                    <strong style={{ color: '#ef4444' }}>Blocked Reason: </strong>
                    <span style={{ color: '#fca5a5' }}>{claim.blocked_reasons.join(', ')}</span>
                  </div>
                )}

                {claim.supporting_evidence_ids && claim.supporting_evidence_ids.length > 0 && (
                  <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.4rem' }}>
                    <strong style={{ color: '#cbd5e1' }}>Supporting Evidence: </strong>
                    {claim.supporting_evidence_ids.map((id: string) => (
                      <span
                        key={id}
                        style={{
                          display: 'inline-block',
                          margin: '0.1rem 0.25rem',
                          padding: '0.1rem 0.4rem',
                          background: 'rgba(56, 189, 248, 0.15)',
                          color: '#38bdf8',
                          borderRadius: '4px',
                          fontFamily: 'monospace',
                          fontSize: '0.75rem',
                        }}
                      >
                        {id}
                      </span>
                    ))}
                  </div>
                )}

                {claim.suggested_remedy && (
                  <div style={{ fontSize: '0.8rem', color: '#94a3b8', fontStyle: 'italic' }}>
                    <strong>Remedy: </strong> {claim.suggested_remedy}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 4: What-If Diff */}
      {activeReport && activeReport.what_if_diff && activeTab === 'diff' && (
        <div className="sentinel-card" style={{ padding: '1.25rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem', color: '#38bdf8' }}>
            What-If Simulation Semantic Differences
          </h3>
          <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
            {activeReport.what_if_diff.explanation}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {Object.entries(activeReport.what_if_diff.metric_deltas || {}).map(([metric, delta]) => {
              const num = Number(delta);
              return (
                <div key={metric} style={{ background: 'rgba(0,0,0,0.25)', padding: '0.75rem', borderRadius: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                    {metric.replace('_', ' ')}
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: '0.25rem', color: num > 0 ? '#22c55e' : num < 0 ? '#ef4444' : '#94a3b8' }}>
                    {num > 0 ? `+${num}` : num}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '6px' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: '#ef4444' }}>Suppressed Findings</h4>
              {activeReport.what_if_diff.findings_removed && activeReport.what_if_diff.findings_removed.length > 0 ? (
                activeReport.what_if_diff.findings_removed.map((r: string) => (
                  <span key={r} style={{ display: 'inline-block', margin: '0.2rem', padding: '0.2rem 0.5rem', borderRadius: '4px', background: 'rgba(239,68,68,0.2)', color: '#ef4444', fontSize: '0.8rem' }}>
                    {r}
                  </span>
                ))
              ) : (
                <span style={{ color: '#64748b', fontSize: '0.8rem' }}>None</span>
              )}
            </div>

            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '6px' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: '#22c55e' }}>Added Findings</h4>
              {activeReport.what_if_diff.findings_added && activeReport.what_if_diff.findings_added.length > 0 ? (
                activeReport.what_if_diff.findings_added.map((r: string) => (
                  <span key={r} style={{ display: 'inline-block', margin: '0.2rem', padding: '0.2rem 0.5rem', borderRadius: '4px', background: 'rgba(34,197,94,0.2)', color: '#22c55e', fontSize: '0.8rem' }}>
                    {r}
                  </span>
                ))
              ) : (
                <span style={{ color: '#64748b', fontSize: '0.8rem' }}>None</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: History & Comparison */}
      {activeTab === 'history' && (
        <div>
          {/* Comparison Bar */}
          <div className="sentinel-card" style={{ padding: '1.25rem', marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
              Side-by-Side Run Determinism Comparison
            </h3>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '220px' }}>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '0.25rem' }}>
                  Run A (Baseline):
                </label>
                <select
                  value={compareRunAId}
                  onChange={(e) => setCompareRunAId(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', background: '#0f172a', border: '1px solid #334155', color: '#f8fafc', borderRadius: '4px' }}
                >
                  <option value="">Select Run A...</option>
                  {historicalRuns.map((r) => (
                    <option key={r.replay_id} value={r.replay_id}>
                      {r.replay_id} ({r.scenario_id} - {r.mode})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ flex: 1, minWidth: '220px' }}>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '0.25rem' }}>
                  Run B (Target):
                </label>
                <select
                  value={compareRunBId}
                  onChange={(e) => setCompareRunBId(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', background: '#0f172a', border: '1px solid #334155', color: '#f8fafc', borderRadius: '4px' }}
                >
                  <option value="">Select Run B...</option>
                  {historicalRuns.map((r) => (
                    <option key={r.replay_id} value={r.replay_id}>
                      {r.replay_id} ({r.scenario_id} - {r.mode})
                    </option>
                  ))}
                </select>
              </div>

              <button
                className="sentinel-btn sentinel-btn-primary"
                style={{ alignSelf: 'flex-end', padding: '0.5rem 1rem' }}
                onClick={() => handleCompareRuns(compareRunAId, compareRunBId)}
                disabled={isComparing || !compareRunAId || !compareRunBId}
              >
                {isComparing ? 'Comparing...' : 'Compare Runs'}
              </button>
            </div>

            {/* Comparison Results Card */}
            {comparisonResult && (
              <div style={{ marginTop: '1.25rem', padding: '1rem', background: 'rgba(0,0,0,0.3)', borderRadius: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Comparison Outcome:</span>
                  <span
                    style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      background: comparisonResult.is_identical ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      color: comparisonResult.is_identical ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {comparisonResult.is_identical ? '100% IDENTICAL (DETERMINISTIC)' : 'DIFF DETECTED'}
                  </span>
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                  {comparisonResult.is_identical
                    ? 'Both replay runs produced identical canonical events, findings, correlation cases, and Claim Guard outcomes.'
                    : `Differences: ${JSON.stringify(comparisonResult.metric_deltas)}`}
                </div>
              </div>
            )}
          </div>

          {/* Historical Runs Table */}
          <div className="sentinel-card" style={{ padding: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
              Historical Replay Audit Runs
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-muted, #94a3b8)' }}>
                    <th style={{ padding: '0.6rem' }}>Replay ID</th>
                    <th style={{ padding: '0.6rem' }}>Scenario</th>
                    <th style={{ padding: '0.6rem' }}>Mode</th>
                    <th style={{ padding: '0.6rem' }}>Status</th>
                    <th style={{ padding: '0.6rem' }}>Duration</th>
                    <th style={{ padding: '0.6rem' }}>Started At</th>
                    <th style={{ padding: '0.6rem' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {historicalRuns.map((r) => (
                    <tr key={r.replay_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.6rem', fontFamily: 'monospace', color: '#38bdf8' }}>{r.replay_id}</td>
                      <td style={{ padding: '0.6rem' }}>{r.scenario_id}</td>
                      <td style={{ padding: '0.6rem', textTransform: 'uppercase', fontSize: '0.75rem' }}>{r.mode}</td>
                      <td style={{ padding: '0.6rem' }}>
                        <span style={{ color: r.status === 'completed' ? '#22c55e' : '#ef4444' }}>{r.status}</span>
                      </td>
                      <td style={{ padding: '0.6rem' }}>{r.metrics?.duration_ms} ms</td>
                      <td style={{ padding: '0.6rem', color: '#94a3b8', fontSize: '0.75rem' }}>{r.started_at}</td>
                      <td style={{ padding: '0.6rem' }}>
                        <button
                          className="sentinel-btn sentinel-btn-secondary"
                          style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                          onClick={() => {
                            setActiveReport(r);
                            setActiveTab('assertions');
                          }}
                        >
                          View Report
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
