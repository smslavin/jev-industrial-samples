# 03 — Brownfield tag mapping

A galaxy already exists, with ISA-style object names (`RawWater_P101`) and UDAs
(`Speed`, `DischargePressure`). The PLC's OPC-UA server uses its own naming
(`PLC1.RW_PMP_1.SPD_FB`, `DISCH_PT`), and half its descriptions are blank. Someone
has to work out which node feeds which attribute. This sample does that mapping
and produces a binding plan.

## Two stages

| Stage | Jev request | Code, before and after |
| --- | --- | --- |
| 1. Device | One request: a Choice per galaxy object over the server's device folders, plus `none` | Flags a folder claimed by two objects |
| 2. Signal | One request per matched object, run concurrently: a Choice per UDA over that folder's nodes, plus `none` | **Before:** filters candidates by data type. **After:** checks units and catches one node feeding two attributes |

Stage 2 can't be part of the first request because its candidate list depends on
the folder chosen in stage 1.

Each candidate shown to Jev includes the node's description, data type, units, and
**current value**. A speed feedback of 82.5 % and a run-hours counter of 18,234 h
look very different, even when both names are cryptic.

## Outcomes

- **auto**: device and signal confidence both ≥ 0.8, units match, no conflicts.
  Goes straight into `bindings`.
- **review**: a proposal with a reason, such as low confidence, a units mismatch
  that needs scaling, a conflict, or an unsure `none`.
- **unmapped**: a confident `none`, no type-compatible node, or no device folder.

`run.py` writes `binding_plan.json`, which contains:
- **`bindings`**: GRAccess input-source strings (`OPCUA:PlantPLC.PLC1.RW_PMP_1.SPD_FB`)
  in the format `bind_uda_io` / `set_inputsource` already accepts.
- **`review`** and **`unmapped`**: the rows a person needs to look at.
- **`device_items`**: the OI Gateway Device Items (`/PlantPLC/s=...`) for every
  proposed node, including review rows, so the reviewer can see live values.

## Run

```
cd 03-tag-mapping
..\.venv\Scripts\python run.py
```

## Results (jev-latest, 2026-10-20)

23/23 attributes match the expected node or `none`, on three consecutive runs. All
17–18 auto rows are correct in every run. The run makes 7 Jev requests in about
0.55 s wall time.

Cases worth reading:

- **Pump 1 vs pump 2.** `RW_PMP_1` and `RW_PMP_2` have nearly identical signal
  lists. Device confidence is 0.99 for P101 but only 0.86–0.89 for P102. Both are
  right.
- **Speed feedback vs reference.** `SPD_FB` and `SPD_REF` are both Float in %. Jev
  picks the feedback for "VFD speed feedback" with 0.95 confidence.
- **Influent vs effluent turbidity.** Both are `TURB_*` in NTU with no description.
  Jev picks `TURB_EFF` from the name alone.
- **H vs HH.** "Clearwell high level alarm" goes to `H` at about 0.77 confidence,
  which lands in review. Review is the right outcome here: some sites alarm on HH.
- **No Boolean node.** Filter 1 has only `BW_STEP` (Int16) for backwash, so code
  marks `BackwashActive` unmapped without asking Jev. Filter 2's `BW_ACT` is found.
- **No device.** `UV_701` isn't on this server. Jev says `none` with 0.99 confidence.

## What the first run taught

The first run got 22/23. P102's `DISCH_PT` reports in psi, the galaxy expects bar,
and Jev answered `none` at 0.53 confidence. There were two problems:

1. **The question mixed two jobs.** Jev was judging the units mismatch when it
   should judge meaning only. Units are code's job. The question now says "judge by
   meaning; units may differ." Jev then picks `DISCH_PT` with 0.96 confidence, and
   code sends it to review for scaling.
2. **The policy treated an unsure `none` like a confident one.** A low-confidence
   `none` now goes to review with the best candidate from the probability
   distribution. Only a confident `none` is marked unmapped.

## Caveats

- Some confidences move a few points between runs. `Level` sits right at the 0.8
  threshold, and `BW_ACT` (no description) has ranged from 0.68 to 0.90. As a
  result, the auto/review split varies by one row between runs. Mapping correctness
  doesn't vary.
- Stage 1 lists every folder in a single Choice. A real server with hundreds of
  devices needs a code-side shortlist first, for example by area or name
  similarity.
- A low-confidence `none` at the device stage is still treated as unmapped. The
  same runner-up logic used in stage 2 should be applied there.
- This is one plant's naming. Run it against a real browse export and a real
  galaxy before trusting the 0.8 threshold.
