import { createContext, useContext } from 'react';
import { useWebSocket } from '../hooks/useWebSocket.js';

const EventContext = createContext({ lastEvent: null, isConnected: false });

export function EventProvider({ children }) {
  const { lastEvent, isConnected } = useWebSocket();

  return (
    <EventContext.Provider value={{ lastEvent, isConnected }}>
      {children}
    </EventContext.Provider>
  );
}

export function useEvents() {
  return useContext(EventContext);
}

export default EventContext;
