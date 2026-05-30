---
title: Finance Analysis via Bottom-Up Estimation + Reconciliation
date: 2026-02-10
status: proposal
author: Larry the Laptop Lobster
---

# Finance Analysis via Bottom-Up Estimation + Reconciliation

## Pitch
Build a bottom-up financial model from tasks, resources, and unit economics, then reconcile it against top-down estimates to surface gaps and improve accuracy.

## Why
Top-down estimates are fast but coarse. Bottom-up estimates are realistic but time-consuming. Combining both gives the speed of top-down with the credibility of bottom-up, while exposing unrealistic assumptions early.

## Problem

- Plans often include partial or inconsistent financials.
- Bottom-up models are missing or unstructured.
- Divergence between top-down and bottom-up is not tracked.

## Proposed Solution
Implement a bottom-up estimation module that:

1. Extracts work packages, resources, and timelines.
2. Builds cost and revenue from unit-level assumptions.
3. Aggregates to totals and cash flow.
4. Reconciles differences with top-down estimates.

## Bottom-Up Estimation Framework

### 1) Work Package Extraction
Identify:

- Tasks and milestones
- Deliverables and work packages
- Staffing requirements
- Duration and dependencies

### 2) Unit Cost Modeling
Attach costs per unit:

- Labor: role-based hourly or monthly rates
- Materials: quantity x price
- Infrastructure: cloud usage, hardware
- External services: contractors, vendors

### 3) Revenue Modeling
Build revenue from:

- Units sold x price
- Contract values and timelines
- Subscription tiers and churn
- Conversion funnel estimates

### 4) Aggregation
Produce:

- Project budget by phase
- Monthly burn and runway
- Break-even timing
- Profit and loss summary

### 5) Multi-Currency Handling

Plans may involve multiple currencies (e.g., cross-border projects). The bottom-up model should:

- Track line items in native currency at the work-package level.
- Roll up to a reporting currency with explicit FX assumptions.
- Support a third currency when local currencies are unstable.

## Reconciliation Layer

Compare bottom-up vs top-down outputs:

- Total revenue variance
- Margin variance
- Capex and opex mismatches
- Timeline inconsistencies

**Reconciliation output:**

- Variance report
- Recommended adjustments
- Updated confidence levels

## Output Schema

```json
{
  "bottom_up": {
    "total_cost": 2200000,
    "total_revenue": 4800000,
    "burn_rate_monthly": 180000,
    "reporting_currency": "USD",
    "fx_assumptions": [
      {"pair": "BRL/USD", "rate": 0.19, "as_of": "2026-02-10", "volatility": "high"}
    ]
  },
  "top_down": {
    "total_cost": 1500000,
    "total_revenue": 5200000
  },
  "variance": {
    "cost_delta": 700000,
    "revenue_delta": -400000
  },
  "reconciliation_notes": [
    "Bottom-up assumes 12 engineers, top-down assumes 8",
    "Top-down margin range exceeds observed unit economics"
  ]
}
```

## Integration Points

- Uses CBS generation as input for cost categories.
- Feeds into investor thesis matching and risk scoring.
- Drives evidence-based adjustments in financial claims.

## Success Metrics

- Percentage of plans with bottom-up models.
- Reduction in financial variance after reconciliation.
- Investor confidence in financial projections.

## Risks

- High data requirements: mitigate with default benchmarks and missing info prompts.
- Estimation complexity: prioritize major cost drivers first.
- False precision: publish ranges and confidence scores.

## Future Enhancements

- Automated cost libraries by region and sector.
- Sensitivity analysis and scenario modeling.
- Learning system that updates estimates from real outcomes.

## Detailed Implementation Plan

### 1) Bottom-up estimator architecture

For each WBS task, build a cost object:
- labor profile (roles, hours, rates)
- material BOM (qty × unit cost)
- external services
- fixed/variable overhead
- contingency allocation

Aggregate task costs -> work package -> phase -> plan total.

### 2) Revenue build-up layer

For plans with revenue:
- unit sales model or contract milestone model
- churn/renewal assumptions (if subscription)
- conversion and ramp assumptions

Link revenue timing to project timeline for cashflow realism.

### 3) Reconciliation algorithm (top-down vs bottom-up)

Input:
- top-down scenario bands (P10/P50/P90)
- bottom-up deterministic/ranged total

Compute variance decomposition by category:
- labor delta
- materials delta
- capex delta
- schedule-induced delta

Generate reconciliation recommendations ranked by expected impact.

### 4) Convergence rules

Define explicit convergence status:
- `green`: variance <= 10%
- `yellow`: 10–20%
- `red`: >20%

If yellow/red, require iteration actions before “finance-ready” status.

### 5) Iteration loop

1. identify highest variance categories
2. request missing inputs or benchmark corrections
3. update assumptions
4. recompute both models
5. re-evaluate convergence state

Track each iteration for audit.

### 6) Integration points

- Pull CBS line items from Proposal 33
- Pull benchmark priors from Proposal 34
- Expose convergence status in plan summary
- Feed risk module when persistent red variance remains

### 7) Output package

Produce a finance bundle:
- bottom-up ledger
- top-down summary
- variance decomposition chart
- reconciliation action log
- convergence status + signoff checklist

### 8) Rollout phases

- Phase A: deterministic bottom-up + simple variance
- Phase B: ranged bottom-up with confidence levels
- Phase C: automated reconciliation recommendations
- Phase D: closed-loop learning from actual spend/revenue outcomes

### 9) Validation checklist

- Accounting consistency (totals match component sums)
- Reproducibility under fixed assumptions
- Reviewer confidence uplift after reconciliation
- Reduced forecast error on executed projects

## Detailed Implementation Plan (Convergence Operations)

### Convergence Workflow
1. Generate bottom-up ledger from WBS/CBS.
2. Pull top-down baseline from proposal 34 module.
3. Compute variance by category and timeline bucket.
4. Trigger correction cycle until convergence status reaches green/yellow threshold.

### Action Prioritization
- Rank correction actions by expected variance reduction per effort unit.
- Recommend max 5 actions per cycle to avoid analysis overload.

### Signoff Policy
- Red variance blocks investor-ready status.
- Yellow requires explicit financial waiver.
- Green auto-advances to packaging phase.

### Learning Loop
- Persist convergence trajectories to improve future default assumptions.

