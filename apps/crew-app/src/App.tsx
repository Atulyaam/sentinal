import React, { useState, useEffect, useCallback } from 'react';
import { RouteId, BackendHealthState, BackendHealthResponse } from './types';
import { Navigation, ROUTES } from './components/Navigation';
import { Header } from './components/Header';
import { OverviewView } from './components/Views/OverviewView';
import { SourcesView } from './components/Views/SourcesView';
import { EventsView } from './components/Views/EventsView';
import { FindingsView } from './components/Views/FindingsView';
import { PlannedView } from './components/Views/PlannedView';

const BACKEND_BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const getInitialRoute = (): RouteId => {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const viewParam = params.get('view') as RouteId;
    if (viewParam && ROUTES.some((r) => r.id === viewParam)) {
      return viewParam;
    }
    const hash = window.location.hash.replace('#', '') as RouteId;
    if (hash && ROUTES.some((r) => r.id === hash)) {
      return hash;
    }
  }
  return 'overview';
};

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<RouteId>(getInitialRoute);
  const [health, setHealth] = useState<BackendHealthState>({
    state: 'connecting',
    data: null,
    lastChecked: null,
    error: null,
  });
  const [isChecking, setIsChecking] = useState<boolean>(false);

  // Sync route changes with browser history
  const handleNavigate = useCallback((route: RouteId) => {
    setCurrentRoute(route);
    if (typeof window !== 'undefined' && window.history) {
      const url = new URL(window.location.href);
      url.searchParams.set('view', route);
      window.history.pushState({}, '', url.toString());
    }
  }, []);

  // Listen for back/forward navigation
  useEffect(() => {
    const onPopState = () => {
      setCurrentRoute(getInitialRoute());
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  // Check backend health endpoint
  const checkBackendHealth = useCallback(async () => {
    setIsChecking(true);
    setHealth((prev) => ({ ...prev, state: 'connecting', error: null }));

    try {
      let response: Response | null = null;

      // 1. Try relative /health first (used when hosted behind reverse proxy or Vite dev proxy)
      try {
        const localRes = await fetch('/health', {
          headers: { 'Accept': 'application/json' },
          cache: 'no-store',
        });
        if (localRes.ok) {
          response = localRes;
        }
      } catch {
        // Ignore network failure on relative URL; will try explicit backend URL below
      }

      // 2. If relative request did not succeed (e.g. 404 on standalone static preview server),
      // query the configured backend endpoint directly
      if (!response) {
        response = await fetch(`${BACKEND_BASE_URL}/health`, {
          headers: { 'Accept': 'application/json' },
          cache: 'no-store',
        });
      }

      if (response && response.ok) {
        const data: BackendHealthResponse = await response.json();
        setHealth({
          state: 'connected',
          data,
          lastChecked: new Date(),
          error: null,
        });
      } else {
        const statusText = response ? `HTTP ${response.status} ${response.statusText}` : 'Unreachable';
        setHealth({
          state: 'disconnected',
          data: null,
          lastChecked: new Date(),
          error: statusText,
        });
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Connection failed';
      setHealth({
        state: 'disconnected',
        data: null,
        lastChecked: new Date(),
        error: errorMessage,
      });
    } finally {
      setIsChecking(false);
    }
  }, []);

  // Poll health on mount and every 30s
  useEffect(() => {
    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 30000);
    return () => clearInterval(interval);
  }, [checkBackendHealth]);

  const activeRouteMeta = ROUTES.find((r) => r.id === currentRoute) || ROUTES[0];

  return (
    <div className="sentinel-app">
      <Navigation
        currentRoute={currentRoute}
        onNavigate={handleNavigate}
      />

      <div className="sentinel-main">
        <Header
          currentRoute={currentRoute}
          health={health}
          onRefreshHealth={checkBackendHealth}
          isChecking={isChecking}
        />

        <main className="sentinel-content" role="main">
          {currentRoute === 'overview' ? (
            <OverviewView
              health={health}
              onRefreshHealth={checkBackendHealth}
              isChecking={isChecking}
              onNavigate={handleNavigate}
            />
          ) : currentRoute === 'sources' ? (
            <SourcesView />
          ) : currentRoute === 'events' ? (
            <EventsView onNavigate={handleNavigate} />
          ) : currentRoute === 'findings' ? (
            <FindingsView onNavigate={handleNavigate} />
          ) : (
            <PlannedView
              routeMeta={activeRouteMeta}
              onNavigateHome={() => handleNavigate('overview')}
            />
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
