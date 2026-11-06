# SkyMediator — Metric Definitions, Mathematical Formulations, and Evaluation Rubric

This document provides formal mathematical definitions, units, provenance, and interpretation guidelines for all evaluation metrics used in benchmarking the SkyMediator multi-agent disruption recovery system against classical Operations Research and heuristics.

---

## 1. Sentinel Prediction Metrics

These metrics quantify Sentinel's capability to forecast weather-induced airport disruptions (such as Kempegowda Hub winter radiation fog) prior to operational onset.

### 1.1 Brier Score
- **Formula:** 
  $$\text{BS} = \frac{1}{N} \sum_{i=1}^{N} (p_i - y_i)^2$$
  where $p_i \in [0, 1]$ is the predicted probability of disruption at observation $i$, and $y_i \in \{0, 1\}$ is the binary ground-truth event indicator ($1$ if visibility $< 600\text{m}$ or $\text{RVR} < 550\text{m}$, $0$ otherwise).
- **Units:** Dimensionless $[0, 1]$.
- **Data Source:** Half-hourly METAR archive for Kempegowda International Airport (`VOBL_METAR_winter_history.csv`, 5,736 observations).
- **Interpretation:** Strictly proper scoring rule assessing probability calibration and sharpness. Lower is better ($0.0$ is perfect calibration).
- **Known Limitations:** Sensitive to background base rates in highly imbalanced rare-event datasets.

### 1.2 Precision, Recall, and $F_1$-Score
- **Formulas:**
  $$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}, \quad \text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}, \quad F_1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$
- **Units:** Dimensionless $[0, 1]$ or percentage ($0\% - 100\%$).
- **Data Source:** Classification predictions evaluated on the held-out test split of the VOBL METAR archive.
- **Interpretation:** Higher is better. Precision measures false alarm avoidance; recall measures missed disruption detection.

### 1.3 Area Under the ROC Curve (ROC-AUC) and PR-AUC
- **Formulas:**
  $$\text{ROC-AUC} = \int_{0}^{1} \text{TPR}(\text{FPR}^{-1}(t)) \, dt, \quad \text{PR-AUC} = \int_{0}^{1} P(R) \, dR$$
- **Units:** Dimensionless $[0, 1]$.
- **Interpretation:** Threshold-independent ranking capability. Higher is better. PR-AUC is especially informative for imbalanced fog distributions.

---

## 2. Operational Recovery Metrics

These metrics measure the operational and economic quality of recovery plans produced by SkyMediator and comparison baselines.

### 2.1 Total Recovery Cost ($\text{Cost}_{\text{tot}}$)
- **Formula:**
  $$\text{Cost}_{\text{tot}} = \sum_{f \in \mathcal{F}} \left( C_{\text{delay}}(d_f) + C_{\text{cancel}}(f) + C_{\text{swap}}(f) \right) + \sum_{p \in \mathcal{P}} \left( C_{\text{care}}(p) + C_{\text{missed}}(p) \right)$$
  where:
  - $C_{\text{delay}}(d_f) = d_f \times \text{INR } 600/\text{min}$ (operational and fuel burn holding cost).
  - $C_{\text{cancel}}(f) = \text{INR } 250,000$ (fixed statutory cancellation liability).
  - $C_{\text{swap}}(f) = \text{INR } 15,000$ (ground towing and gate repositioning cost).
  - $C_{\text{care}}(p) = \text{INR } 1,200$ (meals/refreshments for delays $\ge 120\text{m}$) or $\text{INR } 6,000$ (overnight hotel accommodation under DGCA CAR Section 3, Series M, Part IV).
  - $C_{\text{missed}}(p) = \text{INR } 10,000$ (interline rebooking compensation).
- **Units:** Indian National Rupees ($\text{INR}$).
- **Interpretation:** Lower is better. Represents total financial exposure incurred by the airline.

### 2.2 Total Operational Delay ($D_{\text{tot}}$)
- **Formula:**
  $$D_{\text{tot}} = \sum_{f \in \mathcal{F}_{\text{active}}} \max\left(0, \text{STA}_{\text{mutated}}(f) - \text{STA}_{\text{base}}(f)\right)$$
- **Units:** Minutes ($\text{mins}$).
- **Interpretation:** Lower is better. Directly impacts aircraft turnaround and customer satisfaction.

### 2.3 Normalized Composite Penalty Score ($S_{\text{comp}}$)
- **Formula:**
  $$S_{\text{comp}} = w_1 \cdot \frac{D_{\text{tot}}}{D_{\max}} + w_2 \cdot \frac{\text{Cost}_{\text{tot}}}{\text{Cost}_{\max}} + w_3 \cdot \frac{\text{Pax}_{\text{disrupted}}}{\text{Pax}_{\max}}$$
  Default weights: $w_1 = 0.35$ (delay), $w_2 = 0.40$ (cost), $w_3 = 0.25$ (passenger impact). Normalized using scenario horizon bounds.
- **Units:** Dimensionless $[0, 1]$.
- **Interpretation:** Lower is better ($0.0$ indicates zero disruption impact). Enables multi-objective ranking.

### 2.4 Passenger Connection Impact ($\text{Pax}_{\text{disrupted}}$)
- **Formula:**
  $$\text{Pax}_{\text{disrupted}} = \sum_{p \in \mathcal{P}} \mathbb{I}\left( \text{status}(p) = \text{CANCELLED} \lor \text{buffer}(p) < \text{MCT} \right)$$
  where $\text{MCT}$ is the Minimum Connection Time ($45\text{ mins}$ at VOBL).
- **Units:** Integer passenger count.
- **Interpretation:** Lower is better.

---

## 3. Regulatory Constraint Compliance Metrics

Safety and legality are mandatory hard constraints in SkyMediator.

### 3.1 Independent FDTL Violation Rate
- **Formula:**
  $$\text{VR}_{\text{FDTL}} = \frac{N_{\text{illegal\_crew\_assignments}}}{N_{\text{total\_crew\_assignments}}} \times 100\%$$
- **Units:** Percentage ($\%$).
- **Data Source:** Evaluated strictly by the independent clean-room verification harness `skymediator/eval/validator_fdtl.py`.
- **Target:** **Strictly $0.00\%$**. Any plan with $\text{VR}_{\text{FDTL}} > 0$ is classified as a critical system failure.

### 3.2 Airport Slot Overflow Rate
- **Formula:**
  $$\text{VR}_{\text{slot}} = \frac{N_{\text{movements\_exceeding\_slot\_capacity}}}{N_{\text{total\_movements}}} \times 100\%$$
- **Units:** Percentage ($\%$).
- **Target:** **Strictly $0.00\%$**. Enforced by Slot Agent hard veto.

### 3.3 Plan Feasibility Rate
- **Formula:**
  $$\text{FR} = \frac{N_{\text{feasible\_plans}}}{N_{\text{total\_evaluated\_scenarios}}} \times 100\%$$
  where a plan is feasible iff $\text{VR}_{\text{FDTL}} == 0$, $\text{VR}_{\text{slot}} == 0$, and turnaround margins $\ge 35\text{ mins}$.
- **Units:** Percentage ($\%$).
- **Target:** $100.0\%$ for recoverable operational scenarios.

### 3.4 Safe Abstention and Escalation Rate
- **Formula:**
  $$\text{AR} = \frac{N_{\text{correct\_escalations}}}{N_{\text{adversarial\_unsolvable\_scenarios}}} \times 100\%$$
- **Units:** Percentage ($\%$).
- **Interpretation:** Measures system robustness against hallucinating solutions when regulatory data is ambiguous or contradictory.

---

## 4. Agentic and Observability Metrics

These metrics capture deliberation overhead, negotiation dynamics, and computational cost.

| Metric Name | Mathematical Definition | Units | Target / Bound |
| :--- | :--- | :--- | :--- |
| **Negotiation Rounds** | Number of counter-proposal iterations before consensus | Integer | $\le 3$ rounds (hard cap) |
| **End-to-End Latency** | Wall-clock execution time per scenario | Seconds ($\text{s}$) | $< 15.0\text{s}$ |
| **Token Consumption** | Total LLM prompt + completion tokens | Tokens | Distribution logged |
| **Tool Call Accuracy** | Deterministic tool calls without schema error | Percentage ($\%$) | $100.0\%$ |
| **Clause Retrieval Precision** | Relevant DGCA CAR clause ranked in top-2 | Percentage ($\%$) | $\ge 90.0\%$ |

