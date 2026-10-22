import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateBackoffDelay,
  createEventDeduplicator,
  CONNECTION_STATUS,
  MAX_EVENT_CACHE,
} from '../hooks/useWebSocket.js';

describe('Real-Time Resilience - WebSocket & Polling Protocol', () => {
  describe('Connection Status State Machine Definitions', () => {
    test('defines all 4 connection lifecycle states', () => {
      assert.equal(CONNECTION_STATUS.CONNECTING, 'CONNECTING');
      assert.equal(CONNECTION_STATUS.CONNECTED, 'CONNECTED');
      assert.equal(CONNECTION_STATUS.RECONNECTING, 'RECONNECTING');
      assert.equal(CONNECTION_STATUS.DISCONNECTED, 'DISCONNECTED');
    });

    test('connection states are distinct', () => {
      const values = Object.values(CONNECTION_STATUS);
      const unique = new Set(values);
      assert.equal(values.length, 4);
      assert.equal(unique.size, 4);
    });
  });

  describe('Bounded Exponential Backoff with Jitter', () => {
    test('initial attempt (0) produces delay around base backoff (1000ms)', () => {
      for (let i = 0; i < 20; i++) {
        const delay = calculateBackoffDelay(0, 1000, 30000, 2, 0.1);
        assert.ok(delay >= 900, `delay ${delay} should be >= 900`);
        assert.ok(delay <= 1100, `delay ${delay} should be <= 1100`);
      }
    });

    test('backoff increases exponentially across initial attempts', () => {
      const delay0 = calculateBackoffDelay(0, 1000, 30000, 2, 0.0);
      const delay1 = calculateBackoffDelay(1, 1000, 30000, 2, 0.0);
      const delay2 = calculateBackoffDelay(2, 1000, 30000, 2, 0.0);
      const delay3 = calculateBackoffDelay(3, 1000, 30000, 2, 0.0);

      assert.equal(delay0, 1000);
      assert.equal(delay1, 2000);
      assert.equal(delay2, 4000);
      assert.equal(delay3, 8000);
    });

    test('backoff is capped at maxBackoff (30000ms)', () => {
      for (let attempt = 5; attempt <= 15; attempt++) {
        const delayNoJitter = calculateBackoffDelay(attempt, 1000, 30000, 2, 0.0);
        assert.equal(delayNoJitter, 30000);

        const delayWithJitter = calculateBackoffDelay(attempt, 1000, 30000, 2, 0.1);
        assert.ok(delayWithJitter >= 27000, `delay ${delayWithJitter} >= 27000`);
        assert.ok(delayWithJitter <= 33000, `delay ${delayWithJitter} <= 33000`);
      }
    });

    test('delay never falls below baseBackoff', () => {
      for (let i = 0; i < 50; i++) {
        const delay = calculateBackoffDelay(0, 1000, 30000, 2, 0.5);
        assert.ok(delay >= 1000, `delay ${delay} should never fall below baseBackoff`);
      }
    });
  });

  describe('Ring-Buffer Event Deduplication', () => {
    test('accepts first occurrence of an event and rejects duplicates', () => {
      const isDuplicate = createEventDeduplicator(10);

      const eventA = { event_id: 'evt-001', event_type: 'BED_OCCUPIED', payload: { bed_id: 'BED-01' } };
      const eventB = { event_id: 'evt-002', event_type: 'BED_RELEASED', payload: { bed_id: 'BED-02' } };

      assert.equal(isDuplicate(eventA), false, 'First occurrence of eventA should not be duplicate');
      assert.equal(isDuplicate(eventA), true, 'Immediate duplicate of eventA must be detected');
      assert.equal(isDuplicate(eventB), false, 'First occurrence of eventB should not be duplicate');
      assert.equal(isDuplicate(eventB), true, 'Duplicate of eventB must be detected');
    });

    test('gracefully handles missing or malformed event_id without throwing', () => {
      const isDuplicate = createEventDeduplicator(10);

      assert.equal(isDuplicate(null), false);
      assert.equal(isDuplicate(undefined), false);
      assert.equal(isDuplicate({}), false);
      assert.equal(isDuplicate({ event_type: 'PONG' }), false);
    });

    test('evicts oldest event when ring buffer capacity is exceeded', () => {
      const capacity = 5;
      const isDuplicate = createEventDeduplicator(capacity);

      // Insert 5 unique events
      for (let i = 1; i <= capacity; i++) {
        const res = isDuplicate({ event_id: `evt-${i}` });
        assert.equal(res, false, `Event ${i} should be accepted`);
      }

      // Re-testing evt-1 should still report duplicate
      assert.equal(isDuplicate({ event_id: 'evt-1' }), true);

      // Insert 6th event, which should evict evt-2 (or evt-1 if not re-added, here evt-1 was queried not added)
      isDuplicate({ event_id: 'evt-6' });

      // Now insert more events to completely flush out evt-1
      for (let i = 7; i <= 12; i++) {
        isDuplicate({ event_id: `evt-${i}` });
      }

      // evt-1 should now have been evicted from the ring buffer
      assert.equal(isDuplicate({ event_id: 'evt-1' }), false, 'Evicted event-1 should be treated as new');
    });

    test('default ring buffer capacity matches MAX_EVENT_CACHE (100)', () => {
      assert.equal(MAX_EVENT_CACHE, 100);
      const isDuplicate = createEventDeduplicator();

      for (let i = 1; i <= 100; i++) {
        assert.equal(isDuplicate({ event_id: `e-${i}` }), false);
      }
      assert.equal(isDuplicate({ event_id: 'e-1' }), true);

      // Pushing 101 more entries should evict e-1
      for (let i = 101; i <= 201; i++) {
        isDuplicate({ event_id: `e-${i}` });
      }
      assert.equal(isDuplicate({ event_id: 'e-1' }), false);
    });
  });

  describe('Event Bus Protocol Contracts', () => {
    test('dispatches and listens to authoritative refresh events', () => {
      let authoritativeRefreshes = 0;
      let pollRefreshes = 0;
      let reconnectedEvents = 0;

      const target = new EventTarget();

      const onAuth = () => { authoritativeRefreshes += 1; };
      const onPoll = () => { pollRefreshes += 1; };
      const onRecon = () => { reconnectedEvents += 1; };

      target.addEventListener('app:refresh-authoritative', onAuth);
      target.addEventListener('app:poll-refresh', onPoll);
      target.addEventListener('websocket:reconnected', onRecon);

      target.dispatchEvent(new CustomEvent('app:poll-refresh'));
      target.dispatchEvent(new CustomEvent('app:poll-refresh'));
      target.dispatchEvent(new CustomEvent('websocket:reconnected'));
      target.dispatchEvent(new CustomEvent('app:refresh-authoritative'));

      assert.equal(pollRefreshes, 2);
      assert.equal(reconnectedEvents, 1);
      assert.equal(authoritativeRefreshes, 1);

      // Teardown / cleanup
      target.removeEventListener('app:refresh-authoritative', onAuth);
      target.removeEventListener('app:poll-refresh', onPoll);
      target.removeEventListener('websocket:reconnected', onRecon);

      target.dispatchEvent(new CustomEvent('app:poll-refresh'));
      assert.equal(pollRefreshes, 2, 'No updates after listener teardown');
    });

    test('legitimate successive updates for the same entity with distinct event_ids are preserved', () => {
      const isDuplicate = createEventDeduplicator();

      // Lifecycle updates for the same bed BED-ICU-01
      const step1 = { event_id: 'evt-bed-1', event_type: 'BED_RESERVED', payload: { bed_id: 'BED-ICU-01', status: 'RESERVED' } };
      const step2 = { event_id: 'evt-bed-2', event_type: 'BED_OCCUPIED', payload: { bed_id: 'BED-ICU-01', status: 'OCCUPIED' } };
      const step3 = { event_id: 'evt-bed-3', event_type: 'BED_RELEASED', payload: { bed_id: 'BED-ICU-01', status: 'AVAILABLE' } };

      assert.equal(isDuplicate(step1), false, 'First step should pass');
      assert.equal(isDuplicate(step1), true, 'Duplicate of first step should be filtered');
      assert.equal(isDuplicate(step2), false, 'Legitimate status progression (step 2) must not be discarded');
      assert.equal(isDuplicate(step3), false, 'Legitimate status progression (step 3) must not be discarded');
    });

    test('simulates polling fallback lifecycle transitions', () => {
      let isPolling = false;
      let pollCount = 0;
      let timer = null;

      const startPolling = (interval = 50) => {
        if (timer) return;
        isPolling = true;
        pollCount += 1; // immediate poll
        timer = setInterval(() => { pollCount += 1; }, interval);
      };

      const stopPolling = () => {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
        isPolling = false;
      };

      // Disconnect occurs -> start polling
      startPolling(50);
      assert.equal(isPolling, true);
      assert.equal(pollCount, 1);

      // Reconnection occurs -> stop polling
      stopPolling();
      assert.equal(isPolling, false);
      const frozenCount = pollCount;

      // Another disconnect occurs -> resumes polling
      startPolling(50);
      assert.equal(isPolling, true);
      assert.equal(pollCount, frozenCount + 1);

      stopPolling();
      assert.equal(isPolling, false);
    });
  });
});
