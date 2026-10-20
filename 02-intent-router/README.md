# 02 — Intent router

An operator types into a panel. Before any agent runs, one Jev request decides who
handles it:

| Route | Handled by |
| --- | --- |
| `read_value` | **Code.** Reads the tag directly, with no agent call. |
| `galaxy_lookup` | **Code.** Template, area, description, or units from the galaxy. |
| `write_request` | **Agent, then gate.** The agent proposes the write; [01-write-gate](../01-write-gate/) decides. |
| `needs_agent` | **Agent.** Diagnosis, comparisons, history, MES records. |
| `out_of_scope` | **Refused.** |

## Speculative fan-out

The same request also asks for the arguments the code handlers need, before the
route is known:

| Question | Type | Used when |
| --- | --- | --- |
| `route` | Choice | always |
| `target` | Choice over the tag catalog, plus `none` | read, lookup |
| `attribute` | Choice: PV, SP, Mode, Status, Alarm | read |
| `lookup_field` | Choice: template, area, description, units | lookup |
| `single_item` | Noul | read, lookup |

All five run in parallel inside one call. Code ignores the answers for branches it
doesn't take. Those answers often have low confidence (for example, `lookup_field`
on a read request), and that is expected and harmless.

The tag catalog in [plant.py](plant.py) is a simulated galaxy. In a real deployment,
graccess-mcp supplies the objects and descriptions, and MxAccess supplies the values.
Jev *selects* a tag from that catalog rather than generating a name, so it cannot
invent one.

## Failing safe

Every uncertain outcome falls back to the agent: low route confidence, a target of
`none` or low confidence, or more than one item. A routing mistake costs an agent
call, never a bad write, because writes never run in code here. They always go
through the agent and then the write gate.

## Run

```
cd 02-intent-router
..\.venv\Scripts\python run.py             # all cases
..\.venv\Scripts\python run.py two-items   # one case, every judgment printed
```

## Results (jev-latest, 2026-10-20)

18/18 cases match the expected handler and arguments, on three consecutive runs.
9 of the 18 are answered in code with no agent call. All 18 run concurrently in
0.75–1.3 s wall time, using about 22k input tokens in total (about 1,200 per request,
mostly the tag catalog).

Cases worth reading:

- `two-items` ("What are the T-200 level and the raw water flow?"): `route` says
  read and `target` picks LT_200 with 0.75 confidence. Only the separate
  `single_item` Noul (0.03) prevents half an answer. Splitting that judgment out was
  worth it.
- `no-such-tag` ("steam header pressure"): Jev picks `none` instead of the nearest
  pressure tag (PT_410, drum pressure), so the request goes to the agent.
- `which-cw-pump` ("Is the standby pump available?"): Jev resolves "standby" to
  P_302 from the catalog descriptions.
- `terse-level` ("lvl t200??"): the closest call, with route confidence 0.82 and
  `single_item` 0.72.

## Caveats

- The tag catalog goes into every request, so tokens grow with catalog size. A real
  galaxy with thousands of tags needs a code-side shortlist first, such as filtering
  by the operator's current panel or area, or a BM25 search over descriptions. Jev
  then selects from the shortlist (see TypeSafe's re-ranking cookbook).
- On write requests, `target` and `attribute` are already filled in (`raise-sp` →
  TIC_101.SP). Passing them to the agent as hints, and to the gate as an
  independent cross-check of the agent's proposal, is an easy next step.
- 18 hand-written cases are a demo, not an evaluation. Validate the thresholds on
  real operator phrasing.
