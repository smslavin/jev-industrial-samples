# Jev + agents for industrial automation

Standalone samples showing [TypeSafe's Jev](https://docs.typesafe.ai) next to an
LLM agent in OT workflows. The agent reasons and proposes, code owns control and
policy, and Jev supplies fast, typed judgments, with probabilities, wherever code
needs to understand meaning.

| Sample | Shows |
| --- | --- |
| [01-write-gate](01-write-gate/) | Gating an agent's proposed plant writes: ALLOW / CONFIRM / ESCALATE |

Planned: intent router in front of the agent, OPC-UA brownfield tag mapping, alarm
flood triage, verifying the agent's answers against its tool results.

## Setup

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
echo TYPESAFE_API_KEY=... > .env
```
