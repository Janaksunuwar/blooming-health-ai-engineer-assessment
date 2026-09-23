# Q3 — Agent Evaluation Results

This is the readable version of [`results.json`](results.json). Every status, disposition and finding below comes from that file. `results.json` also holds the full per-thread evidence (classified answers, observed agent behavior and volunteered information).

## Evaluation Scope

The evaluator checks 10 simulated Medi-Cal renewal triage conversations (`thread_01` to `thread_10`) against the workflow configuration in the Gym JSON (`agent_config.engine_config.items` and `outcomes`). For each conversation it checks:

- whether the agent asked the configured questions in the configured order;
- whether the agent reached the terminal disposition that the caller's answers call for;
- whether the transcript contains quality problems, such as leaked internal text or answers the caller gave before being asked.

This evaluation looks only at what the transcripts show. It does not train a model, and it does not assess the underlying language model end to end. It was run in `transcript_only` mode (`captured_fields_supplied: false`, `interviewer_artifacts_used: false`). The answer key and full-events files were not used.

`expected_disposition` is worked out by the evaluator from the configured question graph and the caller's classified answers. `observed_disposition` is the terminal language it found in the agent's turns. If a conversation has no terminal step, both are `null`.

## Summary

| Dimension | PASS | FAIL | UNCERTAIN | NOT_EVALUATED |
|---|---:|---:|---:|---:|
| Workflow status | 6 | 3 | 1 | 0 |
| Task completion | 4 | 3 | 3 | 0 |
| Overall status | 4 | 3 | 3 | 0 |
| Captured-field accuracy | 0 | 0 | 0 | 10 |

These totals were counted directly from `q3/results.json` (10 result objects).

**Captured-field accuracy is `NOT_EVALUATED` for all 10 threads.** The candidate-facing dataset does not include the field values the agent actually saved, so there is nothing to compare against the transcript. Every thread therefore has a `missing_captured_fields` uncertainty. As a result, even an overall `PASS` here says nothing about whether the application fields were recorded correctly.

A workflow `PASS` and an overall `PASS` mean different things. The workflow check asks whether the transcript followed the configured question graph without a critical failure. The overall status also depends on task completion. Threads 02 and 08 show the difference: their workflow is `PASS`, but their overall status is `UNCERTAIN`.

## Per-Conversation Results

| Thread | Workflow | Task completion | Overall | Expected disposition | Observed disposition | Explanation (from `results.json`) |
|---|---|---|---|---|---|---|
| `thread_01` | PASS | PASS | PASS | `medi_cal_active` | `medi_cal_active` | The agent asked `q1_intent` and `q2_active`. The caller said coverage is active, and the agent used `medi_cal_active` terminal language. No critical failures or warnings. The only uncertainty is `missing_captured_fields`. |
| `thread_02` | PASS | UNCERTAIN | UNCERTAIN | `complete_renewal` | `complete_renewal` | The full path `q1_intent` → `q5_packet` was asked in order, and the agent reached `complete_renewal` language. Task completion is `UNCERTAIN` because of `renewal_execution_not_observed`: the transcript does not show the renewal being completed or submitted. See the [note on `complete_renewal`](#note-on-complete_renewal-threads-02-and-08). One warning: in turn 3 the caller answered `q5_packet` early ("never actually got that yellow renewal packet"). No critical failures. |
| `thread_03` | PASS | PASS | PASS | `escalated_chw_out_of_county` | `escalated_chw_out_of_county` | The agent asked `q1_intent` → `q4_residency`. The caller said they moved out of San Diego County, and the agent escalated with out-of-county CHW language. Three warnings: the caller answered `q2_active` and `q3_coverage` early (turn 0) and `q4_residency` early (turn 1). No critical failures. |
| `thread_04` | PASS | PASS | PASS | `medi_cal_active` | `medi_cal_active` | The agent asked `q1_intent` and `q2_active`. The caller said they are still covered, and the agent used `medi_cal_active` language. No critical failures or warnings. |
| `thread_05` | **FAIL** | **FAIL** | **FAIL** | `escalated_chw_appointment` | `escalated_chw_appointment` | The question path and disposition match (in-person CHW appointment). However, the evaluator found **6 `leaked_internal_text` critical failures**: every agent turn from -1 to 4 contains the internal placeholder "(Waiting for your response.)". Under the evaluator's rules, a critical failure makes the workflow, task and overall status all `FAIL`, even when the route itself is correct. One warning: in turn 1 the caller answered `q3_coverage` early. |
| `thread_06` | PASS | PASS | PASS | `escalated_chw_out_of_county` | `escalated_chw_out_of_county` | At `q1_intent` the caller said they were not interested. The agent then asked the configured `decline` follow-up, and the caller said they had moved out of the county. The agent escalated with out-of-county CHW language. No critical failures or warnings. |
| `thread_07` | UNCERTAIN | UNCERTAIN | UNCERTAIN | `null` | `null` | **No terminal disposition was observed** (`missing_terminal_evidence`). The agent asked every question through `q5_choice` (by phone or in person). The transcript ends there, before the caller answers and before any terminal step. The caller's `[GOAL_ACHIEVED]` in turn 4 is a dataset artifact, not a completion signal. Three warnings: the caller answered `q3_coverage` early (turn 1), `q5_packet` early (turn 2) and `q5_choice` early (turn 3). No critical failures. |
| `thread_08` | PASS | UNCERTAIN | UNCERTAIN | `complete_renewal` | `complete_renewal` | The full path `q1_intent` → `q5_packet` was asked in order, and the agent reached `complete_renewal` language. Task completion is `UNCERTAIN` because of `renewal_execution_not_observed`: the transcript does not show the renewal being completed or submitted. See the [note on `complete_renewal`](#note-on-complete_renewal-threads-02-and-08). Two warnings: the caller answered `q3_coverage` early (turn 1) and `q5_packet` early (turn 3). No critical failures. |
| `thread_09` | **FAIL** | **FAIL** | **FAIL** | `null` | `null` | **4 `leaked_internal_text` critical failures**: agent turns -1 to 2 each contain the internal placeholder "(Waiting for your answer.)". **No terminal disposition was observed** either (`missing_terminal_evidence`). The caller reported Kaiser Permanente coverage, the agent asked `q3_plan` ("Which plan is that?"), and the transcript ends before any terminal step. The caller's `[GOAL_ACHIEVED]` in turn 2 is a dataset artifact. Three warnings: in turn 0 the caller answered `q2_active`, `q3_coverage` and `q3_plan` early. |
| `thread_10` | **FAIL** | **FAIL** | **FAIL** | `null` | `null` | **1 `leaked_internal_text` critical failure**: the agent's turn 0 contains "(Waiting for your response.)". The transcript also ends right after the agent asks `q2_active`, so no terminal disposition was observed (`missing_terminal_evidence`). The caller's `[GOAL_ACHIEVED]` in turn 0 is a dataset artifact. One warning: in turn 0 the caller answered `q2_active` early. |

### Note on `complete_renewal` (threads 02 and 08)

Both threads carry the uncertainty `renewal_execution_not_observed`. It is added whenever the observed disposition is `complete_renewal`, and it keeps task completion at `UNCERTAIN` without changing the workflow status.

The reason is the configuration. Unlike the handoff outcomes, the `no_or_lost` route in `q5_packet` goes to `_complete` ("let's get your renewal started"). That means the agent itself is responsible for carrying out the renewal. The transcripts show the route being reached, but not the renewal being done:

- **Observed:** In `thread_02`, turn 4, the agent says "let's get your renewal started. Thank you for your time, and take care!" In turn 5 it then begins collecting details ("Let's start by verifying your name, address, and date of birth"). The transcript ends there. In `thread_08`, turn 4, the agent says "let's get your renewal started. Thank you for your time, and goodbye!" The transcript ends there.
- **Not observed, and not inferred:** Neither transcript shows that a renewal was completed, submitted or processed. Confirming that requires downstream renewal or application-submission records, which the dataset does not include.

### About `[GOAL_ACHIEVED]`

Several caller turns in the input data end with the string `[GOAL_ACHIEVED]` (threads 01, 03, 05, 07, 09 and 10). This marker comes from the simulated caller in the dataset. The evaluator's code does not refer to it, and it does not count toward any status. Threads 07, 09 and 10 contain it but have no terminal disposition.

## Main Findings

- **Critical failures (3 threads):** The only critical failure type found was `leaked_internal_text`: an internal "(Waiting for your ...)" placeholder appeared in what the agent said to the caller. It occurred in `thread_05` (6 agent turns, "(Waiting for your response.)"), `thread_09` (4 agent turns, "(Waiting for your answer.)") and `thread_10` (1 agent turn, "(Waiting for your response.)"), and made all three threads `FAIL`. For `thread_05` this is the only reason for the failure: its question path and disposition both match what was expected.
- **Not enough evidence of completion (3 `UNCERTAIN` threads):**
  - `thread_07` ends before any terminal step (`missing_terminal_evidence`).
  - `thread_02` and `thread_08` reach `complete_renewal` routing, but the transcript does not show the renewal being carried out (`renewal_execution_not_observed`; see the note above).
  - `thread_09` and `thread_10` also have no terminal disposition, but their overall status is `FAIL` because of their critical failures.
- **Answers given before the question was asked (warnings, 7 threads):** `volunteered_answer_needs_confirmation` warnings appear in threads 02, 03, 05, 07, 08, 09 and 10. These are warnings, not critical failures. For example, `thread_03` has three of these warnings and is still `PASS` overall. The evaluator recommends confirming or saving these answers before the workflow relies on them.
- **Captured fields could not be checked (all 10 threads):** Field accuracy is `NOT_EVALUATED` because the dataset has no captured-field values. A transcript-level `PASS` does not show that the fields saved to the application are accurate, or that any downstream renewal or handoff actually happened. You can supply claimed field values with `--captured-fields` (see [`README.md`](README.md)).

### What leak detection covers

The detector flags any parenthetical beginning "(Waiting for your", which catches both variants in the dataset. It deliberately does not flag other parenthetical asides. For example, `thread_03` contains "(Please let me know your answer.)" and "(Go ahead and let me know.)". These could be the caller-facing prompt the agent intended, so they are not treated as internal placeholders. The spec lists "extra helper text" as a noncritical warning, but the evaluator does not currently emit a warning for these asides, so they have no effect on `thread_03`'s result.

### Evaluator changes in this revision

This report reflects the evaluator after three changes, each covered by a regression test in `q3/tests/test_evaluator.py`:

1. **Leak detection widened** from the exact string "(waiting for your response.)" to any "(Waiting for your …)" parenthetical. Scoring effect: `thread_09` went from `UNCERTAIN` to `FAIL` on workflow, task completion and overall status.
2. **`complete_renewal` uncertainty made explicit** with the new `renewal_execution_not_observed` entry and a matching recommended fix. Scoring effect: none. Threads 02 and 08 were already `UNCERTAIN`, and now the reason appears in `results.json`, as the spec's rule that every uncertain result must be explained requires.
3. **In-person choice classification tightened**, so that a bare mention of "appointment" no longer counts as choosing an in-person appointment. It now needs "in person" or an explicit request, such as "set up an appointment". Scoring effect: none. The change removes a spurious volunteered `q5_choice = In-person appointment` from `thread_04`'s supporting evidence, which came from "I just used it for an appointment last week".

`[GOAL_ACHIEVED]` is still excluded from scoring. A regression test confirms that removing it from the dataset leaves every thread's statuses and dispositions unchanged.

## How to Reproduce

Evaluate the 10 conversations. This produces `results.json`, the data behind this report:

```bash
python3 q3/run.py \
  --input q3/data/gym_agent_conversations.json \
  --output q3/results.json
```

Run the evaluator's unit tests. These test the evaluator's own code, not the 10 conversations, and their pass/fail result is separate from the conversation results above:

```bash
python3 -m unittest discover -s q3/tests -v
```
