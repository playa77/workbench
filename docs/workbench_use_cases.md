# Workbench — Family Office Demonstration Guide

> **Version:** 1.0.0 | 2026-06-26
> Generated from a full codebase review of Workbench v0.1.6.
> Knowledge Base agent excluded — still in alpha.

---

## Overview

Workbench is a self-hosted, Bring-Your-Own-Key (BYOK) AI dashboard running 8 LLM-powered agents, each in its own browser tab. Every LLM call flows through a single auditable `OpenRouterClient` path. No telemetry. All data encrypted at rest with AES-256-GCM.

For a family office audience, the key selling points are:
- **Self-hosted** — data never leaves your infrastructure
- **BYOK** — you control the model provider and costs via OpenRouter
- **Multi-agent** — each agent solves a different class of problem, from strategic planning to adversarial stress-testing
- **Zero telemetry** — no vendor lock-in, no analytics, no phoning home

The agents relevant to family office workflows (excluding Knowledge Base) are presented below with curated demonstration prompts.

---

## Agent 1: Chat

**Tab:** Chat | **Icon:** message-circle
**Description:** Plain LLM conversation with any OpenRouter model. Stateless, single-turn.
**What it does:** Send a message, get a full response. No streaming, no tools, no session state — pure text completion.

### Family Office Use Cases

The Chat agent is the "general purpose" interface — best for quick questions, drafting, and one-off queries where you don't need the specialized agents.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | *"Draft a quarterly investment letter for a multi-generational family office. The portfolio is globally diversified (60% equities, 25% fixed income, 10% private equity, 5% real assets). Q2 saw moderate growth with some tech sector volatility. Tone: professional, reassuring, educational. Include a section on long-term horizon advantages."* | How quickly the LLM produces polished, client-ready communications — the kind of letter that a family office investment team might spend hours drafting. |
| 2 | *"Explain the concept of carried interest in private equity to a family member who is not financially trained. Use simple analogies and avoid jargon."* | Shows the LLM's ability to translate complex financial concepts for family members with different levels of sophistication — a perennial challenge in family offices. |
| 3 | *"Compare DAFs (Donor-Advised Funds) and private foundations for a family that gives ~$500K annually to charitable causes. Consider setup complexity, ongoing costs, tax deductions, control, and privacy. Format as a comparison table."* | Demonstrates practical advisory capability on philanthropic structuring, a core family office function. The table format shows the model can produce structured, decision-ready output. |

### What to Highlight During the Demo

- **Speed:** Response comes back in seconds — no typing time.
- **Model flexibility:** You can switch between OpenRouter's 200+ models depending on cost/quality tradeoffs.
- **Stateless simplicity:** No setup. Paste a prompt, get an answer. Ideal for quick questions during a meeting.

---

## Agent 2: News Pipeline

**Tab:** News Pipeline | **Icon:** newspaper
**Description:** Multi-interest AI-powered RSS news scraper, theme analyzer, and content generator.
**What it does:** You define "interests" (topic areas), attach RSS feeds, configure a schedule. The pipeline fetches articles, scrapes full text, uses AI to identify themes, and generates deliverables: summaries, scripts, and daily briefs. Optional SMTP email delivery. Runs on a background scheduler with catch-up logic.

### Family Office Use Cases

This is the information-intelligence engine. A family office tracks dozens of signals — competitors, regulators, markets, industries. This agent automates the monitoring → synthesis → delivery chain.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | **Setup:** Create an interest called "Energy Transition" with RSS feeds from Reuters Energy, Bloomberg Green, S&P Global Commodity Insights, and IEA news. Configure daily runs at 06:00, 750-word summaries, enable email delivery. Run once manually to show immediate output. | The full pipeline lifecycle: define a topic → attach feeds → one-click run → AI-identified themes → deliverable (summary + brief). Shows how the family office can stay on top of a thematic investment area without manual reading. |
| 2 | **Setup:** Create an interest called "Regulatory Watch" with feeds from SEC, ESMA, FINRA, and major law firm regulatory blogs. Set interval to every 48 hours. Show the "themes" output where the AI clusters articles into coherent topics (e.g., "AIFMD II implementation", "SEC private fund adviser rule"). | Demonstrates automated regulatory monitoring — critical for compliance and legal risk management in a family office with cross-border interests. |
| 3 | **Pre-baked output:** Show a previously generated daily brief from a "Competitor Intelligence" interest (tracking other family offices, multi-family offices, and wealth managers). Highlight how the AI-generated script can be used as a morning briefing memo. | Shows the "finished product" value: a concise, theme-organized brief that an investment professional can read in 5 minutes instead of scanning 50 articles. |

### What to Highlight During the Demo

- **Zero manual reading:** The AI reads everything and tells you what matters.
- **Schedule + catch-up:** Runs automatically; if the server was down, it catches up.
- **Email delivery:** Briefs can arrive in the inbox before the morning meeting.
- **Per-user configuration:** Each family office professional can have their own interests and feeds.

---

## Agent 3: Debate Arena

**Tab:** Debate Arena | **Icon:** users
**Description:** Multi-agent AI debate arena — assemble a panel of 12 persona roles with Director Mode.
**What it does:** Pick 2–8 AI personas (Optimist, Pessimist, Pragmatist, Strategist, Contrarian, Historian, Futurist, Capitalist, Marxist, Stoic, Machiavelli, Debitist), set a topic and max rounds (1–50), and watch them debate turn-by-turn. Director Mode lets you inject influence (subtle/moderate/critical) to steer the debate. Pause/resume supported.

### Family Office Use Cases

This agent shines when you need to surface blind spots in an investment thesis, a governance decision, or a strategic move. It forces every perspective to the table — including the ones nobody in the room wants to voice.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | **Topic:** *"Should this family office increase its allocation to private credit from 8% to 18% over the next 3 years?"* **Panel:** Optimist, Pessimist, Pragmatist, Strategist, Contrarian, Capitalist. **Rounds:** 5 | A realistic family office allocation decision. Watch the Optimist talk about yield premiums and illiquidity premia; the Pessimist flag default risk, covenant-lite structures, and correlation to public credit in a downturn; the Capitalist discuss market dynamics and fund manager selection; the Contrarian challenge the entire premise by arguing for public equities instead. 5 rounds produce deep, interlocking analysis. |
| 2 | **Topic:** *"Should the family relocate its holding company from Delaware to Wyoming?"* **Panel:** Pragmatist, Historian (tax law precedent), Strategist (multi-generational planning), Pessimist. **Rounds:** 3. **Director Mode:** At round 2, inject *"Consider the impact on existing limited partnership agreements that specify Delaware governing law."* | Demonstrates Director Mode — the ability to insert a real constraint mid-debate that changes the conversation. Shows how the panel adapts and re-evaluates. |
| 3 | **Topic:** *"Is now the right time to sell the family's majority stake in a 3rd-generation manufacturing business?"* **Panel:** Historian (what happened to families that sold vs. held), Futurist (manufacturing automation trends), Capitalist (valuation multiples), Stoic (emotional and legacy considerations), Machiavelli (buyer tactics, negotiating leverage). **Rounds:** 4 | A deeply personal family office decision. The range of perspectives — from cold financial analysis to emotional legacy — demonstrates how the Debate Arena surfaces dimensions that a spreadsheet cannot. |

### What to Highlight During the Demo

- **Adversarial reasoning:** The AI does not "agree to be helpful" — each persona fights for its perspective, producing genuine clash.
- **Director Mode:** You are not a passive observer. You can steer by injecting facts, constraints, or questions mid-debate.
- **Turn-by-turn visibility:** You see each persona's reasoning as it happens. No black box.
- **Export:** The full debate is exportable as JSON for documentation or board materials.

---

## Agent 4: Deep Research

**Tab:** Deep Research | **Icon:** search
**Description:** Autonomous web research agent — produce cited, publication-quality reports.
**What it does:** Given a research question, the agent uses function-calling to: (1) decompose the question into sub-topics, (2) search the web via Brave Search API, (3) read full webpages, (4) extract and record findings, (5) detect contradictions between sources, (6) produce a single cited markdown report with inline `[N]` citations. Configurable tree depth (1–5) and branching factor (1–10). SSE streaming shows live progress.

### Family Office Use Cases

This is the due diligence engine. Any investment memo, market landscaping exercise, or regulatory deep-dive that currently takes an analyst days can be reduced to a 5–15 minute research run.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | *"Research the secondary market for LP fund stakes. What are current pricing trends, major platforms (e.g. Palico, Nasdaq Private Market, Moonfare), typical discounts/premiums by strategy (PE, VC, real estate, infra), and the regulatory landscape for accredited investors? Identify 3–5 leading secondary funds and their recent performance."* **Depth:** 2, **Branching:** 5 | A classic family office investment topic. The agent will search for market data, fund performance, regulatory guidance, and platform capabilities — then synthesize a single report. The demo should let the live SSE stream run so the audience sees searches happening in real time. |
| 2 | *"Investigate family office direct investing trends in 2025–2026. What sectors are most active (healthcare, AI/technology, climate)? What deal sizes are typical? How do family offices source deals vs. traditional PE? What are the governance challenges? Include data on direct investment returns vs. fund investments."* **Depth:** 3, **Branching:** 4 | Demonstrates deeper tree depth (3 levels, up to 64 leaf topics). Shows how the agent drills into sub-topics methodically. The output is a comprehensive market intelligence report a family office would commission from a consultant for $15K+. |
| 3 | *"What are the tax implications of a US family office establishing a Singapore-based 'Section 13O' fund structure? Cover the Monetary Authority of Singapore requirements, US PFIC and CFC rules, US-Singapore tax treaty implications, reporting obligations (FBAR, FATCA, Form 3520), and typical setup costs and timelines."* | Cross-border tax structuring — bread and butter for international family offices. The agent will find primary regulatory sources, practitioner commentary, and flag contradictions (e.g., when two sources disagree about the minimum AUM or local spending requirements). The live "contradiction detection" events are specifically impressive during a demo. |

### What to Highlight During the Demo

- **Live visibility:** The SSE stream shows every search query, every webpage read, every finding recorded — the audience watches the research happen.
- **Contradiction detection:** When two sources disagree, the agent flags it. This is critical for investment due diligence where consensus is often wrong.
- **Tree topology:** The configurable depth/branching shows you can tune breadth vs. depth depending on whether you want a survey or a deep dive.
- **Cited output:** Every claim in the report links to a numbered source. The report is publication-ready, not a chatbot hallucination.
- **Stop/resume:** You can abort a run if it's heading in the wrong direction and refine the question.

---

## Agent 5: Consigliere (Deliberation)

**Tab:** Consigliere | **Icon:** scale
**Description:** Your contrarian consigliere — stress-tests any idea by finding weak links, probing blind spots, and iterating toward a bulletproof version.
**What it does:** Brings 8 analysis frames to bear on your question. Runs N rounds of pairwise critique (every frame critiques every other frame, N^2-N pairs per round). Optional rhetoric analysis identifies persuasive techniques, biases, inconsistencies, and cross-frame contradictions. Generates a "disagreement surface" mapping where frames converge and diverge. Final synthesis produces a multi-layered answer with explicit uncertainty markers.

**The 8 frames:** Deliberation Director, Critique Agent, Rhetoric Analyst, Synthesis Agent, Pro/Con, SWOT, Stakeholder, Driving Forces.

### Family Office Use Cases

This is the decision-quality assurance agent. Before a major commitment — an investment, a restructuring, a hire, a governance change — you run it through the Consigliere to find what you missed.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | *"We are considering converting our family office from a Single Family Office (SFO) structure to a Multi-Family Office (MFO) to bring in 3–4 additional families, sharing operational costs and increasing negotiating power with asset managers. We manage approximately $800M across our family and the prospective families are trusted peers with $150–400M each. We are concerned about: loss of control, conflicts of interest, regulatory complexity, and cultural fit."* **Frames:** Pro/Con, SWOT, Stakeholder, Driving Forces, Critique Agent. **Rounds:** 3. **Rhetoric:** ON. **Synthesis:** ON. | A high-stakes strategic decision with many stakeholders and non-financial dimensions. Watch the frames develop their positions in Phase 1, then tear each other apart in Phase 2–3 (pairwise critique). The Rhetoric Analysis will identify where emotional language ("trusted peers," "loss of control") might be clouding judgment. The Synthesis will produce a nuanced recommendation with explicit confidence levels. |
| 2 | *"Should we hire an external CIO for the family office, or continue with the current model where the family patriarch makes final investment decisions with input from a 3-person internal team? The patriarch is 72 and succession planning is becoming urgent. The internal team has strong operational skills but limited experience in alternatives and cross-border structuring."* **Frames:** Pro/Con, Stakeholder (family members, internal team, external managers, beneficiaries), SWOT, Critique Agent. **Rounds:** 2. Rhetoric and Synthesis ON. | A succession planning decision with deep emotional and practical dimensions. The Stakeholder frame will map how each party is affected. The Critique Agent will challenge — does the patriarch actually want to cede control? Will the internal team resist an external hire? The Synthesis will not give a simple yes/no but a layered answer with conditions. |
| 3 | *"We are evaluating a co-investment opportunity: a $25M Series C in a European climate-tech company (direct air capture technology). The lead investor is a reputable European VC. The technology is pre-revenue with 3 pilot projects. Our due diligence identified strong IP but significant regulatory uncertainty around carbon credit pricing in the EU. The investment would represent 5% of our liquid portfolio."* **Frames:** SWOT, Critique Agent, Driving Forces, Synthesis Agent. **Rounds:** 2. | A concrete deal evaluation. The Driving Forces frame will map regulatory tailwinds (EU Green Deal, carbon border adjustment) against headwinds (political pushback, technology risk). The Critique Agent will stress-test the "reputable VC" assumption and the carbon credit price forecasts. This is exactly how a family office investment committee should pressure-test a deal before committing. |

### What to Highlight During the Demo

- **Phase tracking:** The SSE stream shows which phase is active — the audience sees frames being generated, then the critique rounds grinding through every frame pair.
- **Disagreement surface:** The visualization of where frames agree and disagree is uniquely valuable — it tells you which parts of the decision are settled and which need further work.
- **Rhetoric analysis:** When it flags "overconfident language" or "emotional valence" in your own framing — the audience realizes the AI is analyzing *their* thinking, not just the answer.
- **Uncertainty awareness:** The Consigliere explicitly says "I'm not sure about X because Y" rather than fabricating confidence.
- **Iterative:** You can re-run with different frames, more rounds, or a refined question — each run gets deeper.

---

## Agent 6: Strategic Planning

**Tab:** Strategic Planning | **Icon:** target
**Description:** AI-powered strategic planning — 9 plan types including project plans, SWOT, WBS, RCA, pitches, and governance frameworks.
**What it does:** You describe a goal and select a plan type. The agent generates a comprehensive, structured plan as a markdown document with SSE streaming. Auto-detects German vs. English input.

**The 9 plan types:** Project Plan, SWOT Analysis, Executive Summary, Work Breakdown Structure (WBS), Schedule/Timeline, Root Cause Analysis (RCA), Pitch/Proposal, Governance Framework, Team Composition.

### Family Office Use Cases

This agent produces structured, actionable documents — the kind that go into board packs, investment committee decks, and operational manuals.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | **Plan Type:** Governance Framework. *"Design a governance framework for a 3rd-generation family office with: 15 family members across 4 branches, an investment committee, a family council, and a next-gen education program. The family's wealth derives from a sold industrial business and is now a diversified portfolio. Key issues: branch representation, voting rights for spouses, dispute resolution mechanism, and a process for family members to opt out of pooled investments."* | Governance is the #1 challenge for multi-generational family offices. This plan type produces: governance bodies with clear mandates, decision escalation matrices, meeting cadences, committee charters, and monitoring mechanisms. The output is a board-ready framework document. |
| 2 | **Plan Type:** Root Cause Analysis. *"Our family office's private equity co-investments have underperformed our fund investments by 480bps annually over the past 5 years. Analyze root causes using 5-Why methodology. Consider: deal sourcing quality, due diligence process, co-investor selection, fee structures, adverse selection (are we being offered the deals others passed on?), and post-investment monitoring."* | RCA is a structured diagnostic tool. The 5-Why chain will trace surface symptoms (lower returns) to root causes (e.g., "we lack dedicated co-investment sourcing capability → because the investment team is structured for fund selection not deal evaluation → because..."). This is exactly the kind of analysis an investment committee needs when something isn't working. |
| 3 | **Plan Type:** Pitch/Proposal. *"Prepare an internal pitch for the family council to approve a $10M allocation to a direct indexing program, replacing 40% of our current ETF exposure. The program would enable tax-loss harvesting at the individual security level, ESG custom screens, and concentrated position management. Address: cost comparison vs. ETFs, tax alpha estimates, operational complexity, and implementation timeline."* | Every major allocation change in a family office requires internal buy-in. This plan type generates a persuasive, structured proposal with problem statement, solution, market analysis, competitive advantage, and ask. The family council can read this as a standalone memo. |
| 4 | **Plan Type:** Team Composition. *"Design the organizational structure for our family office's investment team. We currently have 3 people (CIO, analyst, operations). We are growing to manage $1.2B across public equities, private markets, real estate, and direct investments. Define roles, responsibilities, required skills, reporting lines, and hiring/onboarding recommendations. Consider: should we hire generalists or specialists? In-source or out-source manager selection?"* | As family offices professionalize, team design becomes critical. This output gives role descriptions with skill matrices, organizational chart, hiring phasing, and the make-vs-buy decision framework for each function. |

### What to Highlight During the Demo

- **9 specialized templates:** Each plan type has a dedicated system prompt — it's not a generic "write a plan" request. The LLM is guided by domain-specific instructions.
- **Structure quality:** The outputs use SMART goals, RACI matrices, decision escalation tables, Gantt-style timelines — real planning artifacts, not prose.
- **German support:** For international families, auto-detection of German input with German-language output is a practical feature.
- **PDF export:** Plans can be exported as professional PDFs via LaTeX templates (Professional, Tufte, Classic, Modern, Compact, Manuscript). A Governance Framework printed on the Tufte template in a boardroom makes an impression.

---

## Agent 7: Math Tutor

**Tab:** Math Tutor | **Icon:** scale
**Description:** Step-by-step math tutor with adaptive competency — discuss complex problems with embedded equations, get per-concept checkpoints, and comprehensive MC interviews.
**What it does:** Interactive, session-based math tutoring. You describe a problem through a structured interview (equation type, order, nature, components) or free-form chat. The tutor explains reasoning step-by-step with LaTeX rendering. Adaptive competency tracking (4 levels: Smart High School Senior → College Freshman → College Senior → Grad Student) adjusts explanation depth. Per-concept checkpoint MC questions assess understanding. Deep-dive mode for exploring specific concepts. SSE streaming throughout.

### Family Office Use Cases

Math proficiency is relevant for family offices in two ways: (1) next-gen education — teaching younger family members financial mathematics, and (2) professional development — upskilling investment staff on quantitative methods.

| # | Demo Prompt | What It Showcases |
|---|-------------|-------------------|
| 1 | **Session:** Structured interview → ODE → 1st order → linear. **Equation:** `dy/dt + r*y = C`. *Student: "I'm learning about time value of money. Can you walk me through how this differential equation relates to continuous compounding and discounting?"* Let the tutor explain, then trigger a deep-dive on "why does the exponential function appear?" — show the step-by-step derivation from first principles. | Demonstrates the full interaction model: structured input → chat → deep-dive → checkpoint MC. A family office educating next-gen members on financial math — the tutor adjusts to the student's level, explains not just the "what" but the "why," and checks understanding with MC questions. |
| 2 | **Session:** Structured interview → Algebraic Equation → linear. **Equation:** `(1 + r)^n * PV = FV`. *Student: "Our family's wealth is invested in a portfolio that returns about 7% annually. If we don't touch the principal, how do I think about the real purchasing power in 30 years after inflation? Walk me through it step by step."* | Practical family office math. The tutor can explain compound growth, introduce inflation adjustment, discuss real vs. nominal returns, and connect to Monte Carlo concepts if the student is ready. The competency tracking ensures the explanation doesn't assume too much or too little. |
| 3 | **Session:** Free-form. *"Explain the Kelly Criterion for position sizing in a portfolio context. Walk me through the derivation, the assumptions it makes, and when it's appropriate vs. when it breaks down for a family office managing multi-generational wealth."* Then follow up: *"What about the difference between full Kelly and half-Kelly? And how does this connect to the Merton portfolio problem?"* | Advanced quantitative finance. The tutor will explain from first principles if the competency is set to Grad Student level, or provide intuition-first explanations at lower levels. The deep-dive capability means the student can drill into "how does the log-utility assumption affect the result?" mid-session. Shows the tutor is not just a calculator — it's a discussion partner. |

### What to Highlight During the Demo

- **Structured interview wizard:** Instead of typing messy LaTeX into a text box, the user selects equation type, order, and components through a form — the tutor assembles the mathematical representation.
- **Live LaTeX rendering:** Equations display as proper mathematical notation, not raw text.
- **Adaptive competency:** The tutor adjusts after each MC assessment — the demo can show it recognizing that a student is at Grad Student level and switching to rigorous derivations.
- **Deep-dive capability:** The student can interrupt with "explain that part more" and the tutor will do a first-principles deep dive on the spot.
- **Session persistence:** The full conversation history is saved — a student can continue a multi-session learning arc over days.

---

## Summary: Which Agent for Which Family Office Need?

| Family Office Activity | Best Agent(s) | Why |
|---|---|---|
| **Market monitoring / competitive intelligence** | News Pipeline | Automates the reading → synthesis → delivery chain. |
| **Investment memo / due diligence** | Deep Research | 5–15 minute research with cited sources. |
| **Stress-testing a thesis or decision** | Consigliere | Multi-frame, adversarial, uncertainty-aware. |
| **Surfacing blind spots in groupthink** | Debate Arena | Forces marginalized perspectives into the room. |
| **Board-ready documents / frameworks** | Strategic Planning | Governance Frameworks, SWOT, RCA — structured outputs with PDF export. |
| **Next-gen financial education** | Math Tutor | Adaptive, interactive, LaTeX-rendered. |
| **Quick drafting / communications** | Chat | Letters, comparisons, explanations — instant output. |
| **Philanthropic structuring** | Chat + Consigliere + Deep Research | Quick comparison, then stress-test the choice, then due-diligence the implementation. |
| **Regulatory monitoring** | News Pipeline | Scheduled RSS + AI theme extraction. |
| **Succession planning** | Consigliere + Strategic Planning | Stress-test the decision, then build the governance framework. |
| **Deal evaluation** | Deep Research + Consigliere | Due-diligence the sector, then stress-test the specific deal thesis. |

---

## Demo Flow Recommendation

For a 30-minute family office presentation:

1. **Opening (2 min):** Start with the Chat agent — familiar, low-barrier. Ask it to draft an investment letter. Everyone understands what they're seeing.

2. **The "Wow" Moment (8 min):** Launch a Deep Research query on a topic relevant to the audience (e.g., family office trends, a sector they invest in). Let the SSE stream run while you narrate. The live search → read → synthesize flow is visually compelling and unlike anything in a normal chat interface.

3. **The Adversarial Edge (8 min):** Run the Consigliere on a relatable decision (e.g., "Should we hire an external CIO?"). The audience will connect with the emotional dimensions. The rhetoric analysis and disagreement surface are the "we didn't know AI could do this" moments.

4. **The Structured Deliverables (5 min):** Show the Strategic Planning agent producing a Governance Framework. Point out that this is exportable as a professionally typeset PDF. A board-ready document generated in 30 seconds.

5. **Ongoing Intelligence (5 min):** Show the News Pipeline — pre-configured interests, scheduled runs, email delivery. This is the "when you leave the room, it keeps working" agent.

6. **Closing (2 min):** Mention the Debate Arena and Math Tutor as specialist tools. Emphasize: all data stays on-premise, BYOK, zero telemetry, open-source (MIT).

---

## Technical Notes for the Demo

- **Brave Search API key required** for Deep Research — set as `BRAVE_SEARCH_API_KEY` in `.env` or per-user in Settings.
- **OpenRouter key required** for all agents — paste in Settings before the demo.
- **News Pipeline extras:** Install with `pip install -e ".[news]"` (requires `feedparser`, `trafilatura`, `aiosmtplib`, `apscheduler`).
- **SMTP configuration** for News Pipeline email delivery — pre-configure an interest with email settings for a smooth demo.
- **Pre-warm the LaTeX cache** if demonstrating PDF export — run `tectonic -X compile` on a sample `.tex` file once to fetch packages from CTAN.
- **SSE streaming** requires the frontend to be served from the same origin (no CORS issues in self-hosted deployment).
- **Rate limiting:** Default 60 req/min for agents. Configure in `config/default.toml` if running multiple agents simultaneously during the demo.
- **All agent outputs** are persisted as `AgentSession` records — visit the History tab after the demo to show the full audit trail of everything that was generated.
