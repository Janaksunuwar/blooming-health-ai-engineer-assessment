# Q3: Evaluation Harness

This directory contains the runnable Python evaluation harness for the healthcare workflow assessment.

## Evaluation Philosophy

The evaluator separates four dimensions:

- `workflow_status`: whether the transcript follows the configured question graph.
- `field_accuracy_status`: whether supplied captured fields match transcript evidence.
- `task_completion_status`: whether the agent reaches the configured terminal responsibility.
- conversation warnings: noncritical quality issues such as repeated prompts.

Overall aggregation is conservative:

- Verified critical failure => `FAIL`.
- No critical failure but required evidence missing => `UNCERTAIN`.
- Required checks pass => `PASS`.

In transcript-only mode, captured-field accuracy is `NOT_EVALUATED`. A transcript-only `PASS` is not proof that submitted application fields are accurate.

## Input Format

Run against the candidate-facing conversation dataset:

```bash
python3 q3/run.py \
  --input q3/data/gym_agent_conversations.json \
  --output q3/results.json
```

The input must include:

- `agent_config.engine_config.items`
- `agent_config.engine_config.outcomes`
- `threads[]`
- `threads[].messages[]` with `role`, `turn`, and `text`

The answer key and full-events files are interviewer-side artifacts and are not used.

## Optional Captured Fields

When claimed captured fields are available, pass:

```bash
python3 q3/run.py \
  --input q3/data/gym_agent_conversations.json \
  --captured-fields q3/data/captured_fields.json \
  --output q3/results.json
```

Expected captured-fields shape:

```json
{
  "threads": {
    "thread_01": {
      "fields": {
        "q1_intent": "Yes",
        "q2_active": "Active"
      }
    }
  }
}
```

When captured fields are absent, `field_accuracy_status` is `NOT_EVALUATED` and the report includes a missing-input uncertainty.

If `--captured-fields` is supplied with an empty object, the evaluator runs in full mode and reports missing required captured fields instead of silently falling back to transcript-only mode.

## Deterministic and Semantic Boundaries

The current implementation uses the Python standard library only. It deterministically checks schema, question matching, conservative answer classification, configured transitions, terminal outcomes, repeated questions, and optional captured-field validation.

Natural-language interpretation is intentionally conservative. The classifier handles a small set of reliable phrases, including common negation patterns, and returns `UNCERTAIN` for ambiguous or contradictory answers. Optional semantic checks could be added behind a separate interface and should read `OPENAI_API_KEY` from the environment, but the evaluator runs without an API key.

The evaluator also retains explicitly volunteered information, such as a caller answering several later questions in one turn. Volunteered information can support transcript evidence, but it does not mark those later questions as actually asked or prove the application captured the value.

For `_complete` routes such as "let's get your renewal started", `complete_renewal` means the configured triage path has reached the point where renewal work should begin. It is not proof that downstream renewal execution finished.

## Known Limitations

- Paraphrased questions may be missed unless close to configured wording.
- Free-text answer classification is heuristic and conservative.
- Transcript-only mode cannot verify actual captured application fields.
- Promised handoffs or callbacks are treated as transcript evidence of the triage outcome, not proof that downstream execution occurred.
