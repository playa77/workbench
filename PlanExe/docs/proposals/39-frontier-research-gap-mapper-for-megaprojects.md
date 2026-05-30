---
title: "Frontier Research Gap Mapper for Mega-Projects"
date: 2026-02-10
status: proposal
author: PlanExe Team
---

# Frontier Research Gap Mapper for Mega-Projects

**Author:** PlanExe Team  
**Date:** 2026-02-10  
**Status:** Proposal  
**Tags:** `research`, `frontier`, `megaprojects`, `feasibility`, `innovation`

## Pitch
Detect where a plan depends on unresolved science or engineering and map those dependencies into a structured R&D register before committing to a bid.

## Why
Some plans require breakthroughs, not just execution discipline. Hidden research dependencies are major bid risks that should be explicit, costed, and staged.

## Problem

- Frontier gaps are often implicit, not stated.
- Feasibility assessments assume mature technology.
- Bids proceed before critical R&D constraints are understood.

## Proposed Solution
Create a module that:

1. Identifies plan components that exceed current state-of-practice.
2. Classifies maturity level and research gaps.
3. Produces a research dependency register with timelines and uncertainty.
4. Adjusts bidability and feasibility scores accordingly.

## Classification Framework

Each component is tagged as:

- **Mature:** proven in real-world deployments.
- **Adaptation Required:** proven elsewhere but needs modification.
- **Frontier:** unproven at required scale or conditions.

## Research Dependency Register

Each gap includes:

- Challenge statement
- Current state-of-practice
- Missing capability threshold
- Estimated R&D timeline
- Cost uncertainty band

## Example Challenge Classes (Arctic Bridge)

- ultra-cold concrete curing and durability
- ice-load resistant structural systems
- remote logistics and year-round constructability
- cross-border governance and standards harmonization

## Output Schema

```json
{
  "component": "ice_load_resilience",
  "maturity": "frontier",
  "gap": "No validated structural system for multi-year ice pack",
  "estimated_rnd_years": 3,
  "cost_uncertainty": "high"
}
```

## Integration Points

- Feeds into risk propagation network and Monte Carlo success probability.
- Applies bidability penalty for unresolved frontier gaps.
- Triggers pre-bid R&D phase recommendations.

## Success Metrics

- Fewer bids on technically premature opportunities.
- Better planning of R&D-first project phases.
- Reduced execution failure from unknown technical gaps.

## Risks

- Over-classification of challenges as frontier.
- Incomplete research signals due to limited sources.
- R&D timelines difficult to estimate accurately.

## Future Enhancements

- Automated scanning of research literature and patents.
- Expert panels for frontier assessment.
- Continuous updates as research advances.

## Detailed Implementation Plan

### Phase 1: Frontier Detection Framework

1. Build capability taxonomy by domain:
   - materials science
   - civil/structural engineering
   - logistics in extreme environments
   - cross-border governance and standards

2. Implement maturity classifier:
   - mature / adaptation required / frontier
   - confidence score with evidence references

3. Attach evidence retrieval:
   - standards databases
   - recent publications/patents
   - comparable projects and postmortems

### Phase 2: Research Dependency Register

For each frontier dependency, generate:
- challenge statement
- missing capability threshold
- candidate research tracks
- expected R&D duration/cost ranges
- kill criteria for failed approaches

Store as a first-class artifact linked to plan sections.

### Phase 3: Bidability and sequencing logic

1. Compute a frontier feasibility index.
2. Adjust bid/no-bid recommendation based on unresolved high-severity frontier items.
3. Insert pre-bid R&D phases before main execution phases when required.

### Example for Bering-style bridge scenario

Unresolved class: cold-climate concrete performance.

System output should include:
- what performance threshold is missing
- current evidence gap
- 3 candidate pathways to close the gap
- timeline + budget impact per pathway

### Data model additions

- `frontier_dependencies` (plan_id, component, maturity, severity, confidence)
- `research_tracks` (dependency_id, hypothesis, timeline_range, cost_range)
- `frontier_index` (plan_id, score, blockers_count)

### Governance hooks

- Require expert signoff for high-severity frontier dependencies.
- Prevent final “verified” status if critical frontier blockers unresolved.

### Validation checklist

- Expert review agreement on maturity labels.
- Correlation between frontier index and downstream execution risk.
- Reduction in technically premature bids.

## Detailed Implementation Plan (R&D Programization)

### Frontier Detection Ops
- Build challenge classifiers for materials, environment, logistics, and policy domains.
- Attach evidence references for each frontier label.

### Research Program Builder
- Convert frontier gaps into staged R&D tracks with gates:
  - feasibility proof
  - pilot validation
  - scale readiness

### Bid Integration
- Add bidability penalty for unresolved critical frontier gaps.
- Surface required pre-bid R&D budget/time in executive summary.

### Validation
- Compare mapper outputs with expert panel assessments.

