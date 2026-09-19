# Q2: Keeping a 40-Minute Agent on Course

## Problem Framing

A 130-question Medicaid renewal call should not rely on accumulated audio-native history as authoritative memory. By minute 35, the model may still be fluent while losing track of which questions were answered, which values were validated, and which branch is next.

The system must distinguish what the member said, what the model interpreted, what the application validated and persisted, and which question is authoritative. The model manages conversation; the controller owns application state.

Assumption: the system can send structured events between the Realtime session and backend services while keeping the same WebSocket open. I would not assume the session can be reset, prior audio history can be rewritten, or updated instructions remove old context.

## Architecture

A persistent GPT Realtime session handles audio, turn-taking, clarification, and structured answer proposals. The WebSocket remains open for the call. The model can speak naturally and propose actions, but speech alone does not prove an answer was captured.

An external workflow controller maintains the current question ID, applicable sequence, validation rules, branching dependencies, and allowable transitions. It determines when the workflow can advance.

An external answer store persists values, confirmation status, revisions, and evidence references.

The communication pattern is transactional: the model proposes an answer or action, the controller validates it, the answer store commits it, and the controller explicitly authorizes the next question. Until that authorization arrives, the model should stay within the current question, clarification, and structured answer-submission task. The model may still advance verbally, so unexpected spoken transitions must be detected and corrected rather than accepted as workflow progress.

## Model Context Versus External State

The model's context should be a working view of the current task, not the application record.

| Model active context | External authoritative state |
| --- | --- |
| Current question and conversational task | Full question registry and form schema |
| Relevant recent turns | Complete answer store |
| Minimal instructions for current section | Question dependency graph |
| Confirmed answers needed now | Validation and branching rules |
| Clarification instructions | Completed, pending, and unresolved questions |
| Compact state summary | Authoritative current question ID and workflow status |

The model should receive only the active question, relevant dependencies, confirmed facts, and local rules. Avoid injecting the complete form or every previous answer. The workflow remains outside the model where it can be audited, validated, and recovered deterministically.

## Accurate Answer Capture

An answer-capture transaction should look like this:

1. The member answers the current question.
2. The model proposes a structured value with question ID.
3. The controller verifies the question is current and applicable.
4. The controller validates type, format, dependency, and conflict rules.
5. The answer store persists the value, status, revision, and evidence.
6. The controller confirms the update and authorizes the next question.

For example, if the current question asks for household size and the member says, "It is me and my two kids," the model may propose `{question_id: "household_size", value: 3}`. Numeric parsing is not enough. The controller checks applicability, schema, support from the member's answer, and relevant form-specific rules. If information is insufficient, the field remains unresolved. If the member says, "Actually, my oldest moved out," the controller creates a revision rather than silently overwriting the previous value.

Not every answer needs confirmation. Straightforward, low-risk answers can be captured directly. Ambiguous, contradictory, or high-impact answers should be confirmed explicitly. An uncertain extraction should leave the field unresolved rather than fabricate a value.

## Context Management

I would use event-driven checkpoints rather than only time-based refreshes. Triggers include question completion, new section, answer correction, ambiguity, invalid transition, and drift.

At those boundaries, the controller should update the model's instructions with a compact state summary: current question, dependencies, confirmed answers, and minimal current-task instructions. Existing audio-native history continues accumulating; instruction updates guide future behavior but do not clear model context. If the model recalls outdated information from earlier turns, external state remains authoritative. Provider-supported truncation or compaction may help only if compatible with the persistent-session constraint and validated. Correctness must not depend on restarting the session or reconstructing historical answers from model memory.

## Information Recovery

When a later question depends on an earlier answer, recover information through structured lookup, not memory reconstruction. If Q095 requires Q012, the controller retrieves Q012 and supplies its confirmed value. If Q012 is missing, ambiguous, or superseded, the controller directs the model to clarify before proceeding.

Semantic retrieval may help conversational texture, but it should not replace structured retrieval of validated form values.

## What Breaks First

The first likely failure is synchronization between the live conversation and external workflow state. In speech-to-speech systems, overlapping audio, barge-in, delayed extraction, duplicate events, out-of-order updates, and corrections can all cause divergence.

Example: the member answers Q025. Before Q025 is validated and committed, the model begins asking Q026. The model now behaves as if the workflow advanced, but the controller still records Q025 as pending. Updating instructions alone cannot guarantee the model never verbally skips; the backend has to detect and repair it.

Safeguards include stable question IDs, explicit question-state transitions, controller-authorized progression, versioned and idempotent updates, persist-before-advance behavior, and final validation before submission.

## Detection and Recovery

I would monitor both structured workflow events and observed conversation. Detection signals include expected versus observed question ID, invalid transitions, repeated confirmed questions, missing required answers, conflicting values, failed validations, time since last transition, and model actions rejected by the controller. Where synchronized transcripts or equivalent speech observations are available, associate agent utterances with expected question IDs. If the model verbally advances to Q026 while Q025 is unresolved, record the unauthorized transition, prevent further advancement, and guide the model back. Transcript uncertainty may require clarification or more evidence rather than automatically declaring a confirmed failure.

On divergence, stop authoritative advancement, retrieve persisted state, identify the unresolved question, refresh current instructions, and ask for clarification only if needed. Continue over the existing WebSocket. If the controller can infer the repair, it can guide the model back naturally: "I want to make sure I captured that correctly before we move on."

## Summary

The reliable architecture is not a smarter prompt alone. The Realtime model provides natural conversation; the external controller determines workflow progression; the answer store preserves validated information. As audio-native history grows, correctness depends on explicit state transitions, validated answers, and recoverable records. It still needs realistic testing, but drift becomes detectable and recoverable instead of silently corrupting the application.
