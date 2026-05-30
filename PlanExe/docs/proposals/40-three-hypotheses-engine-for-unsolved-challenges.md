---
title: "Three-Hypotheses Engine: Technical Documentation"
date: 2026-02-11
status: proposal
author: PlanExe Team
---

# Three-Hypotheses Engine for Unsolved Challenges

**Author:** PlanExe Team  
**Date:** 2026-02-11  
**Status:** Proposal  
**Audience:** R&D Leads, Innovation Managers  

---

## Overview
The **Three-Hypotheses Engine** formalizes the "Discovery Phase" of a plan. When a team encounters an unsolved technical challenge (a "Known Unknown"), the system enforces a structured approach: generate exactly three viable hypotheses, design experiments to test them, and track progress until one succeeds or all fail.

It prevents "Tunnel Vision" (betting everything on one unproven idea) and "Analysis Paralysis" (endless research without action).

## Core Problem
Innovation is chaotic. Teams often pursue a single "pet theory" for months, only to fail. They rarely define *up front* what constitutes success or failure, leading to "Zombie Projects" that consume resources but produce no value.

## System Architecture

### 1. Challenge Definition
The user defines the *Problem Statement* (not the solution).
*   *Example:* "We need concrete that cures at -30°C."

### 2. Hypothesis Generator (H1, H2, H3)
The system (or user) proposes 3 distinct approaches. Each hypothesis is a "Bet".
*   **H1 (The Favorite):** High probability, moderate cost.
*   **H2 (The Backup):** Proven tech, higher cost/lower performance.
*   **H3 (The Moonshot):** Low probability, game-changing payoff.

### 3. Experiment Desiuge
For each hypothesis, defining the *Test Protocol*:
*   **Variable:** What are we changing?
*   **Metric:** What are we measuring?
*   **Success Criteria:** What number means "It works"?
*   **Kill Criteria:** What number means "Abandon ship"?

### 4. The Lifecycle Engine
A state machine that tracks each hypothesis through its stages: `Proposed` -> `Approved` -> `Testing` -> `Validated` OR `Refuted`.

---

## The "EVI" Formula (Expected Value of Information)

We prioritize experiments based on EVI.

$$EVI = (P_{success} \times Value_{success}) - Cost_{experiment}$$

Where:
-   $P_{success}$: Probability the hypothesis is true (Estimated).
-   $Value_{success}$: The Net Present Value (NPV) of the solution if it works.
-   $Cost_{experiment}$: The cost to run the test.

**Algorithm:**
1.  Calculate EVI for H1, H2, H3.
2.  If `EVI(H1) >> EVI(H2)`, run H1 first (Serial Strategy).
3.  If `EVI(H1) ≈ EVI(H2)`, run both (Parallel Strategy).

---

## Output Schema (JSON)

The structure of a Challenge object:

```json
{
  "challenge_id": "chal_777",
  "problem_statement": "Cold-weather concrete curing",
  "status": "active",
  "hypotheses": [
    {
      "id": "H1",
      "title": "Chemical Admixture",
      "p_success": 0.6,
      "cost_test": 5000,
      "value_success": 1000000,
      "evi": 595000,
      "state": "testing", 
      "experiments": [
        {
          "id": "exp_1",
          "metric": "cure_time_hours",
          "target": "< 24",
          "result": null
        }
      ]
    },
    {
      "id": "H2",
      "title": "Heated Formwork",
      "p_success": 0.9,
      "cost_test": 50000,
      "value_success": 800000, # Lower value due to higher operational cost
      "evi": 670000, 
      "state": "queued"
    }
  ],
  "strategy": "parallel" # Run H1 and H2 because both have high EVI
}
```

---

## User Interface: "The Experiment Dashboard"

A Kanban board with a twist. Columns are:
1.  **Hypotheses:** The 3 contenders.
2.  **In Flight:** Active experiments.
3.  **The Pivot Point:** Where decisions happen.
4.  **Graveyard:** Failed hypotheses (with "Post-Mortem" attached).
5.  **Winner's Circle:** The validated solution.

### The "Kill Switch"
If an experiment hits its "Kill Criteria" (e.g., "Cost > $100/unit"), the system automatically flags the hypothesis as `Refuted` and recommends moving resources to the next one.

## Future Enhancements
1.  **Automated Literature Review:** Agents that scan arXiv/Patents to suggest H1/H2/H3.
2.  **Bayesian Updating:** Automatically update $P_{success}$ based on partial experiment results.

## Detailed Implementation Plan

### Phase 1: Hypothesis object model and state machine

1. Define strict schema for each hypothesis:
   - assumptions
   - required experiments
   - expected value of success
   - kill criteria

2. Implement lifecycle state machine:
- proposed
- approved
- testing
- validated
- refuted
- archived

3. Add immutable event log for all state transitions.

### Phase 2: Experiment protocol builder

For each hypothesis, auto-generate experiment cards:
- objective metric
- target threshold
- sample size / duration
- budget cap
- stop-loss condition

Require explicit owner and due date before launch.

### Phase 3: Portfolio execution strategy

1. Compute EVI for H1/H2/H3.
2. Choose execution mode:
- serial if one hypothesis dominates
- parallel if top two EVIs are close

3. Reallocate budget dynamically when a hypothesis is refuted.

### Phase 4: Bayesian update loop

After each experiment result:
1. Update posterior success probability.
2. Recalculate EVI and ranking.
3. Trigger recommendation:
- continue
- pivot
- terminate challenge

### Data model additions

- `challenge_registry` (challenge_id, statement, domain, owner, status)
- `hypothesis_cards` (challenge_id, hypothesis_id, p_success, evi, state)
- `experiment_runs` (hypothesis_id, metrics_json, pass_fail, cost)
- `decision_log` (challenge_id, decision, rationale, timestamp)

### Integration with Monte Carlo and planning

- Inject hypothesis success distributions into Monte Carlo plan simulations.
- Update plan success probability after each experiment cycle.
- Surface “research readiness” score in bid/no-bid outputs.

### Validation checklist

- Time-to-first-validated-hypothesis trend.
- Reduction in dead-end R&D spend.
- Post-hoc accuracy of EVI-based prioritization.

## Detailed Implementation Plan (Experiment Governance)

### Hypothesis Portfolio Rules
- Force diversity across H1/H2/H3 approaches.
- Disallow near-duplicate hypotheses unless justified.

### Experiment Program Control
- Every hypothesis must have explicit kill criteria.
- Budget caps enforced per experiment lane.
- Stop-loss automation when outcomes violate thresholds.

### Decision Cadence
- Weekly hypothesis review board
- Auto-update posterior probabilities after each result batch
- Re-rank hypothesis queue by updated EVI

### Outcome Tracking
- Measure time-to-first-validated-path
- Track dead-end spend ratio and reduction over time

