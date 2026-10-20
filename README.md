# Jev + agents for industrial automation

Standalone samples showing [TypeSafe's Jev](https://docs.typesafe.ai) next to an
LLM agent in OT workflows. The agent reasons and proposes, code owns control and
policy, and Jev supplies fast, typed judgments, with probabilities, wherever code
needs to understand meaning.

| Sample | Shows |
| --- | --- |
| [01-write-gate](01-write-gate/) | Gating an agent's proposed plant writes: ALLOW / CONFIRM / ESCALATE |
| [02-intent-router](02-intent-router/) | Routing operator requests: simple reads in code, everything else to the agent |
| [03-tag-mapping](03-tag-mapping/) | Brownfield OPC-UA onboarding: mapping an existing galaxy's UDAs to cryptic PLC tags |

Taken together: the router (02) decides whether the agent is needed, the agent
proposes, and the gate (01) checks writes before they run.

Planned: alarm flood triage, verifying the agent's
answers against its tool results.

## Setup

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
echo TYPESAFE_API_KEY=... > .env
```
