from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluator import FAIL, NOT_EVALUATED, PASS, UNCERTAIN, evaluate_dataset
from src.loader import load_captured_fields


def dataset(messages):
    return {
        "agent_config": {
            "engine_config": {
                "items": [
                    {
                        "id": "q1_intent",
                        "label": "Q1 Intent",
                        "questions": [
                            {
                                "id": "a",
                                "text": "First, would you like our help renewing your Medi-Cal right now, over the phone?",
                                "type": "choice",
                                "options": ["Yes", "Not interested"],
                                "scenarios": [
                                    {"id": "yes", "goto": "item_q2_active:question_a"},
                                    {"id": "not_interested", "goto": "item_decline:question_a"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q2_active",
                        "label": "Q2 Active Medi-Cal",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?",
                                "type": "choice",
                                "options": ["Active", "Not active or unsure"],
                                "scenarios": [
                                    {"id": "active", "disposition": "medi_cal_active"},
                                    {"id": "inactive", "goto": "item_q3_coverage:question_a"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q3_coverage",
                        "label": "Q3 Other Coverage",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?",
                                "type": "boolean",
                                "scenarios": [
                                    {"id": "true", "goto": "item_q3_plan:question_a"},
                                    {"id": "false", "goto": "item_q4_residency:question_a"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q3_plan",
                        "label": "Q3 Which Plan",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Which plan is that?",
                                "type": "choice",
                                "options": ["Kaiser Permanente", "Other"],
                                "scenarios": [
                                    {"id": "__close__", "disposition": "other_coverage_no_action"}
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q4_residency",
                        "label": "Q4 Residency",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Do you still live in San Diego County?",
                                "type": "boolean",
                                "scenarios": [
                                    {"id": "true", "goto": "item_q5_packet:question_a"},
                                    {"id": "false", "disposition": "escalated_chw_out_of_county"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q5_packet",
                        "label": "Q5 Yellow Packet",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Did you receive the yellow renewal packet from the county, and do you still have it?",
                                "type": "choice",
                                "options": ["Already submitted", "Still have it", "No or lost it"],
                                "scenarios": [
                                    {"id": "already_submitted", "disposition": "escalated_chw_status_check"},
                                    {"id": "still_has", "goto": "item_q5_choice:question_a"},
                                    {"id": "no_or_lost", "goto": "_complete"},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "q5_choice",
                        "label": "Q5 Packet Choice",
                        "questions": [
                            {
                                "id": "a",
                                "text": "Since you still have the county's packet, I can help by phone or set up an in-person appointment. Which would you prefer?",
                                "type": "choice",
                                "options": ["In-person appointment", "Complete by phone now"],
                                "scenarios": [
                                    {"id": "in_person", "disposition": "escalated_chw_appointment"},
                                    {"id": "by_phone", "goto": "_complete"},
                                ],
                            }
                        ],
                    },
                ],
                "outcomes": [
                    {
                        "id": "medi_cal_active",
                        "label": "Medi-Cal active",
                        "next_action": "end_call",
                    },
                    {
                        "id": "other_coverage_no_action",
                        "label": "Other coverage",
                        "next_action": "end_call",
                    },
                    {
                        "id": "escalated_chw_out_of_county",
                        "label": "Out of county",
                        "next_action": "handoff",
                    },
                    {
                        "id": "escalated_chw_status_check",
                        "label": "Status check",
                        "next_action": "handoff",
                    },
                    {
                        "id": "escalated_chw_appointment",
                        "label": "Appointment",
                        "next_action": "handoff",
                    },
                ],
            }
        },
        "threads": [{"thread_id": "thread_01", "messages": messages}],
    }


def msg(role, text, turn=0):
    return {"role": role, "text": text, "turn": turn}


class EvaluatorTest(unittest.TestCase):
    def result(self, messages, captured=None):
        return evaluate_dataset(dataset(messages), captured_fields=captured)["results"][0]

    def test_valid_workflow_completion(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes, please."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "I definitely have active coverage."),
                msg("agent", "That's great news, there is nothing you need to do right now."),
            ]
        )
        self.assertEqual(result["workflow_status"], PASS)
        self.assertEqual(result["field_accuracy_status"], NOT_EVALUATED)

    def test_incorrect_terminal_disposition(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "I have active coverage."),
                msg("agent", "Thanks, since you're already covered, there is nothing you need to do."),
            ]
        )
        self.assertEqual(result["overall_status"], FAIL)

    def test_missing_required_information(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
            ]
        )
        self.assertEqual(result["task_completion_status"], UNCERTAIN)

    def test_ambiguous_caller_response(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Maybe, I am not sure."),
            ]
        )
        self.assertTrue(any(issue["code"] == "ambiguous_caller_answer" for issue in result["uncertainties"]))

    def test_repeated_question(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
            ]
        )
        self.assertTrue(any(issue["code"] == "repeated_question" for issue in result["warnings"]))

    def test_captured_field_contradiction(self):
        captured = {"threads": {"thread_01": {"fields": {"q1_intent": "Not interested"}}}}
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
            ],
            captured=captured,
        )
        self.assertEqual(result["field_accuracy_status"], FAIL)

    def test_missing_captured_field_input(self):
        result = self.result([])
        self.assertEqual(result["field_accuracy_status"], NOT_EVALUATED)
        self.assertTrue(any(issue["code"] == "missing_captured_fields" for issue in result["uncertainties"]))

    def test_transcript_ends_before_action_established(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
            ]
        )
        self.assertEqual(result["task_completion_status"], UNCERTAIN)

    def test_active_negation_routes_inactive(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "No, I don't think it's active right now."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
            ]
        )
        self.assertFalse(result["critical_failures"])
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q2_active"]["scenario_id"],
            "inactive",
        )

    def test_unsubmitted_packet_does_not_mean_submitted(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "No, not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "Yes, I still live in San Diego."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
                msg("caller", "I haven't sent it in yet. I still have the packet."),
                msg("agent", "Since you still have the county's packet, I can help by phone or set up an in-person appointment. Which would you prefer?"),
            ]
        )
        self.assertFalse(result["critical_failures"])
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q5_packet"]["scenario_id"],
            "still_has",
        )

    def test_packet_choice_branch_from_still_has_packet(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "Yes."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
                msg("caller", "I still have it."),
                msg("agent", "Since you still have the county's packet, I can help by phone or set up an in-person appointment. Which would you prefer?"),
            ]
        )
        self.assertFalse(result["critical_failures"])

    def test_contradictory_response_stays_uncertain(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "I have active coverage, but I don't think it's active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
            ]
        )
        self.assertFalse(result["critical_failures"])
        self.assertTrue(any(issue["code"] == "ambiguous_caller_answer" for issue in result["uncertainties"]))

    def test_missing_required_captured_field(self):
        captured = {"threads": {"thread_01": {"fields": {"q1_intent": "Yes"}}}}
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "I have active coverage."),
                msg("agent", "That's great news, there is nothing you need to do right now."),
            ],
            captured=captured,
        )
        self.assertTrue(any(issue["code"] == "missing_required_captured_field" for issue in result["critical_failures"]))

    def test_missing_transcript_evidence_is_uncertain_not_contradiction(self):
        captured = {"threads": {"thread_01": {"fields": {"q1_intent": "Yes", "q2_active": "Active"}}}}
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
            ],
            captured=captured,
        )
        self.assertEqual(result["field_accuracy_status"], UNCERTAIN)
        self.assertTrue(any(issue["code"] == "missing_transcript_evidence" for issue in result["uncertainties"]))

    def test_multiple_answers_retained_without_marking_questions_asked(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes. I am not active, I have no other insurance, I still live in San Diego, I still have the packet, and I want to do it by phone."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
            ]
        )
        evidence = result["supporting_evidence"]
        self.assertIn("q3_coverage", evidence["volunteered_information"])
        self.assertNotIn("q3_coverage", evidence["asked_questions"])

    def test_workflow_failure_makes_task_completion_fail(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("agent", "That's great news, there is nothing you need to do right now."),
            ]
        )
        self.assertEqual(result["task_completion_status"], FAIL)

    def test_ambiguous_response_does_not_fabricate_invalid_transition(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Maybe, I am not sure."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
            ]
        )
        self.assertFalse(any(issue["code"] == "invalid_transition" for issue in result["critical_failures"]))
        self.assertTrue(any(issue["code"] == "progressed_after_unresolved_answer" for issue in result["uncertainties"]))

    def test_affirmative_san_diego_residency(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "Yeah, I still live here in San Diego."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
            ]
        )
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q4_residency"]["scenario_id"],
            "true",
        )

    def test_negative_san_diego_residency(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "I moved out of San Diego County."),
            ]
        )
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q4_residency"]["scenario_id"],
            "false",
        )

    def test_used_to_live_in_san_diego_not_current_residency(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "I used to live in San Diego."),
            ]
        )
        self.assertNotIn("q4_residency", result["supporting_evidence"]["classified_answers"])

    def test_never_received_yellow_packet(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "I still live here in San Diego."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
                msg("caller", "I never actually got it in the mail."),
            ]
        )
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q5_packet"]["scenario_id"],
            "no_or_lost",
        )

    def test_already_submitted_yellow_packet(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "Still in San Diego County."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
                msg("caller", "I already mailed it back."),
            ]
        )
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q5_packet"]["scenario_id"],
            "already_submitted",
        )

    def test_generic_other_insurance_not_plan_other(self):
        result = self.result(
            [
                msg("caller", "I don't have any other insurance."),
            ]
        )
        self.assertNotIn("q3_plan", result["supporting_evidence"]["volunteered_information"])

    def test_negative_phone_renewal_preference_not_by_phone(self):
        result = self.result(
            [
                msg("caller", "I'm not interested in renewing over the phone right now."),
            ]
        )
        self.assertNotIn("q5_choice", result["supporting_evidence"]["volunteered_information"])

    def test_empty_captured_fields_is_full_mode(self):
        report = evaluate_dataset(dataset([]), captured_fields={})
        result = report["results"][0]
        self.assertEqual(report["evaluation_mode"], "full")
        self.assertNotEqual(result["field_accuracy_status"], NOT_EVALUATED)

    def test_empty_captured_fields_file_loads_as_empty_threads(self):
        path = Path("/tmp/empty_captured_fields.json")
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(load_captured_fields(path), {"threads": {}})

    def test_equivalent_captured_field_representations(self):
        captured = {"threads": {"thread_01": {"fields": {"q1_intent": "yes", "q2_active": "active"}}}}
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "I have active coverage."),
                msg("agent", "That's great news, there is nothing you need to do right now."),
            ],
            captured=captured,
        )
        self.assertEqual(result["field_accuracy_status"], PASS)

    def test_thread_02_style_packet_response_is_resolved(self):
        result = self.result(
            [
                msg("agent", "First, would you like our help renewing your Medi-Cal right now, over the phone?"),
                msg("caller", "Yes."),
                msg("agent", "Our records show your Medi-Cal may not be active right now. Can you confirm, do you currently have active Medi-Cal coverage?"),
                msg("caller", "Not active."),
                msg("agent", "Do you currently have any other health insurance through work, school, Kaiser, TriCare, Covered California, or a private plan?"),
                msg("caller", "No other insurance."),
                msg("agent", "Do you still live in San Diego County?"),
                msg("caller", "Yeah, I still live here in San Diego."),
                msg("agent", "Did you receive the yellow renewal packet from the county, and do you still have it?"),
                msg("caller", "No, I never actually got it in the mail, so I don't have it."),
                msg("agent", "No problem, let's get your renewal started."),
            ]
        )
        self.assertFalse(any(issue["code"] == "premature_terminal" for issue in result["critical_failures"]))
        self.assertEqual(
            result["supporting_evidence"]["classified_answers"]["q5_packet"]["scenario_id"],
            "no_or_lost",
        )
        self.assertEqual(result["task_completion_status"], UNCERTAIN)


if __name__ == "__main__":
    unittest.main()
