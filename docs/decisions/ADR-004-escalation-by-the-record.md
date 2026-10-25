# ADR-004 — A seat's deeper model is reached by the record's NOT MET, not by the model's judgement

**Date** 2026-10-25 · **Status** accepted · **Review finding** #5 (medium)

## Context

Each seat ran one model for the whole run. The harmony pilots put every seat on an inexpensive model; the only
deeper model was the lead, reached after two failed reworks on the cheap one. Measured in Pegasus
(2026-10-20): cost is volume × price, and most seats are runners whose first attempt is usually right — so a
deep model on every call is most of the bill, while a cheap model that fails should not be retried on the same
cheap model twice before anything changes.

## Decision

`Seat.escalate_to` names a deeper model id. The first attempt at an order runs on `Seat.model`. When the record
sends the order back **NOT MET** and the scheduler reworks it, the rework is dispatched on `escalate_to`; so is
an adopted order whose chain shows a rework already happened. The decision point is the record's predicate check
— deterministic, evidence-based — never the model's confidence or a classifier.

Mechanically the scheduler dispatches the seat as `replace(seat, model=seat.escalate_to)`, so every way of
supplying models (one model, a mapping by name / role / model id, a function of the seat) keeps working, and the
CLI's `model_for` (by `seat.model`) picks the deeper model up without change. The dispatch event records the
model used and whether it was an escalation; the run node's config records `escalate_to` per seat.

## Alternatives considered

- Escalate on the model's own "I'm not sure": that is the model judging the model. The record's check is the
  authority the whole design rests on.
- A cheap classifier choosing the tier per order up front: another model call per order, and a guess; the
  record's verdict after one cheap attempt is a measurement.
- Escalating the lead only: already the case; it starts two reworks too late for a worker that is simply too
  weak for the order.

## Consequences

- Tests: two seats on a lazy cheap model that returns without working are each reworked once onto the deep
  model and the run settles — `cheap.calls == 2` (one attempt per order), both escalated dispatches on `deep`,
  `model_escalations == 2`; a seat without `escalate_to` never escalates.
- Cost shape: the cheap model's one failed attempt is paid for. For the orders where it succeeds (the common
  case in the pilots) nothing deeper is ever called.
- Measurement to follow in the harmony study: condition E with `escalate_to` set, against E without it, on the
  same instances — calls, cost, traps, finish rate.
