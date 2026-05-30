---
title: "Risk Propagation Network + Failure Mode Manifestation"
date: 2026-02-10
status: proposal
author: PlanExe Team
---

# Risk Propagation Network + Failure Mode Manifestation

**Author:** PlanExe Team  
**Date:** 2026-02-10  
**Status:** Proposal  
**Tags:** `risk`, `propagation`, `failure-modes`, `simulation`, `dependencies`

## Pitch
Model how local risks propagate through dependencies to system-level failure, then simulate manifestation paths across many runs to surface the most likely cascades and highest-leverage interventions.

## Why
Risks rarely fail in isolation. Large project failures typically emerge from **interacting risks** across domains (technical, procurement, financing, regulatory). A propagation model makes these interactions explicit and actionable.

## Problem

- Risk registers treat items independently.
- Teams under-estimate compounding effects.
- Mitigation choices are not ranked by systemic impact.

## Proposed Solution
Build a **Risk Propagation Network** that:

1. Represents risks, tasks, and milestones as a connected graph.
2. Encodes causal links and delay effects between nodes.
3. Simulates cascades across the network.
4. Outputs failure pathways and intervention leverage scores.

## Architecture

```text
Plan JSON
  -> Risk + Dependency Extraction
  -> Propagation Graph Builder
  -> Cascade Simulator (Monte Carlo)
  -> Failure Path Analyzer
  -> Mitigation Prioritizer
```

## Graph Model

- **Nodes:** risks, tasks, milestones, resources.
- **Edges:** causal amplification and delay links.
- **Weights:** probability impact, lag time, and severity multiplier.

### Example edge

- Procurement delay -> schedule slippage (weight: high, lag: 2 weeks)
- Schedule slippage -> financing drawdown risk (weight: medium, lag: 1 month)

## Simulation

Run multi-step simulations to reveal cascades:

- Sample risk events based on probability distributions.
- Propagate effects through graph edges.
- Track which nodes fail, when, and how often.

**Outputs per run:**

- failure sequence
- time-to-failure
- cost impact

## Output Schema

```json
{
  "top_failure_paths": [
    {
      "path": ["procurement_delay", "schedule_slip", "financing_gap"],
      "probability": 0.18,
      "expected_loss": 4200000
    }
  ],
  "intervention_points": [
    {"node": "procurement_delay", "leverage": 0.72}
  ]
}
```

## Integration Points

- Feeds into Monte Carlo plan success probability engine.
- Adds a propagation-adjusted risk score to plan ranking.
- Triggers mitigation playbooks for top cascades.

## Success Metrics

- Reduction in surprise compound failures.
- Increased mitigation effectiveness vs baseline risk registers.
- Improved forecast accuracy for delays and cost overruns.

## Risks

- Model complexity could obscure interpretation.
- Missing edges lead to false security.
- Overfitting to historical cascades.

## Future Enhancements

- Automated edge discovery from historical plans.
- Dynamic updates as execution data arrives.
- Cross-project risk propagation benchmarking.

## Detailed Implementation Plan

### Phase 1: Graph Construction Layer

1. Define canonical node types:
   - `risk_event`, `task`, `milestone`, `resource_constraint`

2. Define edge semantics:
   - causal amplification
   - schedule delay transfer
   - cost transfer
   - confidence score per edge

3. Build graph extraction adapters from plan artifacts:
   - WBS + dependencies
   - risk register
   - finance assumptions

### Phase 2: Propagation Simulator

1. At each simulation tick:
   - sample active risk events
   - propagate effects along outgoing edges
   - update impacted task states and milestone forecasts

2. Capture cascade traces:
   - first-trigger node
   - propagation chain
   - terminal failure state

3. Aggregate over 10,000 runs:
   - pathway frequencies
   - expected loss per pathway
   - median time-to-failure

### Phase 3: Mitigation Optimizer

1. Score intervention points by marginal risk reduction.
2. Recommend top mitigation portfolio under budget constraints.
3. Re-simulate with mitigations applied to show deltas.

### Suggested algorithmic approach

- Use weighted directed graph with event queue.
- Compute influence centrality to prioritize mitigation.
- Run counterfactual analysis: remove/attenuate edge and measure probability delta.

### Data model additions

- `risk_graph_nodes` (run_id, node_id, node_type, metadata)
- `risk_graph_edges` (run_id, src, dst, edge_type, weight, lag)
- `risk_cascade_paths` (run_id, path_json, probability, expected_loss)

### Integration points

- Feed risk pathway penalties into ELO/selection ranking.
- Push high-risk cascade alerts into governance dashboard.
- Link mitigation actions back into planning artifacts.

### Validation checklist

- Synthetic graph tests with known cascades.
- Stability tests for edge-weight perturbation.
- Human review of top-10 pathways for interpretability.

## Detailed Implementation Plan (Graph Operations)

### Graph Build Pipeline
1. Extract nodes from tasks, risks, resources.
2. Infer edges from dependencies and causal templates.
3. Score edge confidence and impact weight.

### Runtime
- Run cascade simulation alongside baseline Monte Carlo.
- Persist top failure chains and intervention candidates.

### Mitigation Planner
- Compute marginal risk reduction for each intervention.
- Recommend portfolio under mitigation budget constraint.

### Governance
- Require review for interventions with high operational disruption.

