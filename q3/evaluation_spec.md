# Q3 Evaluation Specification

## Input Data Schema

The candidate-facing input found locally is `gym_agent_conversations (1).json`. The submitted repository should not include the answer key or full-events files because they contain interviewer-side labels, rewards, and raw evaluation signals.

The usable dataset contains:

- Top-level metadata: `dataset`, `source`, `description`, `notes`, `num_threads`, `agent_id`.
- `agent_config.engine_config.items`: workflow questions, question IDs, answer types, allowed options, scenario routes, and terminal dispositions.
- `agent_config.engine_config.outcomes`: expected terminal outcomes and next actions.
- `threads[]`: ten simulated calls with `thread_id`, `episode_id`, `session_id`, `started_at`, `num_turns`, and `messages[]`.
- `messages[]`: ordered transcript events with `turn`, `role`, and `text`.

The original assessment describes two inputs: a transcript and structured captured-field values. The available candidate-facing JSON includes transcripts and workflow configuration, but does not include per-thread captured-field values, claimed final dispositions, or submitted application fields. Those missing inputs must be reported by the evaluator rather than invented.

## Definition of Call Success

A call succeeds if the transcript supports that the agent followed the configured healthcare workflow, captured or routed the member based on answers that are actually evidenced in the conversation, and reached the correct terminal action without a critical workflow error.

Because captured-field values are absent, this dataset can only support a transcript-based workflow evaluation. A full success decision for the original Q3 spec requires structured claimed fields to compare against the transcript. Without them, some calls should return `UNCERTAIN` rather than forced `PASS` or `FAIL`.

The evaluator reports separate dimensions:

- `workflow_status`: configured branching and question progression.
- `field_accuracy_status`: transcript-supported captured fields, or `NOT_EVALUATED` when absent.
- `task_completion_status`: terminal disposition or configured triage responsibility.
- warnings: noncritical conversation-quality issues.

Overall aggregation:

- Verified critical failure => `FAIL`.
- No critical failure but required evidence missing => `UNCERTAIN`.
- All required checks pass => `PASS`.

A transcript-only `PASS` must not be interpreted as proof that captured application fields are accurate.

## Deterministic Evaluation Criteria

The minimum evaluator should run without an API key and perform deterministic checks:

- Validate JSON shape and required keys.
- Build a workflow graph from `agent_config.engine_config.items`.
- Verify message ordering and agent/caller role structure.
- Detect which configured questions the agent asked using normalized text matching.
- Detect exact allowed-option mentions where the caller's answer is unambiguous.
- Check that the next asked question or terminal outcome is allowed by the current workflow node.
- Check that terminal outcome language matches a configured disposition when one is expected.
- Flag repeated questions, skipped required questions, invalid transitions, and premature closing.
- Report missing structured captured-field values as an input gap.
- Retain explicit volunteered answers without treating the corresponding questions as asked.
- Detect leaked internal/template artifacts in agent output (e.g. a placeholder string like "(Waiting for your response.)" that should never reach spoken output) as a critical failure, independent of question-identification logic.
- Detect when a caller appears to correct a previously given answer, flagging the correction and, when the new value can't be confidently resolved, returning an uncertain_answer_correction result rather than silently overwriting the prior answer.

Critical failures include wrong branching after an unambiguous answer, skipping a required question before a terminal decision, closing with a disposition contradicted by the caller, or claiming completion when the transcript leaves a required branch unresolved.

Noncritical warnings include awkward phrasing, redundant confirmations that do not change the branch, extra helper text, or minor conversational quality issues that do not corrupt the workflow outcome.

## Semantic Evaluation Criteria

Some checks require semantic interpretation and should be isolated behind an optional interface:

- Classifying free-text caller answers into configured scenario IDs.
- Determining whether "I mailed it already" means `already_submitted`.
- Extracting insurance plan names from natural language.
- Identifying contradiction, correction, hesitation, or ambiguity.
- Judging whether a final agent response actually communicates the intended outcome.

If no model API key is available, the evaluator should use conservative heuristics and return `UNCERTAIN` when answer meaning is not deterministically clear. Optional LLM checks may improve recall, but they must return structured evidence and should not override deterministic critical failures.

## Uncertainty Handling

Dimension statuses:

- `PASS`: no critical failures, required path is evidenced, and any supplied captured fields match the transcript.
- `FAIL`: at least one critical workflow or field-capture failure is supported by transcript evidence.
- `UNCERTAIN`: required evidence is missing, the caller answer is ambiguous, captured-field values are unavailable, or semantic interpretation is needed but not available.
- `NOT_EVALUATED`: the dimension is intentionally skipped because required input was not supplied, such as field accuracy in transcript-only mode.

The evaluator should prefer `UNCERTAIN` over fabricating caller intent or captured values. Each uncertain result must explain what additional input would resolve it.

When captured fields are supplied, missing required fields on the applicable observed path are critical completeness failures. Missing transcript evidence for a claimed field is `UNCERTAIN` unless there is a verified contradiction.

An explicitly supplied but empty captured-fields file is still full-evaluation mode. It should surface missing required captured fields rather than being treated as transcript-only mode.

## Proposed Result JSON Schema

```json
{
  "thread_id": "thread_01",
  "evaluation_mode": "transcript_only | full",
  "overall_status": "PASS | FAIL | UNCERTAIN",
  "workflow_status": "PASS | FAIL | UNCERTAIN",
  "field_accuracy_status": "PASS | FAIL | UNCERTAIN | NOT_EVALUATED",
  "task_completion_status": "PASS | FAIL | UNCERTAIN",
  "expected_disposition": "medi_cal_active | other_coverage_no_action | ... | null",
  "observed_terminal_action": "end_call | handoff | complete_renewal | null",
  "critical_failures": [
    {
      "code": "invalid_transition",
      "message": "Agent asked q5_choice before q5_packet was resolved.",
      "evidence": {"turn": 4, "text": "..."}
    }
  ],
  "warnings": [
    {
      "code": "repeated_question",
      "message": "Agent re-asked a previously answered question.",
      "evidence": {"turn": 2, "text": "..."}
    }
  ],
  "uncertainties": [
    {
      "code": "missing_captured_fields",
      "message": "No claimed captured-field values were supplied for comparison."
    }
  ],
  "checked_questions": [
    {
      "question_id": "q2_active",
      "asked": true,
      "caller_answer": "active",
      "confidence": "deterministic | heuristic | semantic"
    }
  ]
}
```

## Minimum Implementation Plan

Proposed Python modules:

- `loader.py`: load and validate the candidate JSON.
- `workflow.py`: parse questions, options, routes, and outcomes into a graph.
- `transcript.py`: normalize messages and identify agent questions.
- `classifiers.py`: deterministic and heuristic answer classifiers.
- `evaluator.py`: apply workflow rules and produce result objects.
- `reporter.py`: write JSON and human-readable summaries.
- `run.py`: CLI entry point accepting input path and output path.

The minimum executable should depend only on the Python standard library. It should read the candidate-facing JSON, evaluate every thread conservatively, and emit JSON results. It should not require `OPENAI_API_KEY`.

The CLI supports transcript-only mode and full mode when captured fields are supplied:

```bash
python3 q3/run.py --input q3/data/gym_agent_conversations.json --output q3/results.json
python3 q3/run.py --input q3/data/gym_agent_conversations.json --captured-fields q3/data/captured_fields.json --output q3/results.json
```

## Missing Inputs and Assumptions

Missing from the candidate-facing data:

- Structured captured-field values claimed by the agent.
- Per-thread final submitted disposition.
- Ground-truth labels suitable for candidate use.
- Audio, timing, or confidence signals.

Assumptions:

- `agent_config.engine_config` is the intended workflow definition.
- `messages[]` is the transcript to evaluate.
- Answer key and full-events files are excluded from implementation and success criteria.
- When structured captured fields are later provided, they become first-class inputs and should be checked against transcript evidence and workflow applicability.
