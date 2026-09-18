import { useState, useEffect, useRef } from 'react';
import { getToken } from '../api/client.js';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/events';

export function useWebSocket() {
  const [lastEvent, setLastEvent] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    let pingTimer = null;
    let reconnectTimer = null;
    let retryDelay = 1000;
    let isDisposed = false;

    function connect() {
      if (isDisposed) return;
      const token = getToken();
      if (!token) return;

      try {
        const ws = new WebSocket(`${WS_URL}?token=${token}`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isDisposed) return;
          setIsConnected(true);
          retryDelay = 1000;
          pingTimer = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send('ping');
            }
          }, 30000);
        };

        ws.onmessage = (evt) => {
          if (isDisposed) return;
          try {
            const data = JSON.parse(evt.data);
            if (data.event_type !== 'PONG') {
              setLastEvent(data);
            }
          } catch {
            // ignore non-json payload
          }
        };

        ws.onclose = () => {
          if (isDisposed) return;
          setIsConnected(false);
          clearInterval(pingTimer);
          reconnectTimer = setTimeout(() => {
            retryDelay = Math.min(retryDelay * 2, 30000);
            connect();
          }, retryDelay);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        // ignore connection failure
      }
    }

    connect();

    return () => {
      isDisposed = true;
      clearInterval(pingTimer);
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { lastEvent, isConnected };
}
