import { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '../api/client.js';

const WS_URL = import.meta.env?.VITE_WS_URL || (
  typeof window !== 'undefined' && window.location && window.location.port !== '5173'
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/events`
    : 'ws://localhost:8000/ws/events'
);

export const CONNECTION_STATUS = {
  CONNECTING: 'CONNECTING',
  CONNECTED: 'CONNECTED',
  RECONNECTING: 'RECONNECTING',
  DISCONNECTED: 'DISCONNECTED',
};

export const MAX_EVENT_CACHE = 100;

export function calculateBackoffDelay(
  attempt,
  baseBackoff = 1000,
  maxBackoff = 30000,
  backoffFactor = 2,
  jitterRatio = 0.1
) {
  const rawDelay = Math.min(baseBackoff * Math.pow(backoffFactor, attempt), maxBackoff);
  const jitter = rawDelay * jitterRatio * (Math.random() * 2 - 1);
  return Math.max(baseBackoff, Math.round(rawDelay + jitter));
}

export function createEventDeduplicator(maxCache = MAX_EVENT_CACHE) {
  const seenIds = new Set();
  const order = [];

  return function isDuplicate(event) {
    if (!event || !event.event_id) return false;
    if (seenIds.has(event.event_id)) {
      return true;
    }
    seenIds.add(event.event_id);
    order.push(event.event_id);
    if (order.length > maxCache) {
      const oldest = order.shift();
      seenIds.delete(oldest);
    }
    return false;
  };
}

export function useWebSocket(options = {}) {
  const {
    url = WS_URL,
    pollInterval = 5000,
    baseBackoff = 1000,
    maxBackoff = 30000,
    backoffFactor = 2,
  } = options;

  const [lastEvent, setLastEvent] = useState(null);
  const [status, setStatus] = useState(CONNECTION_STATUS.CONNECTING);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [isPolling, setIsPolling] = useState(false);

  const wsRef = useRef(null);
  const connectRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const pingTimerRef = useRef(null);
  const pollTimerRef = useRef(null);
  const attemptsRef = useRef(0);
  const deduplicatorRef = useRef(null);
  if (deduplicatorRef.current == null) {
    deduplicatorRef.current = createEventDeduplicator(MAX_EVENT_CACHE);
  }
  const hasEverConnectedRef = useRef(false);
  const isDisposedRef = useRef(false);

  // Helper to deduplicate events by event_id
  const isDuplicateEvent = useCallback((event) => {
    return deduplicatorRef.current(event);
  }, []);

  // Calculate exponential backoff delay with bounded cap
  const getBackoffDelay = useCallback((attempt) => {
    return calculateBackoffDelay(attempt, baseBackoff, maxBackoff, backoffFactor);
  }, [baseBackoff, maxBackoff, backoffFactor]);

  // Start REST fallback polling when disconnected
  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return;
    setIsPolling(true);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('app:poll-refresh'));
      pollTimerRef.current = setInterval(() => {
        window.dispatchEvent(new CustomEvent('app:poll-refresh'));
      }, pollInterval);
    }
  }, [pollInterval]);

  // Stop REST fallback polling when connected
  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const connect = useCallback(() => {
    if (isDisposedRef.current) return;

    // Prevent duplicate connections if existing socket is active or opening
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      return;
    }

    // Clean up old socket if in closing/closed state
    if (wsRef.current) {
      try {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
      } catch {
        // ignore close error
      }
      wsRef.current = null;
    }

    const token = getToken();
    if (!token) {
      setStatus(CONNECTION_STATUS.DISCONNECTED);
      startPolling();
      return;
    }

    setStatus(attemptsRef.current > 0 ? CONNECTION_STATUS.RECONNECTING : CONNECTION_STATUS.CONNECTING);

    try {
      const ws = new WebSocket(`${url}?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (isDisposedRef.current) {
          ws.close();
          return;
        }
        setStatus(CONNECTION_STATUS.CONNECTED);
        attemptsRef.current = 0;
        setReconnectAttempts(0);
        stopPolling();

        // If this was a reconnection, dispatch notification and authoritative refresh
        if (hasEverConnectedRef.current) {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('websocket:reconnected'));
            window.dispatchEvent(new CustomEvent('app:refresh-authoritative'));
          }
        }
        hasEverConnectedRef.current = true;

        // Start ping heartbeat every 30s
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);
      };

      ws.onmessage = (evt) => {
        if (isDisposedRef.current) return;
        try {
          const data = JSON.parse(evt.data);
          if (data.event_type === 'PONG') return;

          // Deduplicate events
          if (isDuplicateEvent(data)) return;

          setLastEvent(data);
        } catch {
          // ignore non-json messages
        }
      };

      ws.onclose = () => {
        if (isDisposedRef.current) return;

        if (pingTimerRef.current) {
          clearInterval(pingTimerRef.current);
          pingTimerRef.current = null;
        }

        setStatus(CONNECTION_STATUS.RECONNECTING);
        startPolling();

        // Schedule reconnection with bounded exponential backoff
        attemptsRef.current += 1;
        setReconnectAttempts(attemptsRef.current);
        const delay = getBackoffDelay(attemptsRef.current);

        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(() => {
          connectRef.current?.();
        }, delay);
      };

      ws.onerror = () => {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          try {
            ws.close();
          } catch {
            // ignore
          }
        }
      };
    } catch {
      setStatus(CONNECTION_STATUS.DISCONNECTED);
      startPolling();
      attemptsRef.current += 1;
      setReconnectAttempts(attemptsRef.current);
      const delay = getBackoffDelay(attemptsRef.current);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        connectRef.current?.();
      }, delay);
    }
  }, [url, getBackoffDelay, isDuplicateEvent, startPolling, stopPolling]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Imperative manual reconnect trigger
  const manualReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    attemptsRef.current = 0;
    setReconnectAttempts(0);
    connect();
  }, [connect]);

  useEffect(() => {
    isDisposedRef.current = false;

    const handleOnline = () => {
      manualReconnect();
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('online', handleOnline);
    }

    connect();

    return () => {
      isDisposedRef.current = true;
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      if (typeof window !== 'undefined') {
        window.removeEventListener('online', handleOnline);
      }
      if (wsRef.current) {
        try {
          wsRef.current.onopen = null;
          wsRef.current.onmessage = null;
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.close();
        } catch {
          // ignore
        }
        wsRef.current = null;
      }
    };
  }, [connect, manualReconnect]);

  return {
    lastEvent,
    status,
    isConnected: status === CONNECTION_STATUS.CONNECTED,
    reconnectAttempts,
    isPolling,
    reconnect: manualReconnect,
  };
}
