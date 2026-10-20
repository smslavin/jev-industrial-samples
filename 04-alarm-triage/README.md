# 04 — Alarm flood triage

During an upset, dozens of alarms arrive within minutes. Handing the raw list to an
agent costs context, and the agent can still miss the important one. This sample
triages the flood first, so the agent receives a briefing:

```
Likely initiating event:
  06:12:03 MCC_Intake.Voltage UnderVoltage: Intake MCC bus undervoltage [P2, UNACK]  (p=0.98)
Act now:
  06:16:02 FinishedWater_01.Level LoLo: Clearwell level low low; ... [P1, UNACK]  (urgency 2.4/3, consequence)
  06:12:52 Chlorine_01.GasDetector HiHi: Hypochlorite room chlorine gas high high [P2, UNACK]  (urgency 2.9/3, ...)
  ...
Other active alarms, most urgent first:
  ...
Chattering (for alarm rationalization; check the instrument):
  06:12:20 Clarifier_01.Turbidity Hi (x6) ...
Suppressed (2): Fluoride_01.TankLevel Lo, HighService_02.Mode NotAuto
```

## How the work is split

| Who | Does |
| --- | --- |
| Code, before | Collapses repeats into one entry with a count; strips the answer key |
| Jev, one request | Two questions per alarm: **role** (Choice: initiating / consequence / independent / nuisance) and **urgency** (Score 0–3, judged on the alarm's own merits) |
| Code, after | Policy: never suppress P1; put P1 at the top of Act now; suppress only confident independent or nuisance alarms with low urgency; list chattering by repeat count; sort by urgency |

Role and urgency are separate questions on purpose. An alarm unrelated to the upset
can still be the most urgent thing on the screen.

The state for Jev is the whole flood plus a one-paragraph description of how the
plant is connected. In a real deployment, the agent or graccess-mcp would supply
that description from the galaxy model.

## Scenarios

Both use AvevaWaterOPC object names. See [scenarios.json](scenarios.json).

- **intake-power-dip** (19 alarms): an intake MCC undervoltage trips both raw water
  pumps, and flow-paced dosing, UV flow, and the clearwell follow. It includes
  standing alarms from before the upset, two chattering alarms, and an unrelated
  **chlorine gas HiHi** in the middle of the flood.
- **chlorine-analyzer-failure** (10 alarms): the clearwell residual analyzer fails
  low. The trim loop drives hypochlorite dosing to HiHi, and distribution residual
  climbs. This is the case where a "low chlorine" alarm means too much chlorine.

## Run

```
cd 04-alarm-triage
..\.venv\Scripts\python run.py
```

## Results (jev-latest, 2026-10-20, three runs)

| | intake-power-dip | chlorine-analyzer-failure |
| --- | --- | --- |
| Urgent alarm suppressed (must be 0) | **0** | **0** |
| Initiating event ranked first | yes (p 0.98–0.99) | yes (p 0.73) |
| Role matches label | 15/19 | 8–9/10 |
| Urgency-3 alarm outside Act now | 0–1 | 0–1 |
| Briefing vs raw flood | 4,130 → ~2,000 chars | 2,248 → ~1,000 chars |

The full run takes about 0.35 s for both scenarios, at about 400 Jev input tokens
per alarm.

### What it showed

1. **Separate urgency caught what role missed.** Jev labeled the chlorine gas
   alarm a *consequence* of the power dip, which is wrong (confidence 0.69). It
   still scored it 2.9/3 urgent, so the alarm led Act now. With a single "what
   matters" question, it would have been filed with the cascade.
2. **Urgency scores bunch together during a flood.** Nearly every active alarm
   scores 1.9–2.9. Several alarms labeled "respond now" scored 2.4–2.5 against the
   2.5 cutoff, including the P1 clearwell LoLo, the alarm the plant itself rates
   highest. The fix was policy, not a lower cutoff tuned to these labels: P1 is
   always Act now, and everything else is sorted by urgency, so the bunched scores
   still produce a useful order. One urgency-3 alarm per scenario still sometimes
   lands at 2.4, just under the cutoff: the pump 1 trip, which also appears as
   initiating candidate #2, or distribution residual high, which tops the
   "Other" list.
3. **Chattering is code's job.** Jev called the chattering turbidity and flow
   alarms consequences of the upset, not nuisances. That is arguably right:
   clarifier turbidity does rise when flow collapses. Whether an alarm is
   chattering is a repeat count, so code lists them separately for alarm
   rationalization instead of relying on a judgment.
4. **The analyzer failure ranked first.** `AIT_520 BadQuality` came out as the
   initiating event, ahead of the LoLo residual alarm it caused. That is the
   distinction an operator needs: the residual isn't low, the instrument is lying,
   and the real problem is overdosing.

## Caveats

- **Briefing size:** it only halves on floods this small. A real flood of hundreds
  of alarms would gain more from collapsing the consequence group into counts per
  area. The ordering is the main value here.
- **Scaling:** every alarm's questions go into one request with the whole flood as
  state. Hundreds of alarms would need batching by time window or area. Each batch
  still needs enough context to judge role.
- **Labels and thresholds:** the labels are this author's. Two of the four role
  "misses" in intake-power-dip are defensible answers. The thresholds are
  starting points.
- **Not a replacement for alarm management:** this doesn't replace ISA-18.2 alarm
  rationalization or state-based suppression in the alarm system. It decides what
  an agent reads first, not what the alarm system annunciates.
