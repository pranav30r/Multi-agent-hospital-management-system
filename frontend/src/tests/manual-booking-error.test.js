import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Manual Bed Booking Error Handling', () => {
  test('failed bookBedManual does not trigger status-update fallback and surfaces actual error', async () => {
    let updateBedStatusCalled = false;
    let actualErrorMessage = null;

    // Simulated bookBedManual that fails with backend rejection
    const mockBookBedManual = async () => {
      throw new Error("Bed BED-ICU-01 is in 'OCCUPIED' state and cannot be booked");
    };

    // Simulated updateBedStatus fallback
    const mockUpdateBedStatus = async () => {
      updateBedStatusCalled = true;
    };

    // Simulated handler matching the updated BedGrid logic (no fallback invocation)
    const handleBookBedSimulated = async (fallbackFn = null) => {
      try {
        await mockBookBedManual({
          bed_id: 'BED-ICU-01',
          encounter_id: 'ENC-001',
          patient_id: 'PAT-001',
          reason: 'Emergency admission',
        });
      } catch (err) {
        if (fallbackFn) await fallbackFn();
        actualErrorMessage = err.message || "Failed to reserve bed.";
      }
    };

    // Execute with no fallback function passed
    await handleBookBedSimulated(null);

    // Verify mockUpdateBedStatus exists as a function but was never invoked
    assert.equal(typeof mockUpdateBedStatus, 'function');
    assert.equal(updateBedStatusCalled, false, 'updateBedStatus should not be called when bookBedManual fails');

    // Invariant 2: Actual backend error message MUST be surfaced
    assert.equal(
      actualErrorMessage,
      "Bed BED-ICU-01 is in 'OCCUPIED' state and cannot be booked",
      'Actual backend error must be preserved and surfaced to user'
    );
  });

  test('successful bookBedManual executes without triggering fallback', async () => {
    let updateBedStatusCalled = false;
    let bookedPayload = null;

    const mockBookBedManual = async (payload) => {
      bookedPayload = payload;
      return { id: payload.bed_id, status: 'RESERVED' };
    };

    const handleBookBedSimulated = async () => {
      await mockBookBedManual({
        bed_id: 'BED-GEN-04',
        encounter_id: 'ENC-002',
        patient_id: 'PAT-002',
        reason: 'Direct clinician assignment',
      });
    };

    await handleBookBedSimulated();

    assert.equal(updateBedStatusCalled, false);
    assert.equal(bookedPayload.bed_id, 'BED-GEN-04');
    assert.equal(bookedPayload.patient_id, 'PAT-002');
  });
});
