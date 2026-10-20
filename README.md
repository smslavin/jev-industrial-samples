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
| [04-alarm-triage](04-alarm-triage/) | Alarm floods: a briefing for the agent instead of a dump, without hiding the urgent alarm |

Where Jev sits around the agent in each sample:

- **Before the agent (02):** the router decides whether the agent is needed at all.
- **On what the agent reads (04):** triage decides what the agent sees first.
- **On what the agent does (01):** the gate checks writes before they run.
- **On the data the agent works with (03):** mapping builds the I/O bindings.

The same pattern runs through all four. Code owns exact rules and policy. Jev
answers narrow questions with probabilities. Anything uncertain goes to a person or
the agent, never straight to the plant.

A possible next sample: checking the agent's answers against its tool results.

## Setup

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
echo TYPESAFE_API_KEY=... > .env
```
