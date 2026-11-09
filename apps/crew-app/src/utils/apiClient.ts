/**
 * Project Sentinel API Client Utilities
 * Provides resilient, production-ready API base URL resolution.
 */

export const getApiBaseUrl = (): string => {
  // 1. Explicit environment variable override
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL.replace(/\/+$/, '');
  }

  // 2. Browser runtime auto-detection
  if (typeof window !== 'undefined' && window.location) {
    const port = window.location.port;
    // When running in local Vite development/preview mode, default to backend port 8000
    if (port === '5173' || port === '4173') {
      return 'http://127.0.0.1:8000';
    }
    // In production or unified container deployment, use relative paths (same origin)
    return '';
  }

  // 3. Fallback for test/build environments
  return 'http://127.0.0.1:8000';
};

