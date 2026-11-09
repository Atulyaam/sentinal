import React, { useState, useEffect, useCallback } from 'react';
import { Case, CaseStats, CaseStatus, CaseSeverity, RouteId, TimelineItem, Finding, NormalizedEvent, ClaimVerificationResult } from '../../types';
import { getApiBaseUrl } from '../../utils/apiClient';

const BACKEND_BASE_URL = getApiBaseUrl();

interface CasesViewProps {
  onNavigate?: (route: RouteId) => void;
}

export const CasesView: React.FC<CasesViewProps> = ({ onNavigate }) => {
  const [cases, setCases] = useState<Case[]>([]);
  const [stats, setStats] = useState<CaseStats | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [limit] = useState<number>(50);
  const [offset, setOffset] = useState<number>(0);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selected Case Detail
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'claims' | 'findings' | 'events' | 'correlation' | 'reviews'>('timeline');

  // Loading & Action states
  const [loading, setLoading] = useState<boolean>(true);
  const [correlating, setCorrelating] = useState<boolean>(false);
  const [verifyingClaims, setVerifyingClaims] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Review note inputs
  const [operatorNote, setOperatorNote] = useState<string>('');
  const [selectedNextStatus, setSelectedNextStatus] = useState<CaseStatus>('UnderReview');
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);

  // Detail sub-selection
  const [selectedFindingDetail, setSelectedFindingDetail] = useState<Finding | null>(null);
  const [selectedEventDetail, setSelectedEventDetail] = useState<NormalizedEvent | null>(null);

  // Load case stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/cases/stats`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data: CaseStats = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch case stats:', err);
    }
  }, []);

  // Load cases list
  const fetchCases = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      if (statusFilter !== 'ALL') params.set('status', statusFilter);
      if (severityFilter !== 'ALL') params.set('severity', severityFilter);

      const res = await fetch(`${BACKEND_BASE_URL}/api/cases?${params.toString()}`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        let list: Case[] = data.cases || [];
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          list = list.filter(
            (c) =>
              c.title.toLowerCase().includes(q) ||
              c.case_id.toLowerCase().includes(q) ||
              c.correlation_key_value.toLowerCase().includes(q)
          );
        }
        setCases(list);
        setTotal(data.total || 0);
      } else {
        setActionFeedback({ type: 'error', message: `Failed to load cases: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error loading cases';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setLoading(false);
    }
  }, [limit, offset, statusFilter, severityFilter, searchQuery]);

  // Load specific case detail
  const openCaseDetail = async (caseId: string) => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/cases/${caseId}`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data: Case = await res.json();
        setSelectedCase(data);
        setSelectedNextStatus(data.status === 'Open' ? 'UnderReview' : data.status);
        setSelectedFindingDetail(null);
        setSelectedEventDetail(null);
        setActiveTab('timeline');
      } else {
        setActionFeedback({ type: 'error', message: `Failed to load case detail: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch case detail';
      setActionFeedback({ type: 'error', message: msg });
    }
  };

  useEffect(() => {
    fetchStats();
    fetchCases();
  }, [fetchStats, fetchCases]);

  // Trigger Correlation Engine
  const handleRunCorrelation = async () => {
    setCorrelating(true);
    setActionFeedback(null);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/cases/correlate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ limit_findings: 1000 }),
      });
      if (res.ok) {
        const data = await res.json();
        const r = data.result || {};
        setActionFeedback({
          type: 'success',
          message: `Correlation completed: ${r.findings_scanned ?? 0} findings scanned, ${r.cases_created ?? 0} cases created, ${r.cases_updated ?? 0} updated in ${r.duration_ms ?? 0}ms.`,
        });
        fetchStats();
        fetchCases();
        if (selectedCase) {
          openCaseDetail(selectedCase.case_id);
        }
      } else {
        setActionFeedback({ type: 'error', message: `Correlation run failed: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Correlation execution failed';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setCorrelating(false);
    }
  };

  // Run Claim Guard Verification on Case
  const runClaimGuardDemo = async (caseId: string) => {
    setVerifyingClaims(true);
    setActionFeedback(null);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/cases/${caseId}/claims/demo`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        const results: ClaimVerificationResult[] = data.report?.results || [];
        if (selectedCase && selectedCase.case_id === caseId) {
          setSelectedCase({ ...selectedCase, claims: results });
        }
        setActionFeedback({
          type: 'success',
          message: `Claim Guard completed: ${data.report?.verified_count || 0} verified, ${data.report?.qualified_count || 0} qualified, ${data.report?.blocked_count || 0} blocked.`,
        });
      } else {
        setActionFeedback({ type: 'error', message: `Claim Guard verification failed: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error executing Claim Guard';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setVerifyingClaims(false);
    }
  };

  // Submit Operator Review / Note / Status Change
  const handleSubmitReview = async () => {
    if (!selectedCase) return;
    if (!operatorNote.trim() && selectedNextStatus === selectedCase.status) {
      setActionFeedback({ type: 'error', message: 'Please enter an operator note or select a new status.' });
      return;
    }

    setSubmittingReview(true);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/cases/${selectedCase.case_id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          note: operatorNote.trim(),
          status: selectedNextStatus !== selectedCase.status ? selectedNextStatus : undefined,
          author: 'secops_operator',
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setSelectedCase(data.case);
        setOperatorNote('');
        setActionFeedback({ type: 'success', message: 'Review action recorded successfully.' });
        fetchStats();
        fetchCases();
      } else {
        const errData = await res.json().catch(() => ({}));
        setActionFeedback({
          type: 'error',
          message: errData.message || `Failed to record review: HTTP ${res.status}`,
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Review action failed';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setSubmittingReview(false);
    }
  };

  // Severity styling
  const getSeverityBadgeClass = (sev: CaseSeverity | string) => {
    switch (sev) {
      case 'Critical': return 'badge-critical';
      case 'High': return 'badge-high';
      case 'Medium': return 'badge-medium';
      case 'Low': return 'badge-low';
      default: return 'badge-info';
    }
  };

  // Status styling
  const getStatusBadgeClass = (status: CaseStatus | string) => {
    switch (status) {
      case 'Open': return 'status-badge-open';
      case 'UnderReview': return 'status-badge-review';
      case 'NeedsMoreEvidence': return 'status-badge-evidence';
      case 'Resolved': return 'status-badge-resolved';
      case 'Dismissed': return 'status-badge-dismissed';
      default: return '';
    }
  };

  return (
    <div className="view-container">
      {/* View Header */}
      <div className="view-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>Investigation Cases & Timeline</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--color-text-secondary)', fontSize: '14px' }}>
            Deterministic correlation grouping related security findings into evidence-backed investigation cases.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleRunCorrelation}
            disabled={correlating}
            className="action-button primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}
          >
            {correlating ? (
              <>
                <span className="spinner" style={{ width: '14px', height: '14px' }} />
                <span>Correlating Evidence...</span>
              </>
            ) : (
              <>
                <span>Run Correlation Engine</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Action Feedback Banner */}
      {actionFeedback && (
        <div
          role="status"
          aria-live="polite"
          style={{
            padding: '12px 16px',
            borderRadius: '6px',
            marginBottom: '20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            backgroundColor: actionFeedback.type === 'success' ? 'rgba(52, 211, 153, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            border: `1px solid ${actionFeedback.type === 'success' ? '#34d399' : '#ef4444'}`,
            color: actionFeedback.type === 'success' ? '#34d399' : '#ef4444',
            fontSize: '14px',
          }}
        >
          <span>{actionFeedback.message}</span>
          <button
            onClick={() => setActionFeedback(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '18px' }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Metrics Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div className="card" style={{ padding: '16px', borderLeft: '4px solid var(--color-accent)' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Cases</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>{stats?.total_cases ?? 0}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Assembled via correlation</div>
        </div>
        <div className="card" style={{ padding: '16px', borderLeft: '4px solid #ef4444' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Open Cases</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: '#ef4444' }}>{stats?.cases_by_status?.['Open'] ?? 0}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Awaiting initial triage</div>
        </div>
        <div className="card" style={{ padding: '16px', borderLeft: '4px solid #f59e0b' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Under Review</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: '#f59e0b' }}>{stats?.cases_by_status?.['UnderReview'] ?? 0}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Active analyst investigation</div>
        </div>
        <div className="card" style={{ padding: '16px', borderLeft: '4px solid #3b82f6' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Needs More Evidence</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: '#3b82f6' }}>{stats?.cases_by_status?.['NeedsMoreEvidence'] ?? 0}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Pending further log data</div>
        </div>
        <div className="card" style={{ padding: '16px', borderLeft: '4px solid #10b981' }}>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Resolved</div>
          <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px', color: '#10b981' }}>{stats?.cases_by_status?.['Resolved'] ?? 0}</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Closed with decision</div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="card" style={{ padding: '16px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center' }}>
          <div style={{ flex: 1, minWidth: '220px' }}>
            <input
              type="text"
              placeholder="Search by title, case ID, or key value..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="text-input"
              style={{ width: '100%', padding: '8px 12px' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>Status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="select-input"
              style={{ padding: '8px 12px' }}
            >
              <option value="ALL">All Statuses</option>
              <option value="Open">Open</option>
              <option value="UnderReview">Under Review</option>
              <option value="NeedsMoreEvidence">Needs More Evidence</option>
              <option value="Resolved">Resolved</option>
              <option value="Dismissed">Dismissed</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>Severity:</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="select-input"
              style={{ padding: '8px 12px' }}
            >
              <option value="ALL">All Severities</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
              <option value="Info">Info</option>
            </select>
          </div>

          <button
            onClick={() => { fetchStats(); fetchCases(); }}
            className="action-button secondary"
            style={{ padding: '8px 16px' }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Cases Table */}
      <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
            <div className="spinner" style={{ margin: '0 auto 12px', width: '24px', height: '24px' }} />
            <div>Loading investigation cases...</div>
          </div>
        ) : cases.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center' }}>
            <h3 style={{ margin: '0 0 8px', fontSize: '16px' }}>No Investigation Cases Found</h3>
            <p style={{ margin: '0 0 16px', color: 'var(--color-text-secondary)', fontSize: '14px' }}>
              {statusFilter !== 'ALL' || severityFilter !== 'ALL' || searchQuery
                ? 'No cases match the selected filter criteria.'
                : 'No investigation cases have been correlated yet. Run the correlation engine to group active detection findings.'}
            </p>
            <button onClick={handleRunCorrelation} disabled={correlating} className="action-button primary">
              Run Correlation Engine
            </button>
          </div>
        ) : (
          <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-secondary)' }}>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Case ID</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Severity</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Status</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Title & Correlation Key</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Evidence</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Last Observed</th>
                <th style={{ padding: '12px 16px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr
                  key={c.case_id}
                  style={{
                    borderBottom: '1px solid var(--color-border)',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                  }}
                  onClick={() => openCaseDetail(c.case_id)}
                >
                  <td style={{ padding: '14px 16px', fontFamily: 'monospace', fontSize: '13px', fontWeight: 600 }}>
                    {c.case_id}
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <span
                      className={`badge ${getSeverityBadgeClass(c.severity)}`}
                      title={c.metadata?.severity_derivation || `Derived as ${c.severity}`}
                    >
                      {c.severity}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <span className={`status-badge ${getStatusBadgeClass(c.status)}`}>
                      {c.status}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>{c.title}</div>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                      Key: <code style={{ color: 'var(--color-accent)' }}>{c.correlation_key_type} = {c.correlation_key_value}</code>
                    </div>
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: '13px' }}>
                    <div><strong>{c.finding_count ?? 0}</strong> finding(s)</div>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}><strong>{c.event_count ?? 0}</strong> canonical event(s)</div>
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: '12px', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                    {c.last_observed_at ? new Date(c.last_observed_at).toLocaleString() : 'N/A'}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); openCaseDetail(c.case_id); }}
                      className="action-button secondary"
                      style={{ padding: '6px 12px', fontSize: '12px' }}
                    >
                      Investigate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {cases.length > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderTop: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-secondary)', fontSize: '12px' }}>
            <div style={{ color: 'var(--color-text-secondary)' }}>
              Showing {offset + 1}–{Math.min(offset + cases.length, total)} of {total} case(s)
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="action-button secondary"
                style={{ padding: '4px 10px', fontSize: '12px' }}
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                className="action-button secondary"
                style={{ padding: '4px 10px', fontSize: '12px' }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Case Investigation Drawer / Detail Modal */}
      {selectedCase && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: '850px',
            maxWidth: '100vw',
            backgroundColor: 'var(--color-bg-primary)',
            boxShadow: '-4px 0 24px rgba(0, 0, 0, 0.4)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            borderLeft: '1px solid var(--color-border)',
            overflow: 'hidden',
          }}
        >
          {/* Drawer Header */}
          <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-secondary)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <span className={`badge ${getSeverityBadgeClass(selectedCase.severity)}`}>
                    {selectedCase.severity}
                  </span>
                  <span className={`status-badge ${getStatusBadgeClass(selectedCase.status)}`}>
                    {selectedCase.status}
                  </span>
                  <span style={{ fontSize: '12px', fontFamily: 'monospace', color: 'var(--color-text-secondary)' }}>
                    {selectedCase.case_id}
                  </span>
                </div>
                <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>{selectedCase.title}</h2>
                <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                  {selectedCase.metadata?.severity_derivation || `Severity derived from linked findings.`}
                </p>
              </div>

              <button
                onClick={() => setSelectedCase(null)}
                style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: 'var(--color-text-secondary)' }}
                aria-label="Close investigation panel"
              >
                &times;
              </button>
            </div>

            {/* Operator Actions Bar */}
            <div style={{ marginTop: '16px', padding: '12px', backgroundColor: 'var(--color-bg-primary)', borderRadius: '6px', border: '1px solid var(--color-border)' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 600 }}>Transition Status:</label>
                  <select
                    value={selectedNextStatus}
                    onChange={(e) => setSelectedNextStatus(e.target.value as CaseStatus)}
                    className="select-input"
                    style={{ padding: '4px 8px', fontSize: '13px' }}
                  >
                    <option value="Open">Open</option>
                    <option value="UnderReview">Under Review</option>
                    <option value="NeedsMoreEvidence">Needs More Evidence</option>
                    <option value="Resolved">Resolved</option>
                    <option value="Dismissed">Dismissed</option>
                  </select>
                </div>

                <div style={{ flex: 1, minWidth: '200px' }}>
                  <input
                    type="text"
                    placeholder="Add operator note or decision rationale..."
                    value={operatorNote}
                    onChange={(e) => setOperatorNote(e.target.value)}
                    className="text-input"
                    style={{ width: '100%', padding: '6px 10px', fontSize: '13px' }}
                  />
                </div>

                <button
                  onClick={handleSubmitReview}
                  disabled={submittingReview}
                  className="action-button primary"
                  style={{ padding: '6px 14px', fontSize: '13px' }}
                >
                  {submittingReview ? 'Recording...' : 'Submit Action'}
                </button>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div style={{ display: 'flex', gap: '2px', marginTop: '16px', borderBottom: '1px solid var(--color-border)' }}>
              <button
                onClick={() => setActiveTab('timeline')}
                className={`tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'timeline' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'timeline' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'timeline' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Evidence Timeline ({selectedCase.timeline?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('claims')}
                className={`tab-btn ${activeTab === 'claims' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'claims' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'claims' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'claims' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Claim Guard ({selectedCase.claims?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('correlation')}
                className={`tab-btn ${activeTab === 'correlation' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'correlation' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'correlation' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'correlation' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Correlation Rationale
              </button>
              <button
                onClick={() => setActiveTab('findings')}
                className={`tab-btn ${activeTab === 'findings' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'findings' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'findings' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'findings' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Linked Findings ({selectedCase.findings?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('events')}
                className={`tab-btn ${activeTab === 'events' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'events' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'events' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'events' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Supporting Events ({selectedCase.events?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('reviews')}
                className={`tab-btn ${activeTab === 'reviews' ? 'active' : ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'reviews' ? '2px solid var(--color-accent)' : '2px solid transparent',
                  color: activeTab === 'reviews' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'reviews' ? 600 : 400,
                  fontSize: '13px',
                }}
              >
                Review Log ({selectedCase.review_actions?.length ?? 0})
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
            {/* TAB: TIMELINE */}
            {activeTab === 'timeline' && (
              <div>
                <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600 }}>Chronological Evidence Timeline</h3>
                <div style={{ position: 'relative', paddingLeft: '24px', borderLeft: '2px solid var(--color-border)' }}>
                  {selectedCase.timeline?.map((item: TimelineItem) => (
                    <div key={item.item_id} style={{ marginBottom: '20px', position: 'relative' }}>
                      {/* Bullet marker */}
                      <div
                        style={{
                          position: 'absolute',
                          left: '-31px',
                          top: '2px',
                          width: '12px',
                          height: '12px',
                          borderRadius: '50%',
                          backgroundColor:
                            item.item_type === 'finding'
                              ? '#ef4444'
                              : item.item_type === 'correlation'
                              ? 'var(--color-accent)'
                              : item.item_type === 'status_change'
                              ? '#f59e0b'
                              : item.item_type === 'review_action'
                              ? '#10b981'
                              : '#3b82f6',
                        }}
                      />
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', marginBottom: '2px' }}>
                        {item.timestamp ? new Date(item.timestamp).toLocaleString() : 'Unknown Timestamp'}
                        {' '}&bull;{' '}
                        <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                          {item.item_type.replace('_', ' ')}
                        </span>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: '14px' }}>{item.title}</div>
                      <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                        {item.description}
                      </div>

                      {/* Timeline Detail Expanders */}
                      {item.item_type === 'finding' && (
                        <button
                          onClick={() => { setSelectedFindingDetail(item.data as Finding); }}
                          style={{
                            background: 'none',
                            border: '1px solid var(--color-border)',
                            borderRadius: '4px',
                            color: 'var(--color-accent)',
                            fontSize: '11px',
                            padding: '3px 8px',
                            cursor: 'pointer',
                            marginTop: '6px',
                          }}
                        >
                          View Finding Conditions &rarr;
                        </button>
                      )}
                      {item.item_type === 'event' && (
                        <button
                          onClick={() => { setSelectedEventDetail(item.data as NormalizedEvent); }}
                          style={{
                            background: 'none',
                            border: '1px solid var(--color-border)',
                            borderRadius: '4px',
                            color: 'var(--color-accent)',
                            fontSize: '11px',
                            padding: '3px 8px',
                            cursor: 'pointer',
                            marginTop: '6px',
                          }}
                        >
                          View Event Provenance &rarr;
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* TAB: CLAIM GUARD */}
            {activeTab === 'claims' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <div>
                    <h3 style={{ margin: '0 0 4px', fontSize: '15px', fontWeight: 600 }}>Proof-Carrying Investigation: Claim Guard</h3>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                      AI proposes. Deterministic code verifies. The operator decides.
                    </div>
                  </div>
                  <button
                    onClick={() => runClaimGuardDemo(selectedCase.case_id)}
                    disabled={verifyingClaims}
                    className="primary-btn"
                    style={{
                      padding: '6px 14px',
                      fontSize: '12px',
                      background: 'var(--color-accent)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: verifyingClaims ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    {verifyingClaims ? 'Verifying Claims...' : 'Run Claim Guard Verification'}
                  </button>
                </div>

                {/* Metrics bar */}
                {selectedCase.claims && selectedCase.claims.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '16px' }}>
                    <div className="card" style={{ padding: '10px', textAlign: 'center', borderTop: '3px solid #10b981' }}>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>VERIFIED CLAIMS</div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#10b981' }}>
                        {selectedCase.claims.filter(c => c.status === 'verified').length}
                      </div>
                    </div>
                    <div className="card" style={{ padding: '10px', textAlign: 'center', borderTop: '3px solid #f59e0b' }}>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>QUALIFIED CLAIMS</div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#f59e0b' }}>
                        {selectedCase.claims.filter(c => c.status === 'qualified').length}
                      </div>
                    </div>
                    <div className="card" style={{ padding: '10px', textAlign: 'center', borderTop: '3px solid #ef4444' }}>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>BLOCKED CLAIMS</div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#ef4444' }}>
                        {selectedCase.claims.filter(c => c.status === 'blocked').length}
                      </div>
                    </div>
                    <div className="card" style={{ padding: '10px', textAlign: 'center', borderTop: '3px solid #6366f1' }}>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>VERIFIER ENGINE</div>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-primary)', marginTop: '4px' }}>
                        v1.0.0 Pure Code
                      </div>
                    </div>
                  </div>
                )}

                {/* No claims state */}
                {(!selectedCase.claims || selectedCase.claims.length === 0) && (
                  <div className="card" style={{ padding: '24px', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px', color: 'var(--color-text-primary)' }}>
                      No Claims Verified for this Case
                    </div>
                    <p style={{ margin: '0 0 16px', fontSize: '12px' }}>
                      Run deterministic Claim Guard to verify AI agent proposals against ground-truth evidence,
                      separate observed facts from inferences, and block unsupported or hallucinated statements.
                    </p>
                    <button
                      onClick={() => runClaimGuardDemo(selectedCase.case_id)}
                      disabled={verifyingClaims}
                      className="primary-btn"
                      style={{
                        padding: '8px 18px',
                        fontSize: '13px',
                        background: 'var(--color-accent)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: verifyingClaims ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {verifyingClaims ? 'Evaluating Evidence...' : 'Execute Claim Guard Verification'}
                    </button>
                  </div>
                )}

                {/* Claims list */}
                {selectedCase.claims && selectedCase.claims.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    {/* 1. Verified Claims Section */}
                    {selectedCase.claims.filter(c => c.status === 'verified').length > 0 && (
                      <div>
                        <h4 style={{ margin: '0 0 8px', fontSize: '13px', fontWeight: 600, color: '#10b981', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>●</span> Verified Factual Statements ({selectedCase.claims.filter(c => c.status === 'verified').length})
                        </h4>
                        {selectedCase.claims.filter(c => c.status === 'verified').map((claim) => (
                          <div
                            key={claim.claim_id}
                            className="card"
                            style={{
                              padding: '14px',
                              marginBottom: '8px',
                              borderLeft: '4px solid #10b981',
                              backgroundColor: 'rgba(16, 185, 129, 0.04)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                                {claim.rendered_text}
                              </span>
                              <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '3px', background: 'rgba(16, 185, 129, 0.2)', color: '#10b981', fontWeight: 600 }}>
                                VERIFIED
                              </span>
                            </div>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginTop: '6px', fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                              <span>Evidence:</span>
                              {claim.evidence_refs?.map((ref) => (
                                <code key={ref} style={{ padding: '2px 5px', background: 'var(--color-bg-secondary)', borderRadius: '3px', fontSize: '10px' }}>
                                  {ref}
                                </code>
                              ))}
                              <span>&bull;</span>
                              <span>Type: <code>{claim.claim_type || 'typed_claim'}</code></span>
                              <span>&bull;</span>
                              <span>Certainty: <strong>{claim.certainty || 'observed'}</strong></span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 2. Qualified Claims Section */}
                    {selectedCase.claims.filter(c => c.status === 'qualified').length > 0 && (
                      <div style={{ marginTop: '10px' }}>
                        <h4 style={{ margin: '0 0 8px', fontSize: '13px', fontWeight: 600, color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>▲</span> Qualified Statements with Caveats ({selectedCase.claims.filter(c => c.status === 'qualified').length})
                        </h4>
                        {selectedCase.claims.filter(c => c.status === 'qualified').map((claim) => (
                          <div
                            key={claim.claim_id}
                            className="card"
                            style={{
                              padding: '14px',
                              marginBottom: '8px',
                              borderLeft: '4px solid #f59e0b',
                              backgroundColor: 'rgba(245, 158, 11, 0.04)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                                {claim.rendered_text}
                              </span>
                              <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '3px', background: 'rgba(245, 158, 11, 0.2)', color: '#f59e0b', fontWeight: 600 }}>
                                QUALIFIED
                              </span>
                            </div>
                            {claim.qualification_notes && claim.qualification_notes.length > 0 && (
                              <div style={{ fontSize: '12px', color: '#f59e0b', marginTop: '4px', fontStyle: 'italic' }}>
                                Caveats: {claim.qualification_notes.join('; ')}
                              </div>
                            )}
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginTop: '6px', fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                              <span>Evidence:</span>
                              {claim.evidence_refs?.map((ref) => (
                                <code key={ref} style={{ padding: '2px 5px', background: 'var(--color-bg-secondary)', borderRadius: '3px', fontSize: '10px' }}>
                                  {ref}
                                </code>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 3. Blocked Claims Audit Panel */}
                    {selectedCase.claims.filter(c => c.status === 'blocked').length > 0 && (
                      <div style={{ marginTop: '10px' }}>
                        <h4 style={{ margin: '0 0 8px', fontSize: '13px', fontWeight: 600, color: '#ef4444', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>✕</span> Blocked Proposals Audit Panel ({selectedCase.claims.filter(c => c.status === 'blocked').length})
                        </h4>
                        <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>
                          These AI proposals failed deterministic evidence verification and are strictly blocked from appearing as verified investigation conclusions.
                        </div>
                        {selectedCase.claims.filter(c => c.status === 'blocked').map((claim) => (
                          <div
                            key={claim.claim_id}
                            className="card"
                            style={{
                              padding: '14px',
                              marginBottom: '8px',
                              borderLeft: '4px solid #ef4444',
                              backgroundColor: 'rgba(239, 68, 68, 0.05)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: '#ef4444' }}>
                                [BLOCKED PROPOSAL] {claim.claim_id}
                              </span>
                              <span style={{ fontSize: '10px', padding: '2px 6px', borderRadius: '3px', background: 'rgba(239, 68, 68, 0.2)', color: '#ef4444', fontWeight: 600 }}>
                                REJECTED
                              </span>
                            </div>
                            {claim.blocked_reasons && claim.blocked_reasons.length > 0 && (
                              <div style={{ fontSize: '12px', color: 'var(--color-text-primary)', marginTop: '4px' }}>
                                <strong>Rejection Reason:</strong> {claim.blocked_reasons.join('; ')}
                              </div>
                            )}
                            {claim.suggested_remedy && (
                              <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                                <strong>Required Evidence:</strong> {claim.suggested_remedy}
                              </div>
                            )}
                            <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                              Failed Checks: {claim.checks?.filter(ch => !ch.passed).map(ch => ch.name).join(', ')}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* TAB: CORRELATION RATIONALE */}
            {activeTab === 'correlation' && (
              <div>
                <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600 }}>Deterministic Correlation Rationale</h3>
                <div className="card" style={{ padding: '16px', marginBottom: '16px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '16px' }}>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Correlation Key Type</div>
                      <div style={{ fontSize: '14px', fontWeight: 600 }}>{selectedCase.correlation_key_type}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Correlation Key Value</div>
                      <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-accent)' }}>{selectedCase.correlation_key_value}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Time Window Bound</div>
                      <div style={{ fontSize: '14px', fontWeight: 600 }}>{selectedCase.metadata?.window_seconds ?? 3600} seconds</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>Algorithm Version</div>
                      <div style={{ fontSize: '14px', fontWeight: 600 }}>{selectedCase.algorithm_version}</div>
                    </div>
                  </div>

                  <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '12px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Correlation Explanation:</div>
                    <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.5' }}>
                      {selectedCase.metadata?.correlation_rationale ||
                        `These records were grouped because they share the same ${selectedCase.correlation_key_type} '${selectedCase.correlation_key_value}' and occurred within the configured correlation window.`}
                    </p>
                  </div>
                </div>

                <div className="card" style={{ padding: '16px', backgroundColor: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: '#3b82f6', marginBottom: '4px' }}>
                    Contextual Identity Principle:
                  </div>
                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: '1.5' }}>
                    In Project Sentinel, IP addresses are treated strictly as contextual telemetry and never establish identity or case grouping independently.
                    Cases are grouped only when explicit authenticated identities (normalized user IDs, session tokens, or request traces) align within bounded temporal windows.
                  </p>
                </div>
              </div>
            )}

            {/* TAB: LINKED FINDINGS */}
            {activeTab === 'findings' && (
              <div>
                <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600 }}>Linked Detection Findings</h3>
                {selectedCase.findings?.map((f: Finding) => (
                  <div key={f.finding_id} className="card" style={{ padding: '16px', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span className={`badge ${getSeverityBadgeClass(f.severity)}`}>{f.severity}</span>
                          <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>[{f.rule_id}]</span>
                          <span style={{ fontWeight: 600 }}>{f.title}</span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                          Finding ID: {f.finding_id} &bull; Entity: {f.matched_entity || 'N/A'}
                        </div>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                        {new Date(f.first_observed_at).toLocaleTimeString()}
                      </div>
                    </div>
                    <p style={{ margin: '8px 0', fontSize: '13px' }}>{f.description}</p>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-bg-secondary)', padding: '8px', borderRadius: '4px' }}>
                      <strong>Limitations:</strong> {f.limitations || 'None documented.'}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* TAB: SUPPORTING EVENTS */}
            {activeTab === 'events' && (
              <div>
                <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600 }}>Supporting Canonical Events</h3>
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-bg-secondary)' }}>
                        <th style={{ padding: '8px 12px' }}>Timestamp</th>
                        <th style={{ padding: '8px 12px' }}>Event Type</th>
                        <th style={{ padding: '8px 12px' }}>User</th>
                        <th style={{ padding: '8px 12px' }}>Source IP</th>
                        <th style={{ padding: '8px 12px' }}>Status</th>
                        <th style={{ padding: '8px 12px' }}>Source Provenance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedCase.events?.map((ev: NormalizedEvent) => (
                        <tr
                          key={ev.event_id}
                          style={{ borderBottom: '1px solid var(--color-border)', cursor: 'pointer' }}
                          onClick={() => setSelectedEventDetail(ev)}
                        >
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>{new Date(ev.timestamp).toLocaleTimeString()}</td>
                          <td style={{ padding: '8px 12px', fontWeight: 600 }}>{ev.event_type}</td>
                          <td style={{ padding: '8px 12px' }}>{ev.user_principal || 'none'}</td>
                          <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{ev.source_ip || 'none'}</td>
                          <td style={{ padding: '8px 12px' }}>
                            <span style={{ color: ev.status === 'SUCCESS' ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                              {ev.status}
                            </span>
                          </td>
                          <td style={{ padding: '8px 12px', color: 'var(--color-text-secondary)' }}>
                            {ev.source_file}:{ev.source_line}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB: REVIEWS */}
            {activeTab === 'reviews' && (
              <div>
                <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600 }}>Operator Review Actions History</h3>
                {selectedCase.review_actions && selectedCase.review_actions.length > 0 ? (
                  selectedCase.review_actions.map((ra) => (
                    <div key={ra.action_id} className="card" style={{ padding: '14px', marginBottom: '10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, fontSize: '13px' }}>
                          {ra.action_type === 'status_changed' ? (
                            <span>Status changed: <code style={{ color: '#f59e0b' }}>{ra.previous_status}</code> &rarr; <code style={{ color: '#10b981' }}>{ra.new_status}</code></span>
                          ) : (
                            <span>Operator Note</span>
                          )}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                          {new Date(ra.created_at).toLocaleString()}
                        </span>
                      </div>
                      <div style={{ fontSize: '13px', color: 'var(--color-text-primary)', marginTop: '4px' }}>
                        {ra.operator_note}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                        Author: <strong>{ra.author}</strong> &bull; Action ID: <code>{ra.action_id}</code>
                      </div>
                    </div>
                  ))
                ) : (
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '13px' }}>
                    No operator notes or review decisions recorded yet.
                  </div>
                )}
              </div>
            )}

            {/* SUB-MODAL: Detailed Finding View */}
            {selectedFindingDetail && (
              <div
                style={{
                  marginTop: '20px',
                  padding: '16px',
                  backgroundColor: 'var(--color-bg-secondary)',
                  borderRadius: '6px',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '14px' }}>Finding Detail: {selectedFindingDetail.title}</h4>
                  <button
                    onClick={() => setSelectedFindingDetail(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  >
                    &times;
                  </button>
                </div>
                <div style={{ fontSize: '12px', marginBottom: '8px' }}>
                  <strong>Rule ID:</strong> {selectedFindingDetail.rule_id} (v{selectedFindingDetail.rule_version})
                </div>
                <div style={{ fontSize: '12px', marginBottom: '8px' }}>
                  <strong>Conditions:</strong>
                  <pre style={{ backgroundColor: 'var(--color-bg-primary)', padding: '8px', borderRadius: '4px', overflowX: 'auto' }}>
                    {JSON.stringify(selectedFindingDetail.matched_conditions, null, 2)}
                  </pre>
                </div>
                {onNavigate && (
                  <div style={{ marginTop: '10px' }}>
                    <button
                      onClick={() => onNavigate('findings')}
                      className="action-button secondary"
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                    >
                      Open in Findings View &rarr;
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* SUB-MODAL: Detailed Event View */}
            {selectedEventDetail && (
              <div
                style={{
                  marginTop: '20px',
                  padding: '16px',
                  backgroundColor: 'var(--color-bg-secondary)',
                  borderRadius: '6px',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '14px' }}>Canonical Event Detail: {selectedEventDetail.event_id}</h4>
                  <button
                    onClick={() => setSelectedEventDetail(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  >
                    &times;
                  </button>
                </div>
                <div style={{ fontSize: '12px', marginBottom: '6px' }}>
                  <strong>Source File:</strong> {selectedEventDetail.source_file} (Line {selectedEventDetail.source_line})
                </div>
                <div style={{ fontSize: '12px', marginBottom: '6px' }}>
                  <strong>SHA-256:</strong> <code style={{ fontSize: '11px' }}>{selectedEventDetail.source_sha256}</code>
                </div>
                <div style={{ fontSize: '12px', marginBottom: '8px' }}>
                  <strong>Attributes:</strong>
                  <pre style={{ backgroundColor: 'var(--color-bg-primary)', padding: '8px', borderRadius: '4px', overflowX: 'auto' }}>
                    {JSON.stringify(selectedEventDetail.attributes, null, 2)}
                  </pre>
                </div>
                {onNavigate && (
                  <div style={{ marginTop: '10px' }}>
                    <button
                      onClick={() => onNavigate('events')}
                      className="action-button secondary"
                      style={{ padding: '4px 10px', fontSize: '12px' }}
                    >
                      Open in Canonical Events View &rarr;
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
