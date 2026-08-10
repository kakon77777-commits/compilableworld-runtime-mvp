# PIW Long-session Validation M12

This is the first executable long-session gate for the CompilableWorld Runtime
plan. It turns the earlier 100-turn validation target into a regression test
instead of leaving it as a prose milestone.

## Covered

- 100 turns × 3 observation actions (`look`, `inventory`, `status`), for 300
  normal Kernel submissions.
- Every action must complete through the normal Module → StateDelta → EventIR
  pipeline.
- Observation actions must not mutate the Runtime State snapshot.
- The durable EventLog must contain the expected commit/event pairs and unique
  event IDs, with causation IDs attached.
- A saved Snapshot must restore the same state and scheduler position.
- The resulting EventIR sequence must replay into an equivalent fresh Runtime.

## Boundary

This validates deterministic local long-session behavior, not multiplayer
consensus, network partitions, unbounded AI generation, or production-scale
load. Those remain separate deployment and stress-test packages.

## Verification

`tests/test_long_session.py` is included in the full Runtime regression suite.
