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

## Stress test: a spoofed brownfield from the clean AvevaWaterOPC model

There's no messy dev galaxy to test against, so [dirtier.py](dirtier.py) generates
messy PLC namespaces. It starts from the clean AvevaWaterOPC model (10 objects, 34
attributes, copied from `opcua-mcp/simulator.py`) and rebuilds the OPC-UA side
the way a PLC programmer might have, with a seed. It also writes the answer key.
The galaxy side stays clean, as it usually is on a brownfield job.

| Level | Mess |
| --- | --- |
| easy | One naming convention (`PLC1.RW_PMP_1.FT_PV`), 20 % blank descriptions |
| medium | Adds ISA loop folders on PLC2 (`PLC2.U501.FT501_PV`), 50 % blank, 30 % changed units (psi, gpm, hp, 0–1 fractions), look-alike decoys (setpoints, limits, commands, H/L alarms, raw counts), 10 % missing signals, spare tags |
| hard | Adds Siemens-style German data blocks on PLC3 (`PLC3.DB10.BM_LAEUFT`), 80 % blank, 50 % changed units, 15 % missing |
| swapped | Medium, plus raw water pumps 1 and 2 wired to each other's PLC folders |

```
..\.venv\Scripts\python dirtier.py hard 1        # write dirty/hard-1/*.json
..\.venv\Scripts\python run.py dirty/hard-1      # map it, print every row
..\.venv\Scripts\python sweep.py                 # every level x seeds 1-3
```

### Sweep results (jev-latest, 2026-10-20, seeds 1–3, 34 attributes each)

| Level | Correct | Auto | **Wrong auto** | Review | Unmapped | Missed (real node marked unmapped) |
| --- | --- | --- | --- | --- | --- | --- |
| easy | 34/34 | 34 | **0** | 0 | 0 | 0 |
| medium | 28–31 | 15–17 | **0** | 8–17 | 0–11 | 0–5 |
| hard | 23–26 | 9 | **0** | 12–21 | 4–13 | 0–6 |
| swapped | 20–23 | 15–17 | **5–6** | 8–17 | 0–11 | 0–7 |

Wrong-auto is the number that matters: a binding that skips review and is wrong.
Review and unmapped rows cost an engineer's time. A wrong auto row costs a bad
binding. As the mess increases, the mapper sends more rows to review instead of
guessing.

### What the sweep found

1. **A decoy chosen when the real signal is missing.** The first sweep had 2 wrong
   auto rows on `hard`: with `FT_PV` absent, Jev picked `FT_SP` (a setpoint) for
   `Flow`. The fix was domain knowledge the question hadn't stated. These are
   InputSource bindings, so the node must be a measurement or feedback, never a
   setpoint, limit, command, or selector. After adding that to the question,
   `hard` dropped to 0 wrong auto, and `easy` went from 26–28 auto rows to all 34.
2. **Swapped numbering can't be caught from names.** Every wrong auto row in
   `swapped` is the swapped pump pair. When `RawWater_01` is wired to `RW_PMP_2`,
   nothing in the namespace says so, and a person would make the same mistake.
   This needs a field check: bump the pump and see which `RUN_FB` changes. That
   belongs in a commissioning step, not in better matching.
3. **Unsure "no device" now goes to review.** Stage 1 uses the same runner-up rule
   as stage 2.
4. **Look-alike devices produce a confident "neither".** The chlorine and fluoride
   skids sit in ISA loop folders `U501` / `U502` with the same signal lists and no
   descriptions. Nothing says which is chlorine. Jev answers `none` with 0.90–0.95
   confidence, so 5–6 real rows end up unmapped. A single Choice can't express
   "one of these two, I can't tell which". The next step is one Noul per candidate
   folder in stage 1, so code sees the tie and sends both candidates to review.
   The current failure is in the safe direction.
5. **One confident German miss.** `LAMPE_BH` (Lampe Betriebsstunden, lamp hours)
   with a blank description was rejected for `LampHours` with 0.99 confidence.
   The error is in the safe direction, and it is the kind of abbreviation a site
   glossary in the question's criteria would fix.

The naming rules are this author's idea of a messy plant, not field data. Treat
the sweep as a stress test of the mapper's failure modes, not as a measure of
real-world accuracy.

## Caveats

- Some confidences move a few points between runs. `Level` sits right at the 0.8
  threshold, and `BW_ACT` (no description) has ranged from 0.68 to 0.90. As a
  result, the auto/review split varies by one row between runs. Mapping correctness
  doesn't vary.
- Stage 1 lists every folder in a single Choice. A real server with hundreds of
  devices needs a code-side shortlist first, for example by area or name
  similarity.
- This is one plant's naming. Run it against a real browse export and a real
  galaxy before trusting the 0.8 threshold.
