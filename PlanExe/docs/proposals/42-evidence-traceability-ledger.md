---
title: "Evidence Traceability Ledger: Technical Documentation"
date: 2026-02-11
status: proposal
author: PlanExe Team
---

# Evidence Traceability Ledger: Technical Documentation

**Author:** PlanExe Team  
**Date:** 2026-02-11  
**Status:** Proposal  
**Audience:** Developers, Auditors, Investors  

---

## Overview
The **Evidence Traceability Ledger** is a core component of the PlanExe verification engine. It transforms vague claims into verifiable facts by maintaining a cryptographically-linked ledger of every claim made in a plan and its corresponding evidence.

Unlike a simple citation list, this ledger systems:
1.  **Extracts atomic claims** from unstructured plan text.
2.  **Scores evidence strength** (Level 1-3) using automated heuristics and expert verification.
3.  **Monitors freshness** of linked data sources.
4.  **Generates audit trails** for investor due diligence.

## Use Cases
- **Investor Diligence:** "Show me the source for the $4.2B TAM claim and when it was last verified."
- **Living Plans:** "Alert me if the regulatory approval document expires."
- **Automated Verification:** "Reject any plan with >20% Level 1 (anecdotal) evidence."

## System Architecture

### 1. Claim Extraction Pipeline
When a plan is submitted or updated:
1.  **Parsing:** The plan markdown is parsed into semantic blocks.
2.  **Claim Detection:** An LLM (`gemini-2.0-flash`) identifies discrete factual claims (e.g., "Market grows at 5% CAGR", "Patent #12345 granted").
3.  **Fingerprinting:** Each claim is hashed for change detection.

### 2. Evidence Mapping & Scoring
Each extracted claim must be linked to an evidence source.
-   **Automated Linking:** URL scraping and semantic matching.
-   **Manual Linking:** User uploads documents (PDFs, contracts).
-   **Scoring Engine:** Assigns a `VerificationLevel` (1-3) based on source reliability.

### 3. The Ledger (Storage)
A `ledger_entries` table tracks the state of every claim-evidence pair over time, creating an immutable history of truth.

---

## Data Tables

### `claims`
Stores atomic assertions extracted from the plan.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Primary Key |
| `plan_id` | UUID | FK to Plans |
| `content` | TEXT | The extracted text of the claim |
| `location_ref` | TEXT | Pointer to section/line in the plan |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

### `evidence`
Stores the source material data.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Primary Key |
| `source_type` | ENUM | `url`, `document`, `database_record` |
| `uri` | TEXT | URL or S3 path |
| `snapshot_hash` | TEXT | SHA-256 of the content at time of capture |
| `verification_level` | INT | 1 (Weak) to 3 (Strong) |
| `last_verified_at` | TIMESTAMPTZ | Freshness timestamp |

### `ledger_entries`
The join table linking claims to evidence with status.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Primary Key |
| `claim_id` | UUID | FK to Claims |
| `evidence_id` | UUID | FK to Evidence |
| `status` | ENUM | `verified`, `disputed`, `stale`, `missing` |
| `verifier_id` | UUID | FK to User or Agent |
| `notes` | TEXT | Reviewer comments |

---

## API Reference

### `POST /api/ledger/extract`
Trigger manual extraction of claims for a plan section.

**Request:**
```json
{
  "plan_id": "uuid...",
  "section_content": "The market is projected to reach $50B by 2030...",
  "force_refresh": true
}
```

**Response:**
```json
{
  "claims": [
    {
      "claim_id": "c_123",
      "content": "Market projected to reach $50B by 2030",
      "suggested_evidence_type": "market_report"
    }
  ]
}
```

### `POST /api/ledger/link`
Attach evidence to a specific claim.

**Request:**
```json
{
  "claim_id": "c_123",
  "evidence_uri": "https://doi.org/10.1038/s41586-020-2012-7",
  "evidence_type": "url"
}
```

### `GET /api/ledger/report/{plan_id}`
Get the full traceability report.

**Response:**
```json
{
  "plan_id": "uuid...",
  "overall_score": 88,
  "claims_total": 50,
  "claims_verified": 45,
  "freshness_concerns": 2,
  "entries": [
    {
      "claim": "Patent #12345 granted",
      "status": "verified",
      "level": 3,
      "source": "USPTO Database",
      "last_checked": "2026-02-10"
    }
  ]
}
```

---

## Algorithm: Freshness Scoring

Evidence degrades over time. The system calculates a `freshness_score` (0.0 - 1.0) daily.

```python
def calculate_freshness(evidence_type: str, last_verified: datetime) -> float:
    age_days = (datetime.now() - last_verified).days
    
    # Decay rates based on type
    half_life_days = {
        'financial_statement': 90,  # Quarterly
        'market_report': 365,       # Yearly
        'news_article': 30,         # Fast moving
        'legal_contract': 1095,     # 3 Years
        'academic_paper': 1825      # 5 Years
    }
    
    tau = half_life_days.get(evidence_type, 180)
    score = 0.5 ** (age_days / tau)
    
    return score
```

Using this score, the UI flags items as "Stale" (score < 0.5) or "Expired" (score < 0.1).

---

## User Interface

### Sidebar Ledger
A slide-out panel in the plan editor shows the "Evidence Health" of the current section.
-   **Green checkmarks** for verified Level 3 claims.
-   **Yellow warnings** for stale evidence.
-   **Red alerts** for unverified claims > 48 hours old.

### Audit View
A specialized view for investors that hides the prose and focuses on the `Claim -> Evidence` graph.
-   Filters by "Verification Level".
-   "Challenge" button to requesting updated evidence for specific claims.

## Future Roadmap
1.  **Blockchain Anchoring:** Hash ledger entries to a public chain for tamper-proof history.
2.  **Automated Crawler:** Agent that periodically re-checks URLs for 404s or content changes.
3.  **Citation Graph:** Visualize how one piece of evidence supports multiple claims across different plans (e.g., a shared market report).

## Detailed Implementation Plan

### Phase A — Claims Pipeline Foundation (2–3 weeks)

1. Add section-aware parser for plan markdown/JSON artifacts.
2. Implement claim extraction with stable claim IDs:
   - hash = normalized claim text + location_ref + plan_version
3. Create confidence classifier for extracted claims:
   - factual numeric
   - factual non-numeric
   - normative/opinion (excluded from strict ledger)

### Phase B — Evidence Ingestion + Scoring (2–3 weeks)

1. Build evidence adapters:
   - URL fetch + snapshot hash
   - document upload + OCR extraction
   - structured source connectors (registry/DB)

2. Implement verification-level scoring policy:
   - Level 1: weak/secondary
   - Level 2: credible but indirect
   - Level 3: primary authoritative evidence

3. Introduce freshness profile by evidence type with default half-life values.

### Phase C — Ledger Integrity + Audit (2 weeks)

1. Append-only `ledger_entries` with immutable versioning.
2. Add digital signature of report bundle and ledger digest.
3. Implement dispute flow:
   - mark `disputed`
   - assign reviewer
   - record resolution actions

### Phase D — Product Integration (2 weeks)

1. Add inline plan UI badges per claim:
   - verified / stale / missing / disputed
2. Add investor audit export endpoint:
   - summary + full trace tables + signatures
3. Add policy gate:
   - block “investor-ready” status if verification coverage below threshold

### Suggested quality thresholds

- >=80% claims must have evidence link
- >=60% claims must be Level 2+
- 0 critical claims in `missing` or `disputed` state

### Data model hardening

- Add `plan_version` to claims and ledger rows
- Add `source_fetch_status` and `source_http_code`
- Add `evidence_expiry_at` for freshness checks

### Operational safeguards

- Cache source snapshots to avoid link rot dependence
- Rate-limit external crawlers
- PII redaction on uploaded documents before indexing

### Validation checklist

- Claim extraction precision/recall benchmarks
- Deterministic claim IDs across reruns
- Tamper detection test via signature mismatch
- Freshness state transition tests
- Audit export completeness checks
