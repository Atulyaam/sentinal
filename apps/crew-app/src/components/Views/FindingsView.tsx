import React, { useState, useEffect, useCallback } from 'react';
import { Finding, DetectionStats, DetectionRule, RouteId, FindingStatus, FindingSeverity } from '../../types';
import { getApiBaseUrl } from '../../utils/apiClient';

const BACKEND_BASE_URL = getApiBaseUrl();

interface FindingsViewProps {
  onNavigate?: (route: RouteId) => void;
}

export const FindingsView: React.FC<FindingsViewProps> = ({ onNavigate }) => {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [stats, setStats] = useState<DetectionStats | null>(null);
  const [rules, setRules] = useState<DetectionRule[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [limit] = useState<number>(50);
  const [offset, setOffset] = useState<number>(0);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [ruleFilter, setRuleFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Modals & Drawers
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [showRulesModal, setShowRulesModal] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Load detection statistics
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/detection/stats`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data: DetectionStats = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch detection stats:', err);
    }
  }, []);

  // Load registered rules
  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/rules`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        setRules(data.rules || []);
      }
    } catch (err) {
      console.error('Failed to fetch rules:', err);
    }
  }, []);

  // Load findings with filters
  const fetchFindings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      if (severityFilter !== 'ALL') params.set('severity', severityFilter);
      if (statusFilter !== 'ALL') params.set('status', statusFilter);
      if (ruleFilter !== 'ALL') params.set('rule_id', ruleFilter);

      const res = await fetch(`${BACKEND_BASE_URL}/api/findings?${params.toString()}`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        let list: Finding[] = data.findings || [];
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          list = list.filter(
            (f) =>
              f.title.toLowerCase().includes(q) ||
              (f.matched_entity && f.matched_entity.toLowerCase().includes(q)) ||
              f.rule_id.toLowerCase().includes(q)
          );
        }
        setFindings(list);
        setTotal(data.total || 0);
      } else {
        setActionFeedback({ type: 'error', message: `Failed to load findings: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error loading findings';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setLoading(false);
    }
  }, [limit, offset, severityFilter, statusFilter, ruleFilter, searchQuery]);

  // Initial load
  useEffect(() => {
    fetchStats();
    fetchRules();
    fetchFindings();
  }, [fetchStats, fetchRules, fetchFindings]);

  // Trigger detection evaluation
  const handleRunDetection = async () => {
    setEvaluating(true);
    setActionFeedback(null);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/detection/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ limit_events: 5000 }),
      });
      if (res.ok) {
        const data = await res.json();
        const r = data.result;
        setActionFeedback({
          type: 'success',
          message: `Detection run completed in ${r.duration_ms}ms: ${r.findings_generated} new finding(s) generated, ${r.findings_duplicate} duplicate(s) skipped (${r.events_scanned} events scanned across ${r.rule_count} rules).`,
        });
        await fetchStats();
        await fetchFindings();
      } else {
        setActionFeedback({ type: 'error', message: `Detection run failed: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error executing detection run';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setEvaluating(false);
    }
  };

  // Inspect single finding
  const handleInspectFinding = async (findingId: string) => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/findings/${findingId}`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data: Finding = await res.json();
        setSelectedFinding(data);
      }
    } catch (err) {
      console.error('Failed to fetch finding details:', err);
    }
  };

  // Update finding status
  const handleUpdateStatus = async (findingId: string, newStatus: FindingStatus) => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/findings/${findingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        const updated: Finding = await res.json();
        setSelectedFinding(updated);
        await fetchStats();
        await fetchFindings();
        setActionFeedback({ type: 'success', message: `Finding '${findingId}' status updated to '${newStatus}'.` });
      } else {
        setActionFeedback({ type: 'error', message: `Failed to update status: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error updating status';
      setActionFeedback({ type: 'error', message: msg });
    }
  };

  // Toggle rule enabled state
  const handleToggleRule = async (ruleId: string, currentEnabled: boolean | number) => {
    const nextState = !Boolean(currentEnabled);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/rules/${ruleId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ enabled: nextState }),
      });
      if (res.ok) {
        await fetchRules();
        setActionFeedback({ type: 'success', message: `Rule '${ruleId}' ${nextState ? 'enabled' : 'disabled'} successfully.` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error toggling rule';
      setActionFeedback({ type: 'error', message: msg });
    }
  };

  const getSeverityStyle = (severity: FindingSeverity) => {
    switch (severity) {
      case 'Critical':
        return { color: '#f85149', bg: 'rgba(248, 81, 73, 0.15)', border: '#f85149' };
      case 'High':
        return { color: '#ffa657', bg: 'rgba(255, 166, 87, 0.15)', border: '#ffa657' };
      case 'Medium':
        return { color: '#d29922', bg: 'rgba(210, 153, 34, 0.15)', border: '#d29922' };
      case 'Low':
        return { color: '#58a6ff', bg: 'rgba(88, 166, 255, 0.15)', border: '#58a6ff' };
      case 'Info':
      default:
        return { color: '#8b949e', bg: 'rgba(139, 148, 158, 0.15)', border: '#30363d' };
    }
  };

  const getStatusStyle = (status: FindingStatus) => {
    switch (status) {
      case 'open':
        return { color: '#d29922', bg: 'rgba(210, 153, 34, 0.15)', border: '#d29922' };
      case 'acknowledged':
        return { color: '#58a6ff', bg: 'rgba(88, 166, 255, 0.15)', border: '#58a6ff' };
      case 'resolved':
        return { color: '#3fb950', bg: 'rgba(63, 185, 80, 0.15)', border: '#3fb950' };
      case 'dismissed':
      default:
        return { color: '#8b949e', bg: 'rgba(139, 148, 158, 0.15)', border: '#30363d' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', paddingBottom: '2rem' }}>
      {/* View Header & Action Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
            Deterministic Findings
          </h2>
          <p style={{ color: '#8b949e', fontSize: '0.875rem', marginTop: '0.25rem' }}>
            Evidence-backed security detections evaluated deterministically against canonical events.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => setShowRulesModal(true)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Rules Catalogue ({rules.length})
          </button>
          <button
            onClick={handleRunDetection}
            disabled={evaluating}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: evaluating ? '#1f6feb' : '#238636',
              border: '1px solid rgba(240, 246, 252, 0.1)',
              borderRadius: '6px',
              color: '#ffffff',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: evaluating ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {evaluating ? 'Evaluating Rules...' : 'Run Detection Engine'}
          </button>
        </div>
      </div>

      {/* Action Feedback Banner */}
      {actionFeedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            backgroundColor: actionFeedback.type === 'success' ? 'rgba(63, 185, 80, 0.15)' : 'rgba(248, 81, 73, 0.15)',
            border: `1px solid ${actionFeedback.type === 'success' ? '#2ea043' : '#f85149'}`,
            color: actionFeedback.type === 'success' ? '#3fb950' : '#f85149',
            fontSize: '0.875rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{actionFeedback.message}</span>
          <button
            onClick={() => setActionFeedback(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1.2rem' }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Metric Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ color: '#8b949e', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Total Findings
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f0f6fc', marginTop: '0.25rem' }}>
            {stats ? stats.total_findings : 0}
          </div>
          <div style={{ color: '#6e7681', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            All active & historical findings
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ color: '#8b949e', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Critical & High
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f85149', marginTop: '0.25rem' }}>
            {stats
              ? (stats.findings_by_severity['Critical'] || 0) + (stats.findings_by_severity['High'] || 0)
              : 0}
          </div>
          <div style={{ color: '#6e7681', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            Require immediate triage
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ color: '#8b949e', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Open Findings
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#d29922', marginTop: '0.25rem' }}>
            {stats ? stats.findings_by_status['open'] || 0 : 0}
          </div>
          <div style={{ color: '#6e7681', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            Pending analyst review
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ color: '#8b949e', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
            Resolved / Dismissed
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#3fb950', marginTop: '0.25rem' }}>
            {stats
              ? (stats.findings_by_status['resolved'] || 0) + (stats.findings_by_status['dismissed'] || 0)
              : 0}
          </div>
          <div style={{ color: '#6e7681', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            Closed forensic records
          </div>
        </div>
      </div>

      {/* Filter and Query Bar */}
      <div
        style={{
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: '#161b22',
          padding: '0.75rem 1rem',
          borderRadius: '6px',
          border: '1px solid #30363d',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: '#8b949e', fontWeight: 600 }}>Severity:</span>
          <select
            value={severityFilter}
            onChange={(e) => {
              setSeverityFilter(e.target.value);
              setOffset(0);
            }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
            }}
          >
            <option value="ALL">All Severities</option>
            <option value="Critical">Critical</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
            <option value="Info">Info</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: '#8b949e', fontWeight: 600 }}>Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setOffset(0);
            }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: '#8b949e', fontWeight: 600 }}>Rule:</span>
          <select
            value={ruleFilter}
            onChange={(e) => {
              setRuleFilter(e.target.value);
              setOffset(0);
            }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
            }}
          >
            <option value="ALL">All Rules</option>
            {rules.map((r) => (
              <option key={r.rule_id} value={r.rule_id}>
                {r.rule_id}
              </option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1, minWidth: '180px' }}>
          <input
            type="text"
            placeholder="Search title, entity, rule..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.25rem 0.5rem',
              fontSize: '0.8rem',
            }}
          />
        </div>

        <button
          onClick={() => fetchFindings()}
          style={{
            padding: '0.25rem 0.75rem',
            backgroundColor: '#21262d',
            border: '1px solid #30363d',
            borderRadius: '6px',
            color: '#c9d1d9',
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          Refresh
        </button>
      </div>

      {/* Findings Table */}
      <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #30363d', backgroundColor: '#0d1117', color: '#8b949e', fontSize: '0.75rem', textTransform: 'uppercase' }}>
              <th style={{ padding: '0.75rem 1rem' }}>Severity</th>
              <th style={{ padding: '0.75rem 1rem' }}>Finding Title</th>
              <th style={{ padding: '0.75rem 1rem' }}>Rule</th>
              <th style={{ padding: '0.75rem 1rem' }}>Matched Entity</th>
              <th style={{ padding: '0.75rem 1rem' }}>Status</th>
              <th style={{ padding: '0.75rem 1rem' }}>Last Observed</th>
              <th style={{ padding: '0.75rem 1rem' }}>Evidence</th>
              <th style={{ padding: '0.75rem 1rem' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: '#8b949e' }}>
                  Loading findings from SQLite...
                </td>
              </tr>
            ) : findings.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: '3rem', textAlign: 'center', color: '#8b949e' }}>
                  No security findings found. Run the detection engine or adjust active filters.
                </td>
              </tr>
            ) : (
              findings.map((f) => {
                const sev = getSeverityStyle(f.severity);
                const st = getStatusStyle(f.status);
                return (
                  <tr
                    key={f.finding_id}
                    onClick={() => handleInspectFinding(f.finding_id)}
                    style={{
                      borderBottom: '1px solid #21262d',
                      cursor: 'pointer',
                      transition: 'background-color 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#1f242c')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '9999px',
                          backgroundColor: sev.bg,
                          color: sev.color,
                          border: `1px solid ${sev.border}`,
                        }}
                      >
                        {f.severity}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: '#f0f6fc', fontWeight: 500 }}>
                      {f.title}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#58a6ff' }}>
                        {f.rule_id}
                      </span>{' '}
                      <span style={{ color: '#6e7681', fontSize: '0.75rem' }}>v{f.rule_version}</span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.8rem', color: '#c9d1d9' }}>
                      {f.matched_entity || '—'}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '9999px',
                          backgroundColor: st.bg,
                          color: st.color,
                          border: `1px solid ${st.border}`,
                          textTransform: 'capitalize',
                        }}
                      >
                        {f.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: '#8b949e', fontSize: '0.8rem', fontFamily: 'monospace' }}>
                      {f.last_observed_at}
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: '#21262d',
                          color: '#c9d1d9',
                          border: '1px solid #30363d',
                        }}
                      >
                        {f.supporting_event_ids ? f.supporting_event_ids.length : 0} event(s)
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInspectFinding(f.finding_id);
                        }}
                        style={{
                          padding: '0.2rem 0.6rem',
                          backgroundColor: '#21262d',
                          border: '1px solid #30363d',
                          borderRadius: '4px',
                          color: '#c9d1d9',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: '#8b949e' }}>
        <span>
          Showing {findings.length > 0 ? offset + 1 : 0} &ndash; {Math.min(offset + limit, total)} of {total} findings
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            style={{
              padding: '0.25rem 0.75rem',
              backgroundColor: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: offset === 0 ? '#484f58' : '#c9d1d9',
              cursor: offset === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            Previous
          </button>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            style={{
              padding: '0.25rem 0.75rem',
              backgroundColor: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: offset + limit >= total ? '#484f58' : '#c9d1d9',
              cursor: offset + limit >= total ? 'not-allowed' : 'pointer',
            }}
          >
            Next
          </button>
        </div>
      </div>

      {/* Finding Detail Modal */}
      {selectedFinding && (
        <div
          onClick={() => setSelectedFinding(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#161b22',
              border: '1px solid #30363d',
              borderRadius: '8px',
              width: '100%',
              maxWidth: '850px',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #30363d', paddingBottom: '1rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      ...getSeverityStyle(selectedFinding.severity),
                    }}
                  >
                    {selectedFinding.severity}
                  </span>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      ...getStatusStyle(selectedFinding.status),
                      textTransform: 'capitalize',
                    }}
                  >
                    {selectedFinding.status}
                  </span>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#58a6ff' }}>
                    {selectedFinding.finding_id}
                  </span>
                </div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
                  {selectedFinding.title}
                </h3>
              </div>
              <button
                onClick={() => setSelectedFinding(null)}
                style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: '1.5rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            {/* Status Update Action */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                backgroundColor: '#0d1117',
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                border: '1px solid #30363d',
              }}
            >
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#8b949e' }}>Update Status:</span>
              <select
                value={selectedFinding.status}
                onChange={(e) => handleUpdateStatus(selectedFinding.finding_id, e.target.value as FindingStatus)}
                style={{
                  backgroundColor: '#161b22',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  color: '#f0f6fc',
                  padding: '0.3rem 0.6rem',
                  fontSize: '0.8rem',
                }}
              >
                <option value="open">Open</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved</option>
                <option value="dismissed">Dismissed</option>
              </select>
              <span style={{ fontSize: '0.75rem', color: '#6e7681', marginLeft: 'auto' }}>
                Updated: {selectedFinding.updated_at || selectedFinding.created_at || 'Just now'}
              </span>
            </div>

            {/* Detection Rationale */}
            <div style={{ backgroundColor: '#0d1117', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                Detection Rationale
              </div>
              <p style={{ color: '#f0f6fc', fontSize: '0.875rem', lineHeight: 1.5, margin: 0 }}>
                {selectedFinding.description}
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', marginTop: '1rem', fontSize: '0.8rem' }}>
                <div>
                  <span style={{ color: '#8b949e' }}>Rule Definition: </span>
                  <span style={{ color: '#58a6ff', fontFamily: 'monospace' }}>
                    {selectedFinding.rule_id} (v{selectedFinding.rule_version})
                  </span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Config Hash: </span>
                  <span style={{ color: '#f0f6fc', fontFamily: 'monospace' }}>
                    {selectedFinding.rule_config_hash}
                  </span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Matched Entity: </span>
                  <span style={{ color: '#f0f6fc', fontFamily: 'monospace' }}>
                    {selectedFinding.matched_entity || 'N/A'}
                  </span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Deduplication Key: </span>
                  <div style={{ color: '#79c0ff', fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>
                    {selectedFinding.dedupe_key}
                  </div>
                </div>
              </div>
            </div>

            {/* Documented Limitations */}
            <div
              style={{
                backgroundColor: 'rgba(210, 153, 34, 0.08)',
                border: '1px solid rgba(210, 153, 34, 0.3)',
                borderRadius: '6px',
                padding: '0.75rem 1rem',
                fontSize: '0.8rem',
                color: '#d29922',
                display: 'flex',
                gap: '0.5rem',
              }}
            >
              <span>&#9888;</span>
              <div>
                <strong>Documented Rule Limitations:</strong> {selectedFinding.limitations}
              </div>
            </div>

            {/* Matched Parameters JSON */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                Matched Condition Parameters
              </div>
              <pre
                style={{
                  backgroundColor: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  padding: '1rem',
                  fontFamily: 'monospace',
                  fontSize: '0.8rem',
                  overflowX: 'auto',
                  maxHeight: '180px',
                  color: '#7ee787',
                  margin: 0,
                }}
              >
                {JSON.stringify(selectedFinding.matched_conditions, null, 2)}
              </pre>
            </div>

            {/* Supporting Events */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase' }}>
                  Supporting Canonical Events ({selectedFinding.supporting_event_ids.length})
                </div>
                {onNavigate && (
                  <button
                    onClick={() => {
                      setSelectedFinding(null);
                      onNavigate('events');
                    }}
                    style={{
                      padding: '0.2rem 0.5rem',
                      backgroundColor: '#21262d',
                      border: '1px solid #30363d',
                      borderRadius: '4px',
                      color: '#58a6ff',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                    }}
                  >
                    Open Events View &rarr;
                  </button>
                )}
              </div>

              {selectedFinding.supporting_events && selectedFinding.supporting_events.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '200px', overflowY: 'auto' }}>
                  {selectedFinding.supporting_events.map((evt) => (
                    <div
                      key={evt.event_id}
                      style={{
                        backgroundColor: '#0d1117',
                        border: '1px solid #21262d',
                        borderRadius: '6px',
                        padding: '0.6rem 0.8rem',
                        fontSize: '0.75rem',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.25rem',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontFamily: 'monospace', color: '#58a6ff' }}>{evt.event_id}</span>
                        <span style={{ color: '#8b949e', fontFamily: 'monospace' }}>{evt.timestamp}</span>
                        <span style={{ color: '#f0f6fc', fontWeight: 500 }}>{evt.event_type}</span>
                        <span style={{ color: evt.status === 'SUCCESS' ? '#3fb950' : '#f85149', fontWeight: 600 }}>
                          {evt.status}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: '1rem', color: '#8b949e' }}>
                        {evt.user_principal && <span>User: <strong style={{ color: '#c9d1d9' }}>{evt.user_principal}</strong></span>}
                        {evt.source_ip && <span>IP: <strong style={{ color: '#c9d1d9' }}>{evt.source_ip}</strong></span>}
                        {evt.target_resource && <span>Resource: <strong style={{ color: '#c9d1d9' }}>{evt.target_resource}</strong></span>}
                        <span>Source: {evt.source_file}:{evt.source_line}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {selectedFinding.supporting_event_ids.map((id) => (
                    <span
                      key={id}
                      style={{
                        fontFamily: 'monospace',
                        fontSize: '0.75rem',
                        padding: '2px 6px',
                        backgroundColor: '#0d1117',
                        border: '1px solid #30363d',
                        borderRadius: '4px',
                        color: '#79c0ff',
                      }}
                    >
                      {id}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
              <button
                onClick={() => setSelectedFinding(null)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#21262d',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  color: '#c9d1d9',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rules Catalogue Modal */}
      {showRulesModal && (
        <div
          onClick={() => setShowRulesModal(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#161b22',
              border: '1px solid #30363d',
              borderRadius: '8px',
              width: '100%',
              maxWidth: '850px',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #30363d', paddingBottom: '1rem' }}>
              <div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
                  Detection Rules Catalogue
                </h3>
                <p style={{ color: '#8b949e', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                  Deterministic, versioned rules loaded from the Sentinel rules registry.
                </p>
              </div>
              <button
                onClick={() => setShowRulesModal(false)}
                style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: '1.5rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {rules.map((rule) => {
                const sev = getSeverityStyle(rule.severity);
                return (
                  <div
                    key={rule.rule_id}
                    style={{
                      backgroundColor: '#0d1117',
                      border: '1px solid #30363d',
                      borderRadius: '6px',
                      padding: '1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.75rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#f0f6fc', fontSize: '1rem' }}>
                          {rule.rule_id}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: '#8b949e', border: '1px solid #30363d', padding: '2px 6px', borderRadius: '4px' }}>
                          v{rule.version}
                        </span>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: '9999px',
                            backgroundColor: sev.bg,
                            color: sev.color,
                            border: `1px solid ${sev.border}`,
                          }}
                        >
                          {rule.severity}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={Boolean(rule.enabled)}
                            onChange={() => handleToggleRule(rule.rule_id, rule.enabled)}
                          />
                          <span style={{ fontSize: '0.8rem', color: rule.enabled ? '#3fb950' : '#8b949e' }}>
                            {rule.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </label>
                      </div>
                    </div>

                    <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
                      {rule.name}
                    </h4>
                    <p style={{ color: '#8b949e', fontSize: '0.825rem', lineHeight: 1.4, margin: 0 }}>
                      {rule.description}
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem', fontSize: '0.75rem' }}>
                      <div>
                        <span style={{ color: '#8b949e' }}>Config Hash: </span>
                        <span style={{ fontFamily: 'monospace', color: '#c9d1d9' }}>{rule.config_hash}</span>
                      </div>
                      <div>
                        <span style={{ color: '#8b949e' }}>Limitations: </span>
                        <span style={{ color: '#8b949e' }}>{rule.limitations || 'None documented'}</span>
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '0.75rem', color: '#8b949e', fontWeight: 600 }}>Parameters:</span>
                      <pre
                        style={{
                          backgroundColor: '#161b22',
                          border: '1px solid #21262d',
                          borderRadius: '4px',
                          padding: '0.5rem',
                          fontFamily: 'monospace',
                          fontSize: '0.75rem',
                          color: '#7ee787',
                          margin: '0.25rem 0 0 0',
                          overflowX: 'auto',
                        }}
                      >
                        {JSON.stringify(rule.config, null, 2)}
                      </pre>
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
              <button
                onClick={() => setShowRulesModal(false)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#21262d',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  color: '#c9d1d9',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
