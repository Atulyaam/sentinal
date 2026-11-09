import React, { useState, useEffect, useCallback } from 'react';
import { EventSource, ImportJob, ImportResult, ParserProfile } from '../../types';
import { SourcesIcon, RefreshIcon } from '../Icons';
import { getApiBaseUrl } from '../../utils/apiClient';

const BACKEND_BASE_URL = getApiBaseUrl();

export const SourcesView: React.FC = () => {
  const [sources, setSources] = useState<EventSource[]>([]);
  const [parsers, setParsers] = useState<ParserProfile[]>([]);
  const [imports, setImports] = useState<ImportJob[]>([]);
  const [selectedParser, setSelectedParser] = useState<string>('generic_jsonl');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadResult, setUploadResult] = useState<ImportResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState<ImportJob | null>(null);
  const [isDemoMode, setIsDemoMode] = useState<boolean>(false);

  const fetchEndpoint = async (path: string) => {
    // 1. Try relative URL first
    try {
      const res = await fetch(path, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch {
      // Fallback
    }
    // 2. Direct backend base URL
    const directRes = await fetch(`${BACKEND_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!directRes.ok) {
      throw new Error(`HTTP ${directRes.status} ${directRes.statusText}`);
    }
    return await directRes.json();
  };

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [sourcesData, parsersData, importsData, healthData] = await Promise.all([
        fetchEndpoint('/api/sources').catch(() => ({ sources: [] })),
        fetchEndpoint('/api/parsers').catch(() => ({ parsers: [] })),
        fetchEndpoint('/api/imports').catch(() => ({ imports: [] })),
        fetchEndpoint('/health').catch(() => null),
      ]);

      setSources(sourcesData.sources || []);
      setParsers(parsersData.parsers || []);
      setImports(importsData.imports || []);
      if (healthData && healthData.demo_mode) {
        setIsDemoMode(true);
      }
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to connect to backend service.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
      setUploadResult(null);
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadResult(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('parser_id', selectedParser);
      formData.append('source_id', 'src_manual_default');

      let response: Response;
      try {
        response = await fetch('/api/import', {
          method: 'POST',
          body: formData,
        });
        if (!response.ok && response.status === 404) {
          // Fall back to direct backend URL
          response = await fetch(`${BACKEND_BASE_URL}/api/import`, {
            method: 'POST',
            body: formData,
          });
        }
      } catch {
        response = await fetch(`${BACKEND_BASE_URL}/api/import`, {
          method: 'POST',
          body: formData,
        });
      }

      const result: ImportResult = await response.json();
      setUploadResult(result);

      // Re-fetch historical imports table on completion
      await loadData();
    } catch (err: unknown) {
      setUploadResult({
        status: 'rejected',
        duplicate: false,
        error: err instanceof Error ? err.message : 'Upload transmission failed',
      });
    } finally {
      setIsUploading(false);
    }
  };

  const viewJobDetails = async (importId: string) => {
    try {
      const details = await fetchEndpoint(`/api/imports/${importId}`);
      setSelectedJobDetails(details);
    } catch (err: unknown) {
      alert(`Failed to load details for ${importId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Overview & Action Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: 'var(--color-accent)' }}><SourcesIcon size={20} /></span>
            Data Ingestion &amp; Event Sources
          </h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '13px', marginTop: '4px' }}>
            Operator-approved inboxes, deterministic parsing profiles, SHA-256 idempotency, and SQLite persistence.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={isLoading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 14px',
            borderRadius: '6px',
            backgroundColor: 'var(--color-bg-subtle)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
            fontSize: '13px',
            cursor: isLoading ? 'not-allowed' : 'pointer',
          }}
        >
          <RefreshIcon size={14} className={isLoading ? 'spin' : ''} />
          {isLoading ? 'Refreshing...' : 'Refresh Sources'}
        </button>
      </div>

      {/* Demo Mode Notice */}
      {isDemoMode && (
        <div
          style={{
            background: 'rgba(30, 58, 138, 0.15)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            borderRadius: '6px',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div>
            <strong style={{ color: '#38bdf8', fontSize: '13px' }}>Public Demo Mode Active</strong>
            <p style={{ color: '#cbd5e1', fontSize: '12px', margin: '4px 0 0 0', lineHeight: 1.5 }}>
              Manual log upload and arbitrary directory scanning are disabled for public security. All pipeline stages (ingestion, normalization, detection, correlation, and Claim Guard) can be safely executed using the <strong>Replay Lab</strong> synthetic scenarios.
            </p>
          </div>
        </div>
      )}

      {errorMessage && (
        <div style={{
          backgroundColor: 'var(--color-danger-bg)',
          border: '1px solid var(--color-danger)',
          color: 'var(--color-danger)',
          padding: '12px 16px',
          borderRadius: '6px',
          fontSize: '13px',
        }}>
          Backend Connection Warning: {errorMessage}
        </div>
      )}

      {/* Grid: Configured Sources & Manual Ingestion */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Card 1: Configured Sources & Approved Inbox */}
        <div className="sentinel-card">
          <h2 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px' }}>Configured Event Sources</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {sources.length === 0 ? (
              <div style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
                {isLoading ? 'Loading sources...' : 'No event sources registered.'}
              </div>
            ) : (
              sources.map((src) => (
                <div
                  key={src.source_id}
                  style={{
                    padding: '12px',
                    borderRadius: '6px',
                    backgroundColor: 'var(--color-bg-subtle)',
                    border: '1px solid var(--color-border)',
                    fontSize: '13px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{src.source_name}</span>
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      backgroundColor: src.enabled ? 'var(--color-success-bg)' : 'var(--color-danger-bg)',
                      color: src.enabled ? 'var(--color-success)' : 'var(--color-danger)',
                      fontWeight: 600,
                    }}>
                      {src.enabled ? 'ACTIVE' : 'DISABLED'}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px', fontFamily: 'var(--font-mono)' }}>
                    ID: {src.source_id} | Parser: {src.parser_profile}
                  </div>
                  {src.configured_path && (
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                      Path: <code>{src.configured_path}</code> (Non-recursive polling)
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Card 2: Manual Log File Import */}
        <div className="sentinel-card">
          <h2 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>Manual Log Import</h2>
          <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
            Upload a local file for immediate validation, pre-persistence redaction, and SHA-256 deduplication.
          </p>

          <form onSubmit={handleImportSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px', color: 'var(--color-text-secondary)' }}>
                Target Parser Profile
              </label>
              <select
                value={selectedParser}
                onChange={(e) => setSelectedParser(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  fontSize: '13px',
                }}
              >
                {parsers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.id})
                  </option>
                ))}
              </select>
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                {parsers.find((p) => p.id === selectedParser)?.description}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px', color: 'var(--color-text-secondary)' }}>
                Log File (Max 20 MB)
              </label>
              <input
                type="file"
                onChange={handleFileChange}
                accept=".jsonl,.json,.csv,.log,.txt"
                style={{
                  width: '100%',
                  padding: '8px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  fontSize: '12px',
                }}
              />
              {selectedFile && (
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                  Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={isDemoMode || !selectedFile || isUploading}
              style={{
                marginTop: '4px',
                padding: '10px 16px',
                borderRadius: '6px',
                backgroundColor: isDemoMode || !selectedFile || isUploading ? 'var(--color-border)' : 'var(--color-accent)',
                color: '#ffffff',
                border: 'none',
                fontWeight: 600,
                fontSize: '13px',
                cursor: isDemoMode || !selectedFile || isUploading ? 'not-allowed' : 'pointer',
                transition: 'background-color 0.15s ease',
              }}
            >
              {isDemoMode ? 'Upload Disabled in Public Demo Mode' : isUploading ? 'Validating & Ingesting...' : 'Ingest Log File'}
            </button>
          </form>

          {/* Upload Result Feedback */}
          {uploadResult && (
            <div style={{
              marginTop: '16px',
              padding: '12px',
              borderRadius: '6px',
              backgroundColor: uploadResult.duplicate
                ? 'var(--color-accent-subtle)'
                : uploadResult.status === 'completed'
                ? 'var(--color-success-bg)'
                : uploadResult.status === 'partial'
                ? 'var(--color-warning-bg)'
                : 'var(--color-danger-bg)',
              border: `1px solid ${
                uploadResult.duplicate
                  ? 'var(--color-accent)'
                  : uploadResult.status === 'completed'
                  ? 'var(--color-success)'
                  : uploadResult.status === 'partial'
                  ? 'var(--color-warning)'
                  : 'var(--color-danger)'
              }`,
              fontSize: '12px',
            }}>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                {uploadResult.duplicate
                  ? 'Duplicate Skipped (Idempotency Guard)'
                  : `Import Status: ${uploadResult.status.toUpperCase()}`}
              </div>
              {uploadResult.message && <div style={{ marginBottom: '6px' }}>{uploadResult.message}</div>}
              {uploadResult.error && <div style={{ color: 'var(--color-danger)' }}>{uploadResult.error}</div>}

              {uploadResult.sha256 && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--color-text-muted)', wordBreak: 'break-all' }}>
                  SHA-256: {uploadResult.sha256}
                </div>
              )}

              {uploadResult.total_records !== undefined && (
                <div style={{ marginTop: '6px', display: 'flex', gap: '16px', fontSize: '12px' }}>
                  <span>Total: <strong>{uploadResult.total_records}</strong></span>
                  <span style={{ color: 'var(--color-success)' }}>Accepted: <strong>{uploadResult.accepted_records}</strong></span>
                  <span style={{ color: uploadResult.rejected_records ? 'var(--color-danger)' : 'inherit' }}>
                    Rejected: <strong>{uploadResult.rejected_records}</strong>
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Section 3: Genuine Import History Table */}
      <div className="sentinel-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '15px', fontWeight: 600 }}>Persisted Import History</h2>
            <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
              Immutable audit ledger of ingested log files stored in SQLite. Zero fabricated metrics.
            </p>
          </div>
          <span style={{ fontSize: '12px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
            Total Jobs: {imports.length}
          </span>
        </div>

        {imports.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '40px 20px',
            backgroundColor: 'var(--color-bg-subtle)',
            borderRadius: '6px',
            border: '1px dashed var(--color-border)',
            color: 'var(--color-text-muted)',
            fontSize: '13px',
          }}>
            No log files have been imported yet. Select a file above and click &quot;Ingest Log File&quot; to begin.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}>
                  <th style={{ padding: '8px 12px' }}>Started At</th>
                  <th style={{ padding: '8px 12px' }}>Filename</th>
                  <th style={{ padding: '8px 12px' }}>Parser Profile</th>
                  <th style={{ padding: '8px 12px' }}>Status</th>
                  <th style={{ padding: '8px 12px' }}>Accepted / Total</th>
                  <th style={{ padding: '8px 12px' }}>SHA-256</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Diagnostics</th>
                </tr>
              </thead>
              <tbody>
                {imports.map((job) => (
                  <tr key={job.import_id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap', color: 'var(--color-text-secondary)' }}>
                      {new Date(job.started_at).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px', fontWeight: 500 }}>
                      {job.filename}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>
                      {job.parser_id}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        backgroundColor:
                          job.status === 'completed'
                            ? 'var(--color-success-bg)'
                            : job.status === 'partial'
                            ? 'var(--color-warning-bg)'
                            : 'var(--color-danger-bg)',
                        color:
                          job.status === 'completed'
                            ? 'var(--color-success)'
                            : job.status === 'partial'
                            ? 'var(--color-warning)'
                            : 'var(--color-danger)',
                      }}>
                        {job.status}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>{job.accepted_records}</span>
                      <span style={{ color: 'var(--color-text-muted)' }}> / {job.total_records}</span>
                      {job.rejected_records > 0 && (
                        <span style={{ color: 'var(--color-danger)', marginLeft: '6px' }}>
                          ({job.rejected_records} rejected)
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px' }} title={job.sha256}>
                      {job.sha256.substring(0, 12)}...
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <button
                        onClick={() => viewJobDetails(job.import_id)}
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'var(--color-bg-subtle)',
                          border: '1px solid var(--color-border)',
                          color: 'var(--color-text-primary)',
                          fontSize: '11px',
                          cursor: 'pointer',
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Diagnostics Modal for Inspecting Job Errors */}
      {selectedJobDetails && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: 'var(--color-bg-panel)',
            border: '1px solid var(--color-border)',
            borderRadius: '8px',
            maxWidth: '700px',
            width: '100%',
            maxHeight: '80vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--color-border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <div>
                <h3 style={{ fontSize: '15px', fontWeight: 600 }}>
                  Import Diagnostics — {selectedJobDetails.filename}
                </h3>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                  ID: {selectedJobDetails.import_id}
                </div>
              </div>
              <button
                onClick={() => setSelectedJobDetails(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--color-text-muted)',
                  fontSize: '18px',
                  cursor: 'pointer',
                }}
              >
                &times;
              </button>
            </div>

            <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                <div style={{ padding: '10px', backgroundColor: 'var(--color-bg-subtle)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Status</div>
                  <div style={{ fontWeight: 600, marginTop: '2px' }}>{selectedJobDetails.status.toUpperCase()}</div>
                </div>
                <div style={{ padding: '10px', backgroundColor: 'var(--color-bg-subtle)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Accepted Records</div>
                  <div style={{ fontWeight: 600, color: 'var(--color-success)', marginTop: '2px' }}>
                    {selectedJobDetails.accepted_records}
                  </div>
                </div>
                <div style={{ padding: '10px', backgroundColor: 'var(--color-bg-subtle)', borderRadius: '6px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Rejected Records</div>
                  <div style={{ fontWeight: 600, color: selectedJobDetails.rejected_records ? 'var(--color-danger)' : 'inherit', marginTop: '2px' }}>
                    {selectedJobDetails.rejected_records}
                  </div>
                </div>
              </div>

              <div>
                <h4 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px' }}>
                  Validation Errors ({selectedJobDetails.errors?.length || 0})
                </h4>
                {(!selectedJobDetails.errors || selectedJobDetails.errors.length === 0) ? (
                  <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    No parsing or validation errors were recorded for this import.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {selectedJobDetails.errors.map((err) => (
                      <div
                        key={err.error_id}
                        style={{
                          padding: '10px',
                          backgroundColor: 'var(--color-danger-bg)',
                          border: '1px solid var(--color-danger)',
                          borderRadius: '6px',
                          fontSize: '12px',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: 'var(--color-danger)', display: 'flex', justifyContent: 'space-between' }}>
                          <span>Line / Row {err.record_number}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>{err.error_code}</span>
                        </div>
                        <div style={{ marginTop: '4px', color: 'var(--color-text-primary)' }}>
                          {err.safe_error_message}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div style={{
              padding: '12px 20px',
              borderTop: '1px solid var(--color-border)',
              display: 'flex',
              justifyContent: 'flex-end',
            }}>
              <button
                onClick={() => setSelectedJobDetails(null)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  fontSize: '12px',
                  cursor: 'pointer',
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

