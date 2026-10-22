import { createContext, useContext } from 'react';
import { useWebSocket, CONNECTION_STATUS } from '../hooks/useWebSocket.js';

const EventContext = createContext({
  lastEvent: null,
  isConnected: false,
  status: CONNECTION_STATUS.DISCONNECTED,
  reconnectAttempts: 0,
  isPolling: false,
  reconnect: () => {},
});

export function EventProvider({ children }) {
  const {
    lastEvent,
    status,
    isConnected,
    reconnectAttempts,
    isPolling,
    reconnect,
  } = useWebSocket();

  return (
    <EventContext.Provider
      value={{
        lastEvent,
        status,
        isConnected,
        reconnectAttempts,
        isPolling,
        reconnect,
      }}
    >
      {children}
    </EventContext.Provider>
  );
}

export function useEvents() {
  return useContext(EventContext);
}

export default EventContext;
