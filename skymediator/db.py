"""
Database manager and SQLite DDL initialization for SkyMediator.
Enforces normalized schemas, foreign keys, and indices (resolving GAP-05 & PROP-03).
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union

from skymediator.config import settings

DDL_STATEMENTS = """
PRAGMA foreign_keys = ON;

-- 1. Aircraft Table
CREATE TABLE IF NOT EXISTS aircraft (
    tail VARCHAR(16) PRIMARY KEY,
    aircraft_type VARCHAR(16) NOT NULL DEFAULT 'A320',
    seats INTEGER NOT NULL CHECK (seats > 0),
    min_turn_min INTEGER NOT NULL DEFAULT 35,
    current_airport VARCHAR(4) NOT NULL DEFAULT 'VOBL',
    maintenance_due_hours REAL NOT NULL DEFAULT 100.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Flights Table
CREATE TABLE IF NOT EXISTS flights (
    flight_id VARCHAR(16) PRIMARY KEY,
    tail VARCHAR(16) NOT NULL,
    origin VARCHAR(4) NOT NULL,
    dest VARCHAR(4) NOT NULL,
    std TIMESTAMP NOT NULL,
    sta TIMESTAMP NOT NULL,
    etd TIMESTAMP,
    eta TIMESTAMP,
    seats INTEGER NOT NULL CHECK (seats > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED' 
        CHECK (status IN ('SCHEDULED', 'BOARDING', 'AIRBORNE', 'DELAYED', 'CANCELLED', 'DIVERTED', 'COMPLETED')),
    FOREIGN KEY (tail) REFERENCES aircraft(tail) ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_flights_std ON flights(std);
CREATE INDEX IF NOT EXISTS idx_flights_tail ON flights(tail);
CREATE INDEX IF NOT EXISTS idx_flights_origin_dest ON flights(origin, dest);

-- 3. Weather Observations Table
CREATE TABLE IF NOT EXISTS weather_obs (
    obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    station VARCHAR(4) NOT NULL,
    ts TIMESTAMP NOT NULL,
    visibility_m INTEGER NOT NULL,
    rvr_m INTEGER,
    wind_speed_kts INTEGER NOT NULL,
    wind_dir_deg INTEGER NOT NULL,
    temp_c REAL NOT NULL,
    dewpoint_c REAL NOT NULL,
    cloud_ceiling_ft INTEGER,
    metar_raw TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weather_station_ts ON weather_obs(station, ts);

-- 4. Crew Members Table
CREATE TABLE IF NOT EXISTS crew_members (
    crew_id VARCHAR(16) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('CAPTAIN', 'FIRST_OFFICER', 'CABIN_LEAD', 'CABIN_CREW')),
    base VARCHAR(4) NOT NULL DEFAULT 'VOBL',
    current_airport VARCHAR(4) NOT NULL DEFAULT 'VOBL',
    cumulative_duty_7d_hours REAL NOT NULL DEFAULT 0.0
);

-- 5. Crew Duties Table (Duty Periods)
CREATE TABLE IF NOT EXISTS crew_duties (
    duty_id VARCHAR(32) PRIMARY KEY,
    crew_id VARCHAR(16) NOT NULL,
    duty_start TIMESTAMP NOT NULL,
    duty_end TIMESTAMP,
    rest_period_before_min INTEGER NOT NULL DEFAULT 720,
    max_fdp_minutes INTEGER NOT NULL DEFAULT 750,
    is_split_duty BOOLEAN DEFAULT 0,
    is_augmented BOOLEAN DEFAULT 0,
    FOREIGN KEY (crew_id) REFERENCES crew_members(crew_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_crew_duties_crew_start ON crew_duties(crew_id, duty_start);

-- 6. Crew Duty Flights (Normalized Junction Table)
CREATE TABLE IF NOT EXISTS crew_duty_flights (
    duty_id VARCHAR(32) NOT NULL,
    flight_id VARCHAR(16) NOT NULL,
    leg_sequence INTEGER NOT NULL,
    is_deadhead BOOLEAN DEFAULT 0,
    PRIMARY KEY (duty_id, flight_id),
    FOREIGN KEY (duty_id) REFERENCES crew_duties(duty_id) ON DELETE CASCADE,
    FOREIGN KEY (flight_id) REFERENCES flights(flight_id) ON UPDATE CASCADE
);

-- 7. Passenger Bookings Table
CREATE TABLE IF NOT EXISTS bookings (
    booking_id VARCHAR(32) PRIMARY KEY,
    pax_count INTEGER NOT NULL CHECK (pax_count > 0),
    fare_class VARCHAR(16) NOT NULL CHECK (fare_class IN ('ECONOMY', 'PREMIUM_ECON', 'BUSINESS')),
    avg_fare_paid REAL NOT NULL CHECK (avg_fare_paid >= 0),
    contact_email VARCHAR(64)
);

-- 8. Itinerary Legs Table
CREATE TABLE IF NOT EXISTS itinerary_legs (
    booking_id VARCHAR(32) NOT NULL,
    leg_no INTEGER NOT NULL,
    flight_id VARCHAR(16) NOT NULL,
    seat_assigned VARCHAR(8),
    PRIMARY KEY (booking_id, leg_no),
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (flight_id) REFERENCES flights(flight_id) ON UPDATE CASCADE
);

-- 9. Passenger Flight Connections Table
CREATE TABLE IF NOT EXISTS connections (
    connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id VARCHAR(32) NOT NULL,
    inbound_flight VARCHAR(16) NOT NULL,
    outbound_flight VARCHAR(16) NOT NULL,
    connection_airport VARCHAR(4) NOT NULL DEFAULT 'VOBL',
    min_connect_min INTEGER NOT NULL DEFAULT 45,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    FOREIGN KEY (inbound_flight) REFERENCES flights(flight_id) ON UPDATE CASCADE,
    FOREIGN KEY (outbound_flight) REFERENCES flights(flight_id) ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_connections_flights ON connections(inbound_flight, outbound_flight);

-- 10. Airport Slots and Curfew Table
CREATE TABLE IF NOT EXISTS slots (
    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport VARCHAR(4) NOT NULL,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    curfew_start TIME,
    curfew_end TIME
);
CREATE INDEX IF NOT EXISTS idx_slots_airport_window ON slots(airport, window_start, window_end);

-- 11. Cost Rates Table
CREATE TABLE IF NOT EXISTS cost_rates (
    rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item VARCHAR(64) UNIQUE NOT NULL,
    rate REAL NOT NULL,
    currency VARCHAR(4) NOT NULL DEFAULT 'INR',
    description TEXT
);

-- 12. Scenarios Table
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    disruption_type VARCHAR(16) NOT NULL,
    airport VARCHAR(4) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    severity VARCHAR(16) NOT NULL,
    difficulty VARCHAR(16) NOT NULL,
    seeded_anomalies TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. Weather Observations Table
CREATE TABLE IF NOT EXISTS weather_observations (
    obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
    station VARCHAR(4) NOT NULL,
    observation_time TIMESTAMP NOT NULL,
    visibility_m INTEGER NOT NULL,
    rvr_m INTEGER,
    temperature_c REAL NOT NULL,
    dewpoint_c REAL NOT NULL,
    wind_speed_kts REAL NOT NULL,
    wind_dir_deg INTEGER NOT NULL,
    cloud_ceiling_ft INTEGER,
    metar_raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_weather_station_time ON weather_observations(station, observation_time);

-- 14. Agent Events Table (Live operations stream & replay)
CREATE TABLE IF NOT EXISTS agent_events (
    event_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(32) NOT NULL,
    disruption_id VARCHAR(32),
    plan_id VARCHAR(32),
    plan_revision INTEGER DEFAULT 1,
    round_number INTEGER DEFAULT 1,
    event_type VARCHAR(64) NOT NULL,
    actor VARCHAR(32) NOT NULL,
    recipient VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'INFO',
    summary TEXT NOT NULL,
    structured_payload TEXT,
    correlation_id VARCHAR(64),
    timestamp_utc TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_agent_events_actor ON agent_events(actor);
CREATE INDEX IF NOT EXISTS idx_agent_events_type ON agent_events(event_type);

-- 15. Plan Revisions Table (Version history across deliberation rounds)
CREATE TABLE IF NOT EXISTS plan_revisions (
    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(32) NOT NULL,
    plan_id VARCHAR(32) NOT NULL,
    round_number INTEGER NOT NULL,
    proposing_agent VARCHAR(32) NOT NULL,
    operational_rationale TEXT,
    plan_diff_json TEXT NOT NULL,
    is_feasible BOOLEAN NOT NULL DEFAULT 1,
    vetoed_by_json TEXT,
    veto_reasons_json TEXT,
    scores_json TEXT,
    compliance_notes_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_plan_revisions_run ON plan_revisions(run_id, round_number);
CREATE INDEX IF NOT EXISTS idx_plan_revisions_plan ON plan_revisions(plan_id);

-- 16. Decision Records Table (Persistent Duty Manager audit trail)
CREATE TABLE IF NOT EXISTS decision_records (
    decision_id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(32) NOT NULL,
    disruption_id VARCHAR(32),
    plan_id VARCHAR(32),
    round_number INTEGER NOT NULL DEFAULT 1,
    duty_manager_action VARCHAR(32) NOT NULL CHECK (duty_manager_action IN ('PENDING', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED')),
    duty_manager_id VARCHAR(64) NOT NULL DEFAULT 'Athish Raj (Duty Manager)',
    duty_manager_notes TEXT,
    decision_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    proposed_diff_json TEXT,
    validation_outcomes_json TEXT,
    vetoed_by_json TEXT,
    is_feasible_at_decision BOOLEAN NOT NULL DEFAULT 1,
    mediator_rationale TEXT,
    final_status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED'
);
CREATE INDEX IF NOT EXISTS idx_decision_records_run ON decision_records(run_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_action ON decision_records(duty_manager_action);
CREATE INDEX IF NOT EXISTS idx_decision_records_timestamp ON decision_records(decision_timestamp);
"""


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with foreign keys enabled and Row factory."""
    path = Path(db_path) if db_path else settings.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initializes the database schema."""
    conn = get_connection(db_path)
    try:
        conn.executescript(DDL_STATEMENTS)
        conn.commit()
    finally:
        conn.close()


def reset_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Drops and re-creates all database tables."""
    path = Path(db_path) if db_path else settings.DB_PATH
    if path.exists():
        path.unlink()
    init_db(path)
