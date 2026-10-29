# SkyMediator — Data Feasibility Note (Step 0)

**Document Version:** 1.0.0  
**Date:** 26 October 2026  
**Primary Hub Airport:** Kempegowda International Airport, Bengaluru (**VOBL / BLR**)  
**Secondary Spoke Airports:** Delhi (VIDP / DEL), Mumbai (VABB / BOM), Chennai (VOMM / MAA), Hyderabad (VOHY / HYD), Goa (VOGO / GOI), Kolkata (VECC / CCU)  
**Author:** Athish Raj (Team Lead & Data/Tools Lead)  

---

## 1. Executive Summary and Feasibility Determination

In accordance with Step 0 of the build specification, this document confirms the feasibility of using **Kempegowda International Airport, Bengaluru (ICAO: VOBL, IATA: BLR)** as the primary hub for SkyMediator disruption modeling.

### Feasibility Status: **CONFIRMED (USABLE & REPRODUCIBLE)**

---

## 2. Data Sources and Accessibility Analysis

### 2.1 Weather Observations (METAR / SPECI)
- **Primary Source:** Iowa Environmental Mesonet (IEM) ASOS/METAR Archive (`https://mesonet.agron.iastate.edu/request/download.phtml`).
- **Station Identifier:** `VOBL` (Kempegowda International Airport, Bengaluru, India).
- **Available Variables:** Observation timestamp (`ts`), visibility (`vsby`), Runway Visual Range (`rvr`), wind speed (`sknt`), wind direction (`drct`), ambient temperature (`tmpc`), dew point temperature (`dwpc`), cloud ceiling (`feel`/`skyc`), raw METAR text (`metar`).
- **Phenomena Modeled:** Bengaluru experiences morning radiation fog and low visibility conditions during winter months (November through February), particularly between 05:00 IST and 08:30 IST.
- **Offline Fallback Guarantee:** An offline verified archive of winter METAR observations is packaged directly into `data/raw/weather_vobl.csv` to ensure 100% offline reproducibility and eliminate external network flakiness during evaluation runs.

### 2.2 Flight Schedules and Movement Rotations
- **Airline Profile:** Modeled on standard domestic Airbus A320 commercial operations (180 seats, 35-minute minimum turnaround buffer).
- **Spoke Network:** 6 major domestic hubs and high-frequency spokes:
  - BLR $\leftrightarrow$ DEL (VIDP): 150 minutes block time
  - BLR $\leftrightarrow$ BOM (VABB): 100 minutes block time
  - BLR $\leftrightarrow$ MAA (VOMM): 50 minutes block time
  - BLR $\leftrightarrow$ HYD (VOHY): 70 minutes block time
  - BLR $\leftrightarrow$ GOI (VOGO): 60 minutes block time
  - BLR $\leftrightarrow$ CCU (VECC): 150 minutes block time
- **Flight Volume:** 60 scheduled flights across a 24-hour tactical horizon for 15 dedicated narrow-body aircraft (`VT-BLR01` through `VT-BLR15`).
- **Tail Rotation Feasibility:** Rotations are constructed with strict turnaround checks (`turnaround_margin >= min_turn_min`) and physical airport continuity.

### 2.3 Regulatory Standard Ingestion
- **Crew Flight Duty:** DGCA CAR Section 7, Series J, Part III (Flight and Duty Time Limitations and Rest Requirements).
  - Primary baseline: 2019 baseline regulation (active in Indian OCCs).
  - Experimental toggle: 2024 revised norms (48h weekly rest, night duty limits).
- **Passenger Care:** DGCA CAR Section 3, Series M, Part IV (Facilities to be provided to passengers by airlines due to denied boarding, cancellation of flights and delays in flights).

### 2.4 Synthetic Data Anchoring
Crew rosters and passenger bookings are not public commercial data for any airline. Therefore, synthetic records are deterministically anchored to real scheduled flight IDs:
- **Crew Pairings:** 24 crew members (Captains and First Officers) mapped to multi-sector duties with explicit duty start, rest before duty, and legal FDP limits.
- **Passenger Bookings:** 60 bookings representing 180+ passengers, including single-leg journeys and multi-leg connections through BLR.
- **Fixed Random Seed:** Generation uses `seed=42`, guaranteeing bit-identical SQLite database rebuilds on any machine.
