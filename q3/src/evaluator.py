"""Deterministic transcript-first evaluator for Q3."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .workflow import Question, Route, parse_workflow

PASS = "PASS"
FAIL = "FAIL"
UNCERTAIN = "UNCERTAIN"
NOT_EVALUATED = "NOT_EVALUATED"


def evaluate_dataset(
    dataset: dict[str, Any], captured_fields: dict[str, Any] | None = None
) -> dict[str, Any]:
    workflow = parse_workflow(dataset["agent_config"])
    mode = "full" if captured_fields is not None else "transcript_only"
    results = [
        evaluate_thread(thread, workflow, _thread_claims(captured_fields, thread["thread_id"]), mode)
        for thread in dataset["threads"]
    ]
    return {
        "evaluation_mode": mode,
        "input_summary": {
            "thread_count": len(dataset["threads"]),
            "captured_fields_supplied": captured_fields is not None,
            "interviewer_artifacts_used": False,
        },
        "results": results,
    }


def evaluate_thread(
    thread: dict[str, Any],
    workflow: dict[str, Any],
    captured_claims: dict[str, Any] | None = None,
    mode: str = "transcript_only",
) -> dict[str, Any]:
    questions: dict[str, Question] = workflow["questions"]
    messages = thread["messages"]
    current: tuple[str, str] = ("question", "q1_intent")
    last_question: str | None = None
    asked: list[str] = []
    answers: dict[str, dict[str, Any]] = {}
    volunteered: dict[str, dict[str, Any]] = {}
    critical: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    uncertainties: list[dict[str, Any]] = []
    observed_disposition: str | None = None
    expected_disposition: str | None = None
    observed_behavior: list[dict[str, Any]] = []

    if mode == "transcript_only":
        uncertainties.append(_issue("missing_captured_fields", "Captured-field input was not supplied."))

    for index, message in enumerate(messages):
        role = message.get("role")
        text = message.get("text", "")
        if role == "agent":
            qid = identify_question(text, questions)
            disposition = identify_disposition(text, workflow["outcomes"])
            complete = is_completion_language(text)
            if has_leaked_internal_text(text):
                critical.append(
                    _issue("leaked_internal_text", "Agent turn contains leaked internal template text.", message)
                )
            if qid:
                if qid in asked:
                    warnings.append(_issue("repeated_question", f"Agent repeated {qid}.", message))
                if current[0] == "question" and qid != current[1]:
                    expected_qid = current[1]
                    if expected_qid in volunteered:
                        _record_answer(answers, expected_qid, volunteered[expected_qid], source="volunteered_before_question")
                        route = questions[expected_qid].routes[answers[expected_qid]["scenario_id"]]
                        current = (route.target_kind, route.target_id)
                        warnings.append(
                            _issue(
                                "volunteered_answer_used_for_path",
                                f"Caller volunteered {expected_qid}; agent did not ask it before moving to {qid}.",
                                volunteered[expected_qid]["evidence"],
                            )
                        )
                    if current[0] == "question" and qid != current[1]:
                        unresolved = any(
                            issue["code"] == "ambiguous_caller_answer"
                            and issue.get("question_id") == current[1]
                            for issue in uncertainties
                        )
                        if unresolved:
                            issue = _issue(
                                "progressed_after_unresolved_answer",
                                f"Agent asked {qid} while {current[1]} remained unresolved.",
                                message,
                            )
                            issue["question_id"] = current[1]
                            uncertainties.append(issue)
                            current = ("question", qid)
                        else:
                            critical.append(
                                _issue(
                                    "invalid_transition",
                                    f"Agent asked {qid} while expected question was {current[1]}.",
                                    message,
                                )
                            )
                if current[0] != "question":
                    critical.append(
                        _issue(
                            "question_after_terminal",
                            f"Agent asked {qid} after expected terminal state {current[1]}.",
                            message,
                        )
                    )
                asked.append(qid)
                observed_behavior.append({"turn": message.get("turn"), "event": "asked_question", "question_id": qid})
                last_question = qid
                if current[0] == "question" and qid == current[1] and qid in volunteered:
                    issue = _issue(
                        "volunteered_answer_needs_confirmation",
                        f"Caller volunteered an answer to {qid} before the agent asked it.",
                        volunteered[qid]["evidence"],
                    )
                    issue["question_id"] = qid
                    warnings.append(issue)
            elif disposition or complete:
                observed_disposition = disposition or "complete_renewal"
                observed_behavior.append(
                    {"turn": message.get("turn"), "event": "terminal_language", "disposition": observed_disposition}
                )
                if current[0] == "question":
                    critical.append(
                        _issue(
                            "premature_terminal",
                            f"Agent reached terminal language before resolving {current[1]}.",
                            message,
                        )
                    )
                elif current[1] != observed_disposition:
                    critical.append(
                        _issue(
                            "incorrect_terminal_disposition",
                            f"Expected {current[1]} but observed {observed_disposition}.",
                            message,
                        )
                    )
        elif role == "caller" and last_question:
            for volunteered_qid, volunteered_answer in extract_volunteered_answers(text, questions).items():
                volunteered.setdefault(volunteered_qid, {**volunteered_answer, "evidence": _evidence(message)})
            question = questions[last_question]
            classification = classify_answer(question, text)
            if classification["status"] == PASS:
                route = question.routes[classification["scenario_id"]]
                _record_answer(answers, last_question, {**classification, "evidence": _evidence(message)}, source="asked_response")
                current = (route.target_kind, route.target_id)
                if current[0] in {"disposition", "complete"}:
                    expected_disposition = current[1]
                last_question = None
            else:
                issue = _issue(
                    "ambiguous_caller_answer",
                    f"Could not deterministically classify answer to {last_question}.",
                    message,
                )
                issue["question_id"] = last_question
                uncertainties.append(issue)
        elif role == "caller":
            for volunteered_qid, volunteered_answer in extract_volunteered_answers(text, questions).items():
                volunteered.setdefault(volunteered_qid, {**volunteered_answer, "evidence": _evidence(message)})

    if observed_disposition is None:
        uncertainties.append(_issue("missing_terminal_evidence", "No terminal disposition was observed."))
    applicable_path = applicable_workflow_path(questions, answers)
    field_status, field_issues, field_warnings, field_uncertainties = evaluate_captured_fields(
        captured_claims, questions, answers, applicable_path
    )
    critical.extend(field_issues)
    warnings.extend(field_warnings)
    uncertainties.extend(field_uncertainties)

    workflow_status = FAIL if _workflow_failures(critical) else (UNCERTAIN if _workflow_uncertainties(uncertainties) else PASS)
    task_status = _task_status(critical, uncertainties, observed_disposition)
    overall = _aggregate(workflow_status, field_status, task_status, critical)
    return {
        "thread_id": thread["thread_id"],
        "evaluation_mode": mode,
        "overall_status": overall,
        "workflow_status": workflow_status,
        "field_accuracy_status": field_status,
        "task_completion_status": task_status,
        "expected_disposition": expected_disposition,
        "observed_disposition": observed_disposition,
        "critical_failures": critical,
        "warnings": warnings,
        "uncertainties": uncertainties,
        "supporting_evidence": {
            "applicable_workflow_path": applicable_path,
            "observed_agent_behavior": observed_behavior,
            "classified_answers": answers,
            "volunteered_information": volunteered,
            "asked_questions": asked,
        },
        "recommended_engineering_fixes": _fixes(critical, uncertainties, warnings),
    }


def evaluate_captured_fields(
    claims: dict[str, Any] | None,
    questions: dict[str, Question],
    answers: dict[str, dict[str, Any]],
    applicable_path: list[str],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if claims is None:
        return NOT_EVALUATED, [], [], []
    critical: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    uncertainties: list[dict[str, Any]] = []
    fields = claims.get("fields", claims)
    if not isinstance(fields, dict):
        issue = _issue("invalid_captured_fields", "Captured fields must be an object.")
        issue["evidence"] = {"captured_fields_type": type(fields).__name__}
        return FAIL, [issue], [], []
    for required_id in applicable_path:
        if required_id not in fields:
            issue = _issue("missing_required_captured_field", f"Required captured field {required_id} is missing.")
            issue["evidence"] = answers.get(required_id, {}).get(
                "evidence",
                {"field_id": required_id, "source": "applicable_workflow_path"},
            )
            critical.append(issue)
    for field_id, claimed in fields.items():
        if field_id not in questions:
            warnings.append(_issue("unknown_captured_field", f"Unknown captured field {field_id}."))
            continue
        value_error = validate_claimed_value(questions[field_id], claimed)
        if value_error:
            issue = _issue("invalid_captured_value", value_error)
            issue["evidence"] = {"field_id": field_id, "captured_value": claimed}
            critical.append(issue)
            continue
        if field_id not in answers:
            uncertainties.append(
                _issue("missing_transcript_evidence", f"No transcript evidence found for {field_id}.")
            )
            continue
        observed = answers[field_id]["value"]
        claimed_canonical = canonical_field_value(questions[field_id], claimed)
        observed_canonical = canonical_field_value(questions[field_id], observed)
        if claimed_canonical is None or observed_canonical is None:
            uncertainties.append(
                _issue(
                    "uncertain_field_equivalence",
                    f"Could not establish semantic equivalence for captured field {field_id}.",
                    answers[field_id]["evidence"],
                )
            )
            continue
        if claimed_canonical != observed_canonical:
            critical.append(
                _issue(
                    "captured_field_contradiction",
                    f"Captured {field_id}={claimed!r} contradicts transcript-supported value {observed!r}.",
                    answers[field_id]["evidence"],
                )
            )
    if critical:
        return FAIL, critical, warnings, uncertainties
    if uncertainties:
        return UNCERTAIN, critical, warnings, uncertainties
    return PASS, critical, warnings, uncertainties


def applicable_workflow_path(questions: dict[str, Question], answers: dict[str, dict[str, Any]]) -> list[str]:
    path: list[str] = []
    current = "q1_intent"
    seen: set[str] = set()
    while current in questions and current not in seen:
        seen.add(current)
        path.append(current)
        answer = answers.get(current)
        if not answer:
            break
        route = questions[current].routes.get(answer["scenario_id"])
        if not route or route.target_kind != "question":
            break
        current = route.target_id
    return path


def validate_claimed_value(question: Question, value: Any) -> str | None:
    canonical = canonical_field_value(question, value)
    if canonical is None:
        return f"Captured {question.id}={value!r} is not an allowed value."
    return None


def canonical_field_value(question: Question, value: Any) -> str | None:
    normalized = _norm_value(value)
    if question.answer_type == "boolean":
        if isinstance(value, bool):
            return str(value).lower()
        if normalized in {"true", "yes"}:
            return "true"
        if normalized in {"false", "no"}:
            return "false"
        return None
    for option in question.options:
        if normalized == _norm_value(option):
            return _norm_value(option)
    for scenario_id, route in question.routes.items():
        aliases = {scenario_id, scenario_id.replace("_", " ")}
        if normalized in {_norm_value(alias) for alias in aliases}:
            if question.options:
                mapped = scenario_to_value(question, scenario_id)
                return _norm_value(mapped) if mapped is not None else _norm_value(scenario_id)
            return _norm_value(scenario_id)
    if question.answer_type == "text":
        return normalized
    return None


def scenario_to_value(question: Question, scenario_id: str) -> Any:
    mapping = {
        "yes": "Yes",
        "not_interested": "Not interested",
        "active": "Active",
        "inactive": "Not active or unsure",
        "already_submitted": "Already submitted",
        "still_has": "Still have it",
        "no_or_lost": "No or lost it",
        "in_person": "In-person appointment",
        "by_phone": "Complete by phone now",
    }
    value = mapping.get(scenario_id)
    if value and (not question.options or _norm_value(value) in {_norm_value(option) for option in question.options}):
        return value
    return None


def identify_question(text: str, questions: dict[str, Question]) -> str | None:
    normalized = normalize(text)
    best: tuple[str | None, float] = (None, 0.0)
    for qid, question in questions.items():
        qtext = normalize(question.text)
        if qtext and qtext in normalized:
            return qid
        ratio = SequenceMatcher(None, qtext, normalized).ratio()
        if ratio > best[1]:
            best = (qid, ratio)
    return best[0] if best[1] >= 0.82 else None


def identify_disposition(text: str, outcomes: dict[str, dict[str, Any]]) -> str | None:
    ntext = normalize(text)
    checks = {
        "medi_cal_active": ["great news", "nothing you need to do"],
        "other_coverage_no_action": ["already covered", "nothing you need to do"],
        "escalated_chw_out_of_county": ["county by county", "follow up"],
        "escalated_chw_status_check": ["already submitted", "check on its status"],
        "escalated_chw_appointment": ["schedule", "reach out"],
        "declined_privacy_callback": ["careful with your information"],
        "declined_renewal": ["thanks for letting me know", "take care"],
    }
    for outcome_id in outcomes:
        tokens = checks.get(outcome_id, [])
        if tokens and all(token in ntext for token in tokens):
            return outcome_id
    return None


def is_completion_language(text: str) -> bool:
    ntext = normalize(text)
    return "let s get your renewal started" in ntext or "let s get started" in ntext


def has_leaked_internal_text(text: str) -> bool:
    return "(waiting for your response.)" in text.lower()


def classify_answer(question: Question, text: str) -> dict[str, Any]:
    ntext = normalize(text)
    if _ambiguous(ntext):
        return {"status": UNCERTAIN}
    classifier = {
        "q1_intent": _classify_intent,
        "q2_active": _classify_active,
        "q3_coverage": _classify_coverage,
        "q3_plan": lambda value: _classify_plan(value, question),
        "q4_residency": _classify_residency,
        "q5_packet": _classify_packet,
        "q5_choice": _classify_packet_choice,
        "decline": _classify_decline,
    }.get(question.id)
    if not classifier:
        return {"status": UNCERTAIN}
    scenario_id, value = classifier(ntext)
    if scenario_id in question.routes:
        return {"status": PASS, "scenario_id": scenario_id, "value": value}
    return {"status": UNCERTAIN}


def extract_volunteered_answers(text: str, questions: dict[str, Question]) -> dict[str, dict[str, Any]]:
    volunteered: dict[str, dict[str, Any]] = {}
    for qid, question in questions.items():
        if qid in {"q1_intent", "decline"}:
            continue
        classification = classify_answer(question, text)
        if classification["status"] == PASS:
            volunteered[qid] = classification
    return volunteered


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _classify_intent(text: str) -> tuple[str | None, Any]:
    if any(token in text for token in ("yes", "please", "like your help", "like some help", "like help", "need help")):
        return "yes", "Yes"
    if any(token in text for token in ("not interested", "no thanks", "decline")):
        return "not_interested", "Not interested"
    return None, None


def _classify_active(text: str) -> tuple[str | None, Any]:
    if _has_any_phrase(text, ("not active", "not currently active", "inactive", "don t think it s active", "do not think it s active", "isn t active", "is not active", "unsure")):
        return "inactive", "Not active or unsure"
    if _has_negated_word(text, "active"):
        return "inactive", "Not active or unsure"
    if _has_any_phrase(text, ("definitely have active", "have active", "active coverage", "still covered", "definitely still covered")):
        return "active", "Active"
    return None, None


def _classify_coverage(text: str) -> tuple[str | None, Any]:
    plans = ("kaiser", "tricare", "covered california", "private plan", "work", "school")
    if _has_any_phrase(text, ("no other", "don t have any other", "do not have any other", "no health insurance", "no insurance")):
        return "false", False
    if any(_word_or_phrase(text, plan) for plan in plans):
        return "true", True
    return None, None


def _classify_plan(text: str, question: Question) -> tuple[str | None, Any]:
    for option in question.options:
        option_norm = normalize(option)
        if option_norm == "other":
            if _has_any_phrase(text, ("other plan", "another plan", "different plan")) and not _has_any_phrase(text, ("other insurance", "no other")):
                return "__close__", option
            continue
        if _word_or_phrase(text, option_norm):
            return "__close__", option
    return None, None


def _classify_residency(text: str) -> tuple[str | None, Any]:
    if _has_any_phrase(text, ("used to live", "used to be in san diego")):
        return None, None
    if _has_any_phrase(text, ("moved out", "not in san diego", "out of san diego", "don t live in san diego", "do not live in san diego")):
        return "false", False
    if _has_any_phrase(
        text,
        (
            "still live in san diego",
            "still live here in san diego",
            "still in san diego",
            "still in san diego county",
            "still here in san diego",
            "live here in san diego",
            "live in san diego county",
        ),
    ) or text == "yes":
        return "true", True
    return None, None


def _classify_packet(text: str) -> tuple[str | None, Any]:
    negative_submission = _has_any_phrase(
        text,
        ("haven t sent", "have not sent", "didn t send", "did not send", "not submitted", "haven t submitted"),
    )
    if _has_any_phrase(text, ("still have", "right here", "have the yellow packet", "packet right here")):
        return "still_has", "Still have it"
    if not negative_submission and _has_any_phrase(text, ("already submitted", "mailed it back", "mailed it", "sent it in", "submitted it")):
        return "already_submitted", "Already submitted"
    if _has_any_phrase(text, ("never got", "never received", "lost it", "didn t receive", "did not receive", "didn t get", "did not get", "no packet")) or re.search(r"\bnever\b(?:\s+\w+){0,3}\s+\bgot\b", text):
        return "no_or_lost", "No or lost it"
    return None, None


def _classify_packet_choice(text: str) -> tuple[str | None, Any]:
    if _has_any_phrase(text, ("not interested", "don t want", "do not want", "no phone", "not by phone")):
        return None, None
    if "in person" in text or "appointment" in text:
        return "in_person", "In-person appointment"
    if _has_any_phrase(text, ("by phone", "over the phone", "on the phone")) and _has_any_phrase(
        text, ("complete", "finish", "do it", "do this", "renewal")
    ):
        return "by_phone", "Complete by phone now"
    if _has_any_phrase(text, ("finish it", "complete it")):
        return "by_phone", "Complete by phone now"
    return None, None


def _classify_decline(text: str) -> tuple[str | None, Any]:
    if "kaiser" in text or "covered" in text or "other insurance" in text:
        return "reveals_other_coverage", text
    if "active" in text:
        return "reveals_active", text
    if "moved out" in text or "not in san diego" in text:
        return "reveals_out_of_county", text
    if "privacy" in text or "immigration" in text:
        return "privacy_concern", text
    if "my own" in text or "myself" in text:
        return "self_submit", text
    if "not interested" in text or "no thanks" in text:
        return "not_interested", text
    return None, None


def _ambiguous(text: str) -> bool:
    if any(token in text for token in ("maybe", "not sure", "i guess", "i don t know")):
        return True
    return _contradictory(text)


def _contradictory(text: str) -> bool:
    return (
        _has_negated_word(text, "active") and _has_any_phrase(text, ("have active", "active coverage", "still covered"))
    ) or (
        _has_any_phrase(text, ("still have", "right here")) and _has_any_phrase(text, ("lost it", "never got"))
    )


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_word_or_phrase(text, phrase) for phrase in phrases)


def _word_or_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _has_negated_word(text: str, word: str) -> bool:
    return re.search(rf"\b(no|not|don t|do not|doesn t|does not|isn t|is not|haven t|have not)\b(?:\s+\w+){{0,4}}\s+{word}\b", text) is not None


def _thread_claims(captured_fields: dict[str, Any] | None, thread_id: str) -> dict[str, Any] | None:
    if captured_fields is None:
        return None
    return captured_fields.get("threads", {}).get(thread_id, {})


def _aggregate(workflow: str, fields: str, task: str, critical: list[dict[str, Any]]) -> str:
    if critical or FAIL in (workflow, fields, task):
        return FAIL
    if UNCERTAIN in (workflow, task) or fields == UNCERTAIN:
        return UNCERTAIN
    return PASS


def _task_status(critical: list[dict[str, Any]], uncertainties: list[dict[str, Any]], observed: str | None) -> str:
    if _workflow_failures(critical):
        return FAIL
    if observed == "complete_renewal":
        return UNCERTAIN
    if observed is None or any(issue["code"] == "missing_terminal_evidence" for issue in uncertainties):
        return UNCERTAIN
    return PASS


def _workflow_failures(critical: list[dict[str, Any]]) -> bool:
    return any(not issue["code"].startswith("captured_field") and "captured" not in issue["code"] for issue in critical)


def _workflow_uncertainties(uncertainties: list[dict[str, Any]]) -> bool:
    return any(issue["code"] != "missing_captured_fields" for issue in uncertainties)


def _issue(code: str, message: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    issue = {"code": code, "message": message}
    if evidence:
        issue["evidence"] = _evidence(evidence)
    return issue


def _evidence(message: dict[str, Any]) -> dict[str, Any]:
    return {"turn": message.get("turn"), "role": message.get("role"), "text": message.get("text")}


def _record_answer(
    answers: dict[str, dict[str, Any]], qid: str, classification: dict[str, Any], source: str
) -> None:
    answers[qid] = {
        "scenario_id": classification["scenario_id"],
        "value": classification["value"],
        "source": source,
        "evidence": classification["evidence"],
    }


def _fixes(
    critical: list[dict[str, Any]], uncertainties: list[dict[str, Any]], warnings: list[dict[str, Any]]
) -> list[str]:
    fixes: list[str] = []
    codes = {issue["code"] for issue in critical + uncertainties + warnings}
    if "invalid_transition" in codes or "question_after_terminal" in codes:
        fixes.append("Review workflow state management and next-question authorization.")
    if "premature_terminal" in codes:
        fixes.append("Ensure the agent resolves the current workflow question before closing or announcing completion.")
    if "leaked_internal_text" in codes:
        fixes.append("Review template rendering — internal placeholder text should never reach agent output.")
    if "incorrect_terminal_disposition" in codes:
        fixes.append("Review terminal-disposition selection against the configured workflow route.")
    if "missing_captured_fields" in codes:
        fixes.append("Provide claimed captured fields to evaluate field accuracy.")
    if "ambiguous_caller_answer" in codes:
        fixes.append("Route ambiguous answers through clarification or semantic review.")
    if "captured_field_contradiction" in codes:
        fixes.append("Inspect extraction logic for the named captured field.")
    if "missing_required_captured_field" in codes:
        fixes.append("Ensure the application record includes every required field for the applicable workflow path.")
    if "missing_transcript_evidence" in codes:
        fixes.append("Provide transcript evidence or semantic review for the claimed captured field.")
    if "repeated_question" in codes:
        fixes.append("Add guards against re-asking answered questions.")
    if "volunteered_answer_used_for_path" in codes or "volunteered_answer_needs_confirmation" in codes:
        fixes.append("Confirm or persist volunteered information before relying on it for workflow progression.")
    return fixes


def _norm_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return normalize(str(value))
