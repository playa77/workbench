---
title: Cost Breakdown Structure (CBS) Generation
date: 2026-02-10
status: proposal
author: Larry the Laptop Lobster
---

# Cost Breakdown Structure (CBS) Generation

## Pitch
Automatically generate a Cost Breakdown Structure (CBS) from a plan, mapping scope to cost categories, subcategories, and line items with assumptions and confidence levels.

## Why
Most plans mention costs but do not structure them. A CBS enables:

- Comparable cost estimates across plans.
- Immediate visibility into cost drivers.
- Faster budgeting, funding, and procurement decisions.

## Problem
Without a CBS:

- Cost claims are vague or non-auditable.
- Missing categories create hidden risk.
- Downstream financial models are inconsistent.

## Proposed Solution
Implement a CBS generator that:

1. Parses plan scope and milestones.
2. Maps scope elements to standard cost categories.
3. Produces a multi-level CBS with assumptions and ranges.
4. Assigns confidence and missing-info flags.

## CBS Taxonomy (Default)

Level 1 categories:

- Labor
- Materials
- Equipment
- Software and Licenses
- Facilities
- Professional Services
- Compliance and Legal
- Operations and Maintenance
- Contingency

Level 2 examples:

- Labor: engineering, project management, field staff
- Materials: raw materials, components, consumables
- Facilities: rent, utilities, site prep
- Compliance: permits, audits, regulatory fees

## Generation Process

### 1) Scope Extraction
Identify:

- Deliverables (what will be built or delivered)
- Work packages (tasks and milestones)
- Dependencies and external services

### 2) Mapping Rules
Apply mapping from scope to cost categories:

- Physical deliverables -> materials + equipment + labor
- Software deliverables -> labor + cloud + licenses
- Regulated projects -> compliance + legal

### 3) Cost Estimation
Use a combination of:

- Benchmark ratios (per unit, per employee, per square meter)
- Historical PlanExe costs
- User-provided or inferred quantities

### 3.1) Multi-Currency Handling

Plans may involve multiple currencies (e.g., cross-border bridge projects). The CBS should:

- Capture line items in their native currency.
- Store a reporting currency for rollups (default to plan base currency).
- Record FX assumptions (rate, date, source, volatility band).
- Allow dual-currency rollups when contracts are split by jurisdiction.

### 4) Confidence Assignment

- High: explicit quantities and pricing provided.
- Medium: benchmark-based estimates.
- Low: inferred or missing data.

## Output Schema

```json
{
  "cbs": [
    {
      "category": "Labor",
      "subcategories": [
        {"name": "Engineering", "estimate": 420000, "currency": "EUR", "confidence": "medium"},
        {"name": "Project Management", "estimate": 120000, "currency": "EUR", "confidence": "medium"}
      ]
    },
    {
      "category": "Compliance and Legal",
      "subcategories": [
        {"name": "Permits", "estimate": 30000, "currency": "DKK", "confidence": "low"}
      ]
    }
  ],
  "total_estimate": 570000,
  "reporting_currency": "EUR",
  "fx_assumptions": [
    {"pair": "DKK/EUR", "rate": 0.13, "as_of": "2026-02-10", "volatility": "medium"}
  ],
  "contingency": 0.12,
  "assumptions": [
    "Engineering team of 5 for 12 months",
    "Permit costs based on regional averages"
  ]
}
```

## Integration Points

- Feed into top-down and bottom-up finance modules.
- Use as a checklist for missing cost categories.
- Provide input to bid pricing and risk analysis.

## Success Metrics

- % plans with a generated CBS.
- Reduction in unaccounted cost categories during review.
- Alignment between CBS totals and final budget.

## Risks

- Over-simplified categories: mitigate with domain-specific mappings.
- False precision: provide ranges and confidence labels.
- Missing quantities: require user clarification prompts.

## Future Enhancements

- Domain-specific CBS templates.
- Automated cost library updates.
- Integration with procurement and supplier pricing feeds.

## Detailed Implementation Plan

### 1) Canonical CBS taxonomy service

Create a versioned taxonomy module:
- global categories (L1)
- domain-specific subcategories (L2/L3)
- mapping aliases (e.g., “permits” -> compliance/legal)

This avoids inconsistent CBS labels across plans.

### 2) WBS-to-CBS mapper

Implement deterministic + ML-assisted mapper:
1. Rule-based first pass from task metadata and keywords.
2. LLM-assisted classification for ambiguous tasks.
3. Confidence score and explanation per mapping.

Store mapping artifacts:
- `wbs_task_id`
- `cbs_path`
- `mapping_confidence`
- `mapping_reason`

### 3) Cost line generation

For each mapped task, generate cost lines:
- quantity
- unit
- unit rate
- currency
- low/base/high estimate
- source (user input, benchmark, quote, inferred)

Represent uncertainty explicitly; avoid single-point false precision.

### 4) Assumptions and provenance registry

Every cost line should reference an assumption record:
- assumption text
- evidence source
- owner
- last update timestamp

Provide “assumption drift” detection if benchmarks change.

### 5) CBS outputs and exports

Generate:
- hierarchical CBS table
- WBS↔CBS crosswalk table
- top cost drivers with sensitivity
- export to CSV/XLSX/JSON for finance tooling

### 6) Integration with top-down and bottom-up finance

- Top-down uses CBS categories for ratio application.
- Bottom-up consumes CBS line items as task-level cost ledger.
- Reconciliation reports highlight CBS categories causing variance.

### 7) API contract proposal

```json
{
  "plan_id": "...",
  "cbs_version": "v1.0",
  "currency": "USD",
  "items": [
    {
      "wbs_task_id": "3.2",
      "cbs_path": "Labor/Engineering/Backend",
      "estimate": {"low": 50000, "base": 70000, "high": 95000},
      "confidence": "medium",
      "assumption_id": "asm_42"
    }
  ]
}
```

### 8) Rollout phases

- Phase A: rule-based mapping + static taxonomy
- Phase B: confidence scoring + assumption registry
- Phase C: export + integration with finance modules
- Phase D: live vendor pricing and automated refresh

### 9) Validation checklist

- Coverage: % WBS tasks mapped to valid CBS nodes
- Consistency: repeated runs produce stable mappings
- Auditability: every line has source + assumption
- Usability: finance users can edit/approve CBS quickly

## Detailed Implementation Plan (Finance Integration)

### Domain Template Strategy
- Start with 5 templates: software, infra, manufacturing, nonprofit, public sector.
- Fallback to generic taxonomy when domain confidence < threshold.

### Editing Workflow
1. Auto-generate CBS draft.
2. User reviews low-confidence lines first.
3. Finance reviewer signs off final CBS baseline.

### Change Control
- Every CBS edit creates a diff record with rationale.
- Lock finalized CBS version for downstream reconciliation.

### Export Targets
- CSV for analysts
- XLSX for procurement/accounting
- JSON for API consumers

