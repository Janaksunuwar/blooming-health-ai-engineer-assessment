"""Workflow parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Route:
    scenario_id: str
    target_kind: str
    target_id: str


@dataclass(frozen=True)
class Question:
    id: str
    label: str
    text: str
    answer_type: str
    options: tuple[str, ...]
    routes: dict[str, Route]


def parse_workflow(agent_config: dict[str, Any]) -> dict[str, Any]:
    engine_config = agent_config.get("engine_config", {})
    questions: dict[str, Question] = {}
    order: list[str] = []
    for item in engine_config.get("items", []):
        item_id = item["id"]
        question = item["questions"][0]
        routes = {
            scenario["id"]: _parse_route(scenario)
            for scenario in question.get("scenarios", [])
        }
        questions[item_id] = Question(
            id=item_id,
            label=item.get("label", item_id),
            text=question["text"],
            answer_type=question.get("type", "text"),
            options=tuple(question.get("options") or ()),
            routes=routes,
        )
        order.append(item_id)
    outcomes = {outcome["id"]: outcome for outcome in engine_config.get("outcomes", [])}
    return {"questions": questions, "order": order, "outcomes": outcomes}


def _parse_route(scenario: dict[str, Any]) -> Route:
    if scenario.get("disposition"):
        return Route(scenario["id"], "disposition", scenario["disposition"])
    goto = scenario.get("goto")
    if goto == "_complete":
        return Route(scenario["id"], "complete", "complete_renewal")
    if isinstance(goto, str) and goto.startswith("item_"):
        return Route(scenario["id"], "question", goto.split(":", 1)[0].removeprefix("item_"))
    return Route(scenario["id"], "complete", "complete_renewal")
