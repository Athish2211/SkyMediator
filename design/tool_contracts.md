# SkyMediator — Tool Contracts and Execution Specifications

**Document Version:** 1.0.0  
**Status:** Under Architectural Review  
**Date:** 26 October 2026  
**Project:** Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), BMSCE  
**Authors:** Athish Raj, Dinesh K, Sanchit Rajesh  
**Instructor:** Dr. Kalyan Nagaraj  

---

## 1. Overview and Determinism Principle

All calculations in SkyMediator are strictly decoupled from the Large Language Model. LLMs are prohibited from executing arithmetic (flight hours, duty rest subtraction, slot counts, cost aggregations, or composite scores). 

Instead, deterministic Python tools execute all calculations. There are **14 deterministic tools** and **2 learned/retrieval tools**.

---

## 2. Deterministic Calculation and Query Tools

### 2.1 `query_schedule`
- **File:** `tools/schedule.py`
- **Purpose:** Queries the current flight schedule by flight IDs or time/airport window.
- **Signature:**
  ```python
  def query_schedule(
      flight_ids: Optional[List[str]] = None,
      airport: Optional[str] = None,
      window_start: Optional[datetime] = None,
      window_end: Optional[datetime] = None,
      db_path: str = "data/processed/skymediator.db"
  ) -> List[Dict[str, Any]]:
  ```
- **Returns:** List of matching flight rows with fields `[flight_id, tail, origin, dest, std, sta, status, seats]`.
- **Determinism:** 100% deterministic SQLite query.

---

### 2.2 `apply_plan_diff` (Core Architectural Mutation Tool)
- **File:** `tools/schedule.py`
- **Purpose:** Applies a list of atomic `PlanDiffOp` mutations (`swap_tail`, `delay`, `cancel`, `reposition_crew`) to a base flight schedule, producing a simulated mutated schedule for downstream validation without altering SQLite.
- **Signature:**
  ```python
  def apply_plan_diff(
      base_schedule: List[Dict[str, Any]],
      plan_diff: List[Dict[str, Any]]
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "mutated_flights": List[Dict[str, Any]],
      "applied_ops_count": int,
      "unresolved_conflicts": List[str]
  }
  ```
- **Determinism:** 100% deterministic pure function.

---

### 2.3 `swap_tail`
- **File:** `tools/schedule.py`
- **Purpose:** Validates whether swapping an aircraft onto a specific flight satisfies physical continuity, equipment type compatibility, and minimum turnaround time (`min_turn_min`).
- **Signature:**
  ```python
  def swap_tail(
      flight_id: str,
      new_tail: str,
      schedule: List[Dict[str, Any]],
      db_path: str = "data/processed/skymediator.db"
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "is_valid": bool,
      "turnaround_margin_minutes": int,
      "reasons": List[str]
  }
  ```

---

### 2.4 `check_range_maint`
- **File:** `tools/schedule.py`
- **Purpose:** Verifies that a tail assigned to a flight has sufficient flight hours remaining before mandatory A-Check maintenance and will end its rotation at a certified maintenance base.
- **Signature:**
  ```python
  def check_range_maint(
      tail: str,
      flight_id: str,
      db_path: str = "data/processed/skymediator.db"
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "is_valid": bool,
      "hours_to_maintenance": float,
      "terminates_at_maintenance_base": bool,
      "reasons": List[str]
  }
  ```

---

### 2.5 `calc_duty_time` (FDTL Calculation Engine)
- **File:** `tools/duty.py`
- **Purpose:** Evaluates crew rosters against DGCA CAR Section 7, Series J, Part III. Calculates cumulative duty minutes, Flight Duty Period (FDP), Window of Circadian Low (WOCL) night operations (02:00–06:00), and rest requirements.
- **Signature:**
  ```python
  def calc_duty_time(
      crew_id: str,
      mutated_schedule: List[Dict[str, Any]],
      base_crew_duties: List[Dict[str, Any]],
      fdtl_version: Literal["2019", "2024"] = "2019"
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "crew_id": str,
      "is_legal": bool,
      "total_fdp_minutes": int,
      "max_allowed_fdp_minutes": int,
      "total_block_hours": float,
      "wocl_overlap_minutes": int,
      "rest_provided_minutes": int,
      "rest_required_minutes": int,
      "violations": List[Dict[str, Any]]  # [{"type": "FDP_EXCEEDED", "actual": 810, "limit": 750}]
  }
  ```
- **Determinism:** 100% deterministic arithmetic implementation of statutory limits.

---

### 2.6 `check_slot`
- **File:** `tools/slots.py`
- **Purpose:** Checks whether arrivals and departures in a mutated schedule exceed airport movement capacities (e.g., fog restricted rate of 12 movements/30 min) or land during airport curfew hours.
- **Signature:**
  ```python
  def check_slot(
      airport: str,
      mutated_schedule: List[Dict[str, Any]],
      db_path: str = "data/processed/skymediator.db"
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "is_valid": bool,
      "violated_windows": List[Dict[str, Any]],  # [{"window": "06:00-06:30", "capacity": 12, "actual": 15}]
      "curfew_breaches": List[Dict[str, Any]]
  }
  ```

---

### 2.7 `get_affected_bookings`
- **File:** `tools/passengers.py`
- **Purpose:** Retrieves all passenger booking records associated with a set of delayed or cancelled flight IDs.
- **Signature:**
  ```python
  def get_affected_bookings(
      flight_ids: List[str],
      db_path: str = "data/processed/skymediator.db"
  ) -> List[Dict[str, Any]]:
  ```

---

### 2.8 `calc_missed_connections`
- **File:** `tools/passengers.py`
- **Purpose:** Identifies itinerary connections where the revised arrival time of an inbound flight leaves less than `min_connect_min` before the scheduled departure of the outbound flight.
- **Signature:**
  ```python
  def calc_missed_connections(
      mutated_schedule: List[Dict[str, Any]],
      db_path: str = "data/processed/skymediator.db"
  ) -> Dict[str, Any]:
  ```
- **Returns:**
  ```python
  {
      "total_missed_connections": int,
      "broken_connection_records": List[Dict[str, Any]]
  }
  ```

---

### 2.9 `get_rebooking_options`
- **File:** `tools/passengers.py`
- **Purpose:** Queries alternative flights departing within 12 hours from the same origin to destination with available seat capacity (`seats_available > 0`).
- **Signature:**
  ```python
  def get_rebooking_options(
      booking_id: str,
      mutated_schedule: List[Dict[str, Any]],
      db_path: str = "data/processed/skymediator.db"
  ) -> List[Dict[str, Any]]:
  ```

---

### 2.10 `estimate_cost`
- **File:** `tools/cost.py`
- **Purpose:** Calculates the exact operational and regulatory cost of a mutated schedule using rates defined in `cost_rates`.
- **Signature:**
  ```python
  def estimate_cost(
      mutated_schedule: List[Dict[str, Any]],
      missed_connections_count: int,
      affected_bookings: List[Dict[str, Any]],
      db_path: str = "data/processed/skymediator.db"
  ) -> Dict[str, Any]:
  ```
- **Formulas:**
  1. $\text{Delay Cost} = \sum_{\text{flights}} \max(0, \text{DelayMinutes}) \times \text{Rate}_{\text{delay\_per\_min}}$
  2. $\text{Cancellation Cost} = \sum_{\text{cancelled}} \text{Rate}_{\text{cancel\_base}}$
  3. $\text{Meal Care (DGCA)} = \sum_{\text{pax with delay} \ge 120\text{m}} \text{Rate}_{\text{meal\_voucher}}$
  4. $\text{Hotel Care (DGCA)} = \sum_{\text{pax with overnight delay}} \text{Rate}_{\text{hotel\_night}}$
  5. $\text{Statutory Compensation} = \sum_{\text{unnotified cancel}} \text{Rate}_{\text{dgca\_comp}}$
- **Returns:** Itemized dictionary and `total_cost`.

---

### 2.11 `score_plan` (Resolving GAP-06)
- **File:** `tools/scoring.py`
- **Purpose:** Evaluates normalized multi-objective penalty score for surviving candidate plans:
  $$\text{Score} = w_1 \left(\frac{\text{DelayMinutes}}{600}\right) + w_2 \left(\frac{\text{MissedPax}}{200}\right) + w_3 \left(\frac{\text{Cost}}{1,000,000}\right) + w_4 \left(\frac{\text{CrewBufferPenalty}}{100}\right)$$
- **Signature:**
  ```python
  def score_plan(
      delay_minutes: int,
      missed_connections: int,
      total_cost: float,
      crew_buffer_penalty: float,
      weights: Optional[Dict[str, float]] = None
  ) -> Dict[str, Any]:
  ```
- **Returns:** `{"composite_score": float, "normalized_components": Dict[str, float]}` (Lower score indicates superior plan).

---

### 2.12 `get_forecast` & `aog_risk`
- **File:** `tools/schedule.py`
- **Purpose:** Retrieves formatted weather features from `weather_obs` and aircraft technical logs for the Sentinel agent.

---

### 2.13 `validate_plan_independent` (Evaluation-Only)
- **File:** `eval/validator_fdtl.py`
- **Purpose:** A clean-room, independent regulatory validator coded directly from DGCA CAR. Evaluates final plans during benchmarks and test harnesses.
- **STRICT ARCHITECTURAL ISOLATION:** Agents are prohibited from calling this tool at runtime to prevent circular validation (Resolving GAP-03).

---

## 3. Learned and Retrieval Tools

### 3.1 `retrieve_fdtl` (Agentic RAG)
- **File:** `agents/crew.py` / `ingest/build_rules_index.py`
- **Purpose:** Vector similarity search over chunked DGCA CAR Section 7, Series J, Part III text using ChromaDB or FAISS.
- **Signature:**
  ```python
  def retrieve_fdtl(
      query: str,
      k: int = 3,
      similarity_threshold: float = 0.65,
      index_path: str = "data/processed/fdtl_index"
  ) -> List[Dict[str, Any]]:
  ```
- **Returns:**
  ```python
  [
      {
          "clause_id": "CAR-7-J-III-Para-6.2",
          "heading": "Maximum Flight Duty Period (FDP)",
          "content": "For two pilot operation with up to two landings...",
          "score": 0.82
      }
  ]
  ```

---

### 3.2 `fog_risk_model`
- **File:** `agents/sentinel.py`
- **Purpose:** Scikit-learn classification pipeline (RandomForest or LogisticRegression) predicting probability of fog event ($RVR < 550\text{m}$) within the next 6 hours.
- **Features:** Temperature, Dew point depression, Wind speed, Relative humidity, Hour of day, Visibility trend.
- **Output:** `{"probability": float, "confidence": float, "predicted_label": int}`.
