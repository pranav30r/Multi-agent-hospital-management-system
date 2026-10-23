# Task 6: End-to-End Validation

## Acceptance flow

`backend/tests/test_task6_end_to_end_acceptance.py` exercises one realistic high-risk emergency from intake to dashboard:

1. Seed a patient with severe chest-pain symptoms and an available ICU bed.
2. Complete the clinical intake questionnaire.
3. Run the coordinated triage/resource workflow and verify it creates a pending approval without reserving a bed prematurely.
4. Approve as a doctor and verify the encounter/bed association, reserved-bed count, and pending-approval count change.
5. Verify intake, approval-required, bed-reserved, and approval-decided events reach the connected dashboard WebSocket.

The test runs with Redis unavailable, exercising the in-process event fallback. It uses the project's test database fixtures and does not require Docker.

## Run the acceptance test

From the repository root in PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_task6_end_to_end_acceptance.py -p no:cacheprovider
```

## Focused edge-case validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_hospital_workflow_coordinator.py::test_03_high_risk_escalation_and_hitl_approval_gate `
  tests/test_hospital_workflow_coordinator.py::test_05_no_eligible_bed_resource_unavailable `
  tests/test_concurrency_reliability.py::test_concurrent_bed_booking_exact_single_winner `
  tests/test_event_driven_agent_execution.py::test_event_id_deduplication `
  tests/test_event_driven_agent_execution.py::test_concurrent_duplicate_events_for_same_encounter `
  tests/test_event_driven_agent_execution.py::test_transient_error_retry_with_backoff `
  tests/test_event_driven_agent_execution.py::test_fatal_error_aborts_without_infinite_retry `
  tests/test_approval_execution_pipeline.py::test_approval_fails_closed_when_target_bed_is_stale_or_occupied `
  -p no:cacheprovider
```

These cover high-risk human review, unavailable beds, conflicting bed bookings (single winner), repeated event IDs, concurrent duplicate intake events, transient agent failure/retry, fatal agent failure, and stale/occupied approval targets. The concurrent-event test waits for actual worker-queue completion rather than sleeping for a fixed duration, preventing slow CI/local runs from being mistaken for missing orchestration.
