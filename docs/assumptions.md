# Assumptions

## Q1

- The burst calculation uses a conservative upper-bound scenario: all 10,000 outbound calls are answered immediately, start uniformly over 30 minutes, and last exactly 40 minutes.
- Final worker sizing depends on measured safe concurrent sessions per worker, including audio-frame latency, underruns, CPU scheduling delay, memory, provider limits, and telephony limits.

## Q2

- The Realtime WebSocket remains open for the call; correctness must not depend on restarting the session or rewriting prior audio-native history.
- The model can propose answers and speak naturally, but the external workflow controller and answer store are authoritative for validated fields and workflow advancement.

## Q3

- The submitted candidate-facing dataset contains ten transcript-only simulated calls and workflow configuration.
- Claimed captured-field records from the original assessment are not present in the candidate-facing dataset. Full field-accuracy evaluation requires a reviewer-supplied captured-fields JSON file.
- The evaluator uses only deterministic and conservative heuristic checks by default. It does not use interviewer answer keys, full-events files, reward labels, or an LLM API.
