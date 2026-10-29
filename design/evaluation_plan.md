# SkyMediator — Evaluation Plan, Benchmarks, and Statistical Methodology

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Evaluation Philosophy and Scientific Framing

### 1.1 The Research Claim
An Operations Research solver (such as Google OR-Tools using Mixed Integer Linear Programming or CP-SAT) will almost certainly outperform a multi-agent LLM system on raw mathematical cost minimization over a rigid, closed mathematical problem. 

Therefore, SkyMediator does not make the unscientific claim that LLMs are superior pure optimizers. Instead, the honest, publishable academic claims are:
1. **Explainable Regulatory Adjudication:** Multi-agent deliberation provides transparent, clause-cited legal and operational reasoning that duty managers can audit and trust.
2. **Robustness to Operational Ambiguity:** When confronted with messy, incomplete data or conflicting regulatory rules, the multi-agent system gracefully reflects and abstains rather than producing brittle or hallucinated plans.
3. **Near-Optimal Operational Performance:** SkyMediator achieves near-parity ($\ge 85\%$) with solver-generated costs while adhering to 100% regulatory compliance ($0.00\%$ FDTL violations).

---

## 2. Benchmark Datasets and Test Suites

### 2.1 Test Suite Composition (25+ Scenarios)
The evaluation harness executes against a curated suite of at least 25 reproducible scenarios:
- **10 Mild Fog Scenarios (Standard):** Fog reducing runway capacity by 30% for 3 hours; minor delays, manageable swaps.
- **10 Severe Fog Scenarios (Stress):** Low Visibility Procedures (LVP CAT III) lasting 6–8 hours; severe cascading delays, crew timing out, curfew conflicts.
- **5 Adversarial / Edge Case Scenarios (Robustness):**
  1. *Missing Connection Time:* An itinerary connection record with null `min_connect_min`.
  2. *Seat Saturation:* All potential rebooking flights at 100% load factor.
  3. *Ambiguous FDTL Clause:* Flight arriving at edge of WOCL (Window of Circadian Low) with split-duty extension.
  4. *Total Slot Gridlock:* Disruption window with zero available landing slots.
  5. *Uncrewed Base:* Outstation flight where no local reserve crew exists.

### 2.2 External Benchmarks and Historical Replay
1. **ROADEF 2009 Challenge (Amadeus):**
   - Industry benchmark dataset for airline disruption management.
   - Evaluates aircraft rotation recovery, passenger itinerary disruptions, and cancellation penalties.
   - SkyMediator implements a data adapter (`eval/baselines/roadef_adapter.py`) to convert ROADEF problem instances into `plan_state` schemas.
2. **BTS / OpenSky Replay Days:**
   - Real disruption days replayed from historical BTS records to benchmark against actual historical airline actions.

---

## 3. Baselines for Comparison

Every scenario is evaluated across three distinct operational engines:
1. **Greedy Heuristic Baseline (`eval/baselines/greedy_recovery.py`):**
   - Sequential, rule-based recovery: swaps to the first available idle tail; delays flights sequentially; cancels flights exceeding a hard 4-hour delay threshold.
2. **Operations Research Solver (`eval/baselines/or_tools_solver.py`):**
   - Mixed Integer Programming (MIP) or Constraint Programming (CP-SAT) formulated in Google OR-Tools.
   - Minimizes total delay, cancellation, and passenger cost subject to linear aircraft continuity constraints. Represents the theoretical upper bound on cost efficiency.
3. **SkyMediator Multi-Agent System:**
   - The full LangGraph deliberative architecture with Sentinel, Rotation, Crew Legality, Slot, Passenger, Cost, and Mediator agents.

---

## 4. Evaluation Metrics Taxonomy

| Group | Metric | Mathematical Formulation | Evaluation Tool / Method |
| :--- | :--- | :--- | :--- |
| **Recovery Quality** | Total Operational Cost | $\text{Cost} = \sum C_{\text{delay}} + \sum C_{\text{cancel}} + \sum C_{\text{care}}$ | `tools/cost.py` |
| | Disrupted Passengers | $\sum \text{Pax}_{\text{cancelled}} + \sum \text{Pax}_{\text{missed\_conn}}$ | `tools/passengers.py` |
| | Average Flight Delay | $\frac{1}{N} \sum \max(0, \text{STA}_{\text{new}} - \text{STA}_{\text{orig}})$ | `tools/schedule.py` |
| | Cancellation Rate | $\frac{N_{\text{cancelled}}}{N_{\text{total}}} \times 100\%$ | Plan diff audit |
| **Regulatory Compliance** | FDTL Violation Rate | $\frac{N_{\text{illegal\_crew\_assignments}}}{N_{\text{total\_crew\_assignments}}}$ | Clean-room `eval/validator_fdtl.py` (**Target: 0.00%**) |
| | Slot Breach Rate | $\frac{N_{\text{slot\_overflow\_movements}}}{N_{\text{total\_movements}}}$ | `tools/slots.py` (**Target: 0.00%**) |
| **Prediction (Sentinel)** | Brier Score | $\frac{1}{M} \sum_{t=1}^M (p_t - y_t)^2$ | Time-split test on METAR archive |
| | Precision, Recall, F1 | $\text{Precision} = \frac{TP}{TP+FP}$, $\text{Recall} = \frac{TP}{TP+FN}$ | Fog detection threshold $RVR < 550\text{m}$ |
| | Lead Time | $T_{\text{disruption\_onset}} - T_{\text{alert}}$ | Early warning margin (hours) |
| **Abstention & Safety** | Risk-Coverage Curve | Accuracy plotted as a function of coverage (selective answering) | Tested on the 5 adversarial scenarios |
| | Hallucination Rate | Unverified claims / total claims | Audit of RAG citations vs CAR ground truth |
| **Agentic RAG Quality** | Clause Recall@3 | $\frac{\text{Queries with correct clause in top-3}}{50}$ | 50-item gold set in `eval/rag_gold.jsonl` |
| | Citation Precision | Correctly cited clause IDs / Total citations | Regex audit of agent message rationale |
| **System Efficiency** | Rounds to Consensus | Average deliberation rounds ($\le 3.0$) | JSONL trace spans |
| | Latency per Scenario | Wall-clock execution time (seconds) | Benchmark timer |
| | Token Consumption | Input + Output tokens per recovery run | Trace span metadata |
| **Human Alignment** | Duty Manager Accept Rate | $\frac{N_{\text{accepted}}}{N_{\text{presented}}}$ | Subjective rubric evaluation |
| | Inter-Rater Agreement | Cohen's $\kappa$ across 3 human evaluators | 10 sampled recovery explanations |

---

## 5. Experimental Ablations

To isolate the contribution of each architectural innovation, SkyMediator will run systematic ablation experiments across identical scenarios:
1. **Single-Agent vs. Multi-Agent:** Replace the multi-agent graph with a single monolithic prompt given all tools.
2. **Predictive vs. Reactive:** Compare recovery costs when the Sentinel triggers proactive adjustments 3 hours early vs. reactive recovery after fog onset.
3. **1 Round vs. 3 Rounds:** Measure the score and compliance improvement achieved by iterative counter-proposals vs. single-pass generation.
4. **Agentic RAG vs. Static Few-Shot / No-RAG:** Compare FDTL compliance and citation precision with dynamic retrieval vs. pre-injected static rule summaries.
5. **Mediator Reflection On vs. Off:** Evaluate whether Mediator self-reflection catches multi-agent trade-off anomalies.

---

## 6. Statistical Rigor and Reporting Protocol

Because LLMs exhibit non-zero stochasticity, all evaluations must adhere to rigorous statistical reporting standards:
1. **Repeated Runs:** Every scenario is executed $N = 10$ times across all conditions with logged random seeds.
2. **Confidence Intervals:** 95% Confidence Intervals are calculated using paired bootstrap resampling ($B = 10,000$).
3. **Significance Testing:** Paired Wilcoxon signed-rank tests are conducted between SkyMediator and the baseline models ($p < 0.05$ threshold).
4. **Effect Size:** Standardized effect sizes (Cohen's $d$ and Cliff's $\Delta$) are reported for all cost and delay reductions.
5. **Reporting Negative Results:** Any metric where the multi-agent system underperforms the greedy baseline or solver will be explicitly reported and analyzed in the final academic report.
