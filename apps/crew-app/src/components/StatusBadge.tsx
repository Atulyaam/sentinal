import React from 'react';
import { ConnectionState } from '../types';

interface StatusBadgeProps {
  state: ConnectionState;
  appVersion?: string;
  onRefresh?: () => void;
  isChecking?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ 
  state, 
  appVersion, 
  onRefresh, 
  isChecking = false 
}) => {
  const getLabel = () => {
    switch (state) {
      case 'connected':
        return `Backend Connected${appVersion ? ` (v${appVersion})` : ''}`;
      case 'connecting':
        return 'Connecting...';
      case 'disconnected':
        return 'Backend Unavailable';
    }
  };

  return (
    <div 
      className={`status-pill ${state}`} 
      role="status" 
      aria-live="polite"
      aria-label={`System Status: ${getLabel()}`}
    >
      <span className="status-pill-dot" aria-hidden="true" />
      <span>{getLabel()}</span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isChecking}
          title="Refresh connectivity status"
          aria-label="Refresh connectivity status"
          style={{
            background: 'none',
            border: 'none',
            color: 'inherit',
            cursor: isChecking ? 'default' : 'pointer',
            padding: '2px',
            marginLeft: '4px',
            display: 'inline-flex',
            alignItems: 'center',
            opacity: isChecking ? 0.5 : 0.85
          }}
        >
          <svg 
            width="12" 
            height="12" 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            strokeWidth="2.5" 
            strokeLinecap="round" 
            strokeLinejoin="round"
            style={{
              animation: isChecking ? 'spin 1s linear infinite' : 'none'
            }}
          >
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        </button>
      )}
    </div>
  );
};
