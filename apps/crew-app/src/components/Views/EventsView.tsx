import React, { useState, useEffect, useCallback } from 'react';
import { NormalizedEvent, NormalizationStats, NormalizationRunResult, RouteId } from '../../types';

const BACKEND_BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

interface EventsViewProps {
  onNavigate?: (route: RouteId) => void;
}

export const EventsView: React.FC<EventsViewProps> = ({ onNavigate }) => {
  const [events, setEvents] = useState<NormalizedEvent[]>([]);
  const [stats, setStats] = useState<NormalizationStats | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [limit] = useState<number>(50);
  const [offset, setOffset] = useState<number>(0);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('');
  const [userFilter, setUserFilter] = useState<string>('');

  // Interaction & Details Drawer
  const [selectedEvent, setSelectedEvent] = useState<NormalizedEvent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [normalizing, setNormalizing] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Load stats
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/normalization/stats`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data: NormalizationStats = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch normalization stats:', err);
    }
  }, []);

  // Load events
  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      if (statusFilter !== 'ALL') params.set('status', statusFilter);
      if (eventTypeFilter.trim()) params.set('event_type', eventTypeFilter.trim());
      if (userFilter.trim()) params.set('user_principal', userFilter.trim());

      const res = await fetch(`${BACKEND_BASE_URL}/api/events?${params.toString()}`, {
        headers: { Accept: 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
        setTotal(data.total || 0);
      } else {
        setActionFeedback({ type: 'error', message: `Failed to load events: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error loading events';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setLoading(false);
    }
  }, [limit, offset, statusFilter, eventTypeFilter, userFilter]);

  // Initial load
  useEffect(() => {
    fetchStats();
    fetchEvents();
  }, [fetchStats, fetchEvents]);

  // Trigger manual normalization batch
  const handleRunNormalization = async () => {
    setNormalizing(true);
    setActionFeedback(null);
    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/normalization/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ limit: 500 }),
      });
      if (res.ok) {
        const data = await res.json();
        const result: NormalizationRunResult = data.result;
        setActionFeedback({
          type: 'success',
          message: `Normalization batch finished: ${result.accepted} accepted, ${result.rejected} rejected, ${result.skipped} skipped.`,
        });
        await fetchStats();
        await fetchEvents();
      } else {
        setActionFeedback({ type: 'error', message: `Normalization run failed: HTTP ${res.status}` });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Normalization request failed';
      setActionFeedback({ type: 'error', message: msg });
    } finally {
      setNormalizing(false);
    }
  };

  return (
    <div className="events-container" style={{ padding: '1.5rem', color: '#c9d1d9' }}>
      {/* View Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
            Canonical Events & Provenance
          </h1>
          <p style={{ margin: '0.25rem 0 0 0', color: '#8b949e', fontSize: '0.875rem' }}>
            Deterministically normalized security events conforming to NormalizedEventContract with immutable SHA-256 provenance.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => { fetchStats(); fetchEvents(); }}
            disabled={loading || normalizing}
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
            Refresh
          </button>
          <button
            onClick={handleRunNormalization}
            disabled={normalizing}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: normalizing ? '#238636aa' : '#238636',
              border: '1px solid #2ea043',
              borderRadius: '6px',
              color: '#ffffff',
              fontWeight: 500,
              cursor: normalizing ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {normalizing ? 'Normalizing...' : 'Run Normalization'}
          </button>
        </div>
      </div>

      {/* Action / Notification Banner */}
      {actionFeedback && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            marginBottom: '1rem',
            fontSize: '0.875rem',
            backgroundColor: actionFeedback.type === 'success' ? '#1f3526' : '#3d1f24',
            border: `1px solid ${actionFeedback.type === 'success' ? '#2ea043' : '#f85149'}`,
            color: actionFeedback.type === 'success' ? '#3fb950' : '#f85149',
          }}
        >
          {actionFeedback.message}
        </div>
      )}

      {/* Aggregate Metrics Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Normalized Events
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: '#58a6ff', marginTop: '0.25rem' }}>
            {stats ? stats.total_normalized_events.toLocaleString() : '—'}
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Pending Unnormalized
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: stats && stats.pending_unnormalized_records > 0 ? '#d29922' : '#8b949e', marginTop: '0.25rem' }}>
            {stats ? stats.pending_unnormalized_records.toLocaleString() : '—'}
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Normalization Errors
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: stats && stats.total_normalization_errors > 0 ? '#f85149' : '#3fb950', marginTop: '0.25rem' }}>
            {stats ? stats.total_normalization_errors.toLocaleString() : '—'}
          </div>
        </div>

        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Event Types Observed
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: '#f0f6fc', marginTop: '0.25rem' }}>
            {stats ? Object.keys(stats.events_by_type).length : '—'}
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.75rem',
          backgroundColor: '#161b22',
          border: '1px solid #30363d',
          borderRadius: '6px',
          padding: '0.75rem',
          marginBottom: '1rem',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: '#8b949e' }}>Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.35rem 0.6rem',
              fontSize: '0.875rem',
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILURE">FAILURE</option>
            <option value="ERROR">ERROR</option>
            <option value="UNKNOWN">UNKNOWN</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: '#8b949e' }}>Event Type:</label>
          <input
            type="text"
            placeholder="e.g. user_authentication"
            value={eventTypeFilter}
            onChange={(e) => { setEventTypeFilter(e.target.value); setOffset(0); }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.35rem 0.6rem',
              fontSize: '0.875rem',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label style={{ fontSize: '0.8rem', color: '#8b949e' }}>Principal:</label>
          <input
            type="text"
            placeholder="Filter by username/principal"
            value={userFilter}
            onChange={(e) => { setUserFilter(e.target.value); setOffset(0); }}
            style={{
              backgroundColor: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: '#c9d1d9',
              padding: '0.35rem 0.6rem',
              fontSize: '0.875rem',
            }}
          />
        </div>

        {(statusFilter !== 'ALL' || eventTypeFilter || userFilter) && (
          <button
            onClick={() => { setStatusFilter('ALL'); setEventTypeFilter(''); setUserFilter(''); setOffset(0); }}
            style={{
              background: 'none',
              border: 'none',
              color: '#58a6ff',
              cursor: 'pointer',
              fontSize: '0.8rem',
              textDecoration: 'underline',
              padding: '0.35rem 0.5rem',
            }}
          >
            Clear Filters
          </button>
        )}

        <div style={{ marginLeft: 'auto', fontSize: '0.8rem', color: '#8b949e' }}>
          Showing {events.length} of {total} matches
        </div>
      </div>

      {/* Events Table */}
      <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', borderRadius: '6px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #30363d', backgroundColor: '#0d1117', color: '#8b949e' }}>
              <th style={{ padding: '0.75rem 1rem' }}>Timestamp (UTC)</th>
              <th style={{ padding: '0.75rem 1rem' }}>Status</th>
              <th style={{ padding: '0.75rem 1rem' }}>Event Type</th>
              <th style={{ padding: '0.75rem 1rem' }}>Principal</th>
              <th style={{ padding: '0.75rem 1rem' }}>Source IP</th>
              <th style={{ padding: '0.75rem 1rem' }}>Target Resource</th>
              <th style={{ padding: '0.75rem 1rem' }}>Source Provenance</th>
              <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} style={{ padding: '3rem 1rem', textAlign: 'center', color: '#8b949e' }}>
                  Loading normalized canonical events...
                </td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: '3rem 1rem', textAlign: 'center', color: '#8b949e' }}>
                  <div style={{ marginBottom: '0.5rem', fontSize: '1rem', color: '#f0f6fc' }}>
                    No normalized events match the current criteria.
                  </div>
                  <div style={{ fontSize: '0.875rem' }}>
                    {stats && stats.pending_unnormalized_records > 0 ? (
                      <div>
                        There are {stats.pending_unnormalized_records} pending records.{' '}
                        <button
                          onClick={handleRunNormalization}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#58a6ff',
                            cursor: 'pointer',
                            textDecoration: 'underline',
                          }}
                        >
                          Run Normalization
                        </button>
                      </div>
                    ) : (
                      <div>
                        Import log files from the{' '}
                        {onNavigate && (
                          <button
                            onClick={() => onNavigate('sources')}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: '#58a6ff',
                              cursor: 'pointer',
                              textDecoration: 'underline',
                            }}
                          >
                            Sources view
                          </button>
                        )}{' '}
                        to populate the pipeline.
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              events.map((evt) => (
                <tr
                  key={evt.event_id}
                  onClick={() => setSelectedEvent(evt)}
                  style={{
                    borderBottom: '1px solid #21262d',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#21262d')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <td style={{ padding: '0.75rem 1rem', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                    {evt.timestamp}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    <span
                      style={{
                        padding: '0.2rem 0.5rem',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor:
                          evt.status === 'SUCCESS' ? '#1f3526' : evt.status === 'FAILURE' ? '#3d1f24' : '#2d2218',
                        color:
                          evt.status === 'SUCCESS' ? '#3fb950' : evt.status === 'FAILURE' ? '#f85149' : '#d29922',
                        border: `1px solid ${evt.status === 'SUCCESS' ? '#2ea043' : evt.status === 'FAILURE' ? '#f85149' : '#bb8009'}`,
                      }}
                    >
                      {evt.status}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 1rem', color: '#f0f6fc', fontWeight: 500 }}>
                    {evt.event_type}
                  </td>
                  <td style={{ padding: '0.75rem 1rem' }}>
                    {evt.user_principal ? (
                      <span style={{ color: '#58a6ff', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        {evt.user_principal}
                      </span>
                    ) : (
                      <span style={{ color: '#6e7681' }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                    {evt.source_ip || <span style={{ color: '#6e7681' }}>—</span>}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {evt.target_resource ? (
                      <span title={evt.target_resource}>{evt.target_resource}</span>
                    ) : (
                      <span style={{ color: '#6e7681' }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', fontSize: '0.8rem', color: '#8b949e', whiteSpace: 'nowrap' }}>
                    {evt.source_file}:{evt.source_line}
                  </td>
                  <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEvent(evt);
                      }}
                      style={{
                        padding: '0.25rem 0.5rem',
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {total > limit && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: offset === 0 ? '#6e7681' : '#c9d1d9',
              cursor: offset === 0 ? 'not-allowed' : 'pointer',
              fontSize: '0.8rem',
            }}
          >
            Previous
          </button>
          <span style={{ fontSize: '0.8rem', color: '#8b949e' }}>
            Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)}
          </span>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '6px',
              color: offset + limit >= total ? '#6e7681' : '#c9d1d9',
              cursor: offset + limit >= total ? 'not-allowed' : 'pointer',
              fontSize: '0.8rem',
            }}
          >
            Next
          </button>
        </div>
      )}

      {/* Event Details & Provenance Modal / Drawer */}
      {selectedEvent && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 1000,
            padding: '1.5rem',
          }}
          onClick={() => setSelectedEvent(null)}
        >
          <div
            style={{
              backgroundColor: '#161b22',
              border: '1px solid #30363d',
              borderRadius: '8px',
              width: '100%',
              maxWidth: '750px',
              maxHeight: '90vh',
              overflowY: 'auto',
              padding: '1.5rem',
              color: '#c9d1d9',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f0f6fc', margin: 0 }}>
                    Event Inspector
                  </h2>
                  <span
                    style={{
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      backgroundColor:
                        selectedEvent.status === 'SUCCESS'
                          ? '#1f3526'
                          : selectedEvent.status === 'FAILURE'
                          ? '#3d1f24'
                          : '#2d2218',
                      color:
                        selectedEvent.status === 'SUCCESS'
                          ? '#3fb950'
                          : selectedEvent.status === 'FAILURE'
                          ? '#f85149'
                          : '#d29922',
                      border: `1px solid ${
                        selectedEvent.status === 'SUCCESS'
                          ? '#2ea043'
                          : selectedEvent.status === 'FAILURE'
                          ? '#f85149'
                          : '#bb8009'
                      }`,
                    }}
                  >
                    {selectedEvent.status}
                  </span>
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#58a6ff', marginTop: '0.25rem' }}>
                  {selectedEvent.event_id}
                </div>
              </div>

              <button
                onClick={() => setSelectedEvent(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#8b949e',
                  fontSize: '1.5rem',
                  cursor: 'pointer',
                  padding: '0 0.5rem',
                }}
              >
                ×
              </button>
            </div>

            {/* Provenance Card */}
            <div style={{ backgroundColor: '#0d1117', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem', marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                Immutable Source Provenance
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', fontSize: '0.8rem' }}>
                <div>
                  <span style={{ color: '#8b949e' }}>Source File: </span>
                  <span style={{ color: '#f0f6fc' }}>{selectedEvent.source_file}</span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Physical Line: </span>
                  <span style={{ color: '#f0f6fc' }}>Row {selectedEvent.source_line}</span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Source Format: </span>
                  <span style={{ color: '#f0f6fc' }}>{selectedEvent.source_type}</span>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Normalizer: </span>
                  <span style={{ color: '#f0f6fc' }}>v{selectedEvent.normalization_version || '1.0.0'}</span>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <span style={{ color: '#8b949e' }}>Source SHA-256: </span>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#79c0ff', wordBreak: 'break-all', marginTop: '0.2rem' }}>
                    {selectedEvent.source_sha256}
                  </div>
                </div>
              </div>
            </div>

            {/* Canonical Context */}
            <div style={{ backgroundColor: '#0d1117', border: '1px solid #30363d', borderRadius: '6px', padding: '1rem', marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                Canonical Context
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', fontSize: '0.8rem' }}>
                <div>
                  <span style={{ color: '#8b949e' }}>Normalized Timestamp: </span>
                  <div style={{ fontFamily: 'monospace', color: '#f0f6fc', marginTop: '0.1rem' }}>{selectedEvent.timestamp}</div>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Event Classification: </span>
                  <div style={{ color: '#f0f6fc', fontWeight: 500, marginTop: '0.1rem' }}>{selectedEvent.event_type}</div>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>User Principal: </span>
                  <div style={{ color: selectedEvent.user_principal ? '#58a6ff' : '#6e7681', fontFamily: 'monospace', marginTop: '0.1rem' }}>
                    {selectedEvent.user_principal || 'Unspecified'}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#8b949e' }}>Source IP: </span>
                  <div style={{ color: selectedEvent.source_ip ? '#f0f6fc' : '#6e7681', fontFamily: 'monospace', marginTop: '0.1rem' }}>
                    {selectedEvent.source_ip || 'Unspecified'}
                  </div>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <span style={{ color: '#8b949e' }}>Target Resource: </span>
                  <div style={{ color: selectedEvent.target_resource ? '#f0f6fc' : '#6e7681', fontFamily: 'monospace', marginTop: '0.1rem' }}>
                    {selectedEvent.target_resource || 'None recorded'}
                  </div>
                </div>
              </div>
            </div>

            {/* Structured Attributes Viewer */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8b949e', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                Event Attributes & Scoped Metadata
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
                  maxHeight: '220px',
                  color: '#7ee787',
                  margin: 0,
                }}
              >
                {JSON.stringify(selectedEvent.attributes, null, 2)}
              </pre>
            </div>

            {/* Modal Footer */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
              <button
                onClick={() => setSelectedEvent(null)}
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
