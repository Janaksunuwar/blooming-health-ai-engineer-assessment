# Blooming Health Senior AI Engineer Assessment

This repository contains work for the Blooming Health Senior AI Engineer take-home assessment.

The assessment has three independent problems:

1. [Q1](q1/capacity_under_burst.md): Capacity planning for 10,000 outbound AI voice calls within a 30-minute window.
2. [Q2](q2/long_running_agent.md): Architecture for keeping a long-running AI voice agent accurate across a 40-minute Medicaid renewal workflow.
3. [Q3](q3/README.md): A runnable Python evaluation harness for determining whether an AI agent successfully completed a healthcare workflow from a transcript and captured field values.

## Repository Organization

```text
.
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   └── assumptions.md
├── q1/
│   └── capacity_under_burst.md
├── q2/
│   └── long_running_agent.md
└── q3/
    ├── README.md
    ├── evaluation_spec.md
    ├── requirements.txt
    ├── results.json
    ├── run.py
    ├── data/
    │   ├── .gitkeep
    │   └── gym_agent_conversations.json
    ├── src/
    │   ├── __init__.py
    │   ├── evaluator.py
    │   ├── loader.py
    │   └── workflow.py
    └── tests/
        ├── __init__.py
        └── test_evaluator.py
```

Q1 and Q2 are written responses. Q3 is a runnable Python evaluation harness with a candidate-facing transcript dataset, deterministic workflow checks, captured-field validation support, tests, and a generated results file.

The included Q3 dataset, `q3/data/gym_agent_conversations.json`, contains ten simulated transcript-only conversations. It does not include claimed captured-field records, so the default run evaluates workflow behavior and reports `field_accuracy_status` as `NOT_EVALUATED`. When a reviewer provides captured fields with `--captured-fields`, the evaluator runs in full mode and compares claimed field values against transcript evidence. A transcript-only `PASS` should not be read as proof of submitted application-field accuracy or downstream Medicaid renewal completion.

Note: `q3/data/gym_agent_conversations.json` contains a leftover `[GOAL_ACHIEVED]` marker embedded in some caller dialogue, an artifact of how the sample data was generated; the evaluator does not read or depend on this string anywhere, and it is noted here for transparency.

The Q3 evaluator can be run from the repository root:

```bash
python3 q3/run.py --input q3/data/gym_agent_conversations.json --output q3/results.json
```

The Q3 unit tests can be run with:

```bash
python3 -m unittest discover -s q3/tests -v
```

Q3 uses only the Python standard library; `q3/requirements.txt` is intentionally empty.
