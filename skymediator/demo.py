"""
End-to-End Demonstration Script for SkyMediator Vertical Slice.
Executes and displays:
1. Scenario A: Successful recovery.
2. Scenario B: Hard Veto and successful Counter-Proposal recovery.
3. Scenario C: Absolute hard constraints triggering escalation.
"""

from datetime import datetime, timedelta
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from skymediator.config import settings
from skymediator.fixtures import seed_database
from skymediator.graph import build_recovery_graph

console = Console()


def run_vertical_slice_demo():
    console.print(Panel.fit(
        "[bold cyan]SkyMediator — Multi-Agent Disruption Recovery (Vertical Slice)[/bold cyan]\n"
        f"Primary Hub: [yellow]{settings.HUB_AIRPORT}[/yellow] ({settings.HUB_IATA} - Bengaluru)\n"
        f"Regulatory Standard: [green]DGCA CAR Sec 7 Series J Part III ({settings.FDTL_VERSION})[/green]\n"
        f"Team Lead: [bold white]Athish Raj[/bold white]",
        border_style="cyan"
    ))

    # Initialize Seeded Database
    seed_database(settings.DB_PATH)
    graph = build_recovery_graph()

    base_time = datetime(2026, 11, 1, 6, 0)

    # =========================================================================
    # DEMO 1: SUCCESSFUL MULTI-ROUND RECOVERY (Veto -> Counter-Proposal -> Approved)
    # =========================================================================
    console.print("\n[bold green]========================================================================[/bold green]")
    console.print("[bold green]=== DEMO 1: Fog Disruption with Crew Veto & Successful Counter-Proposal ===[/bold green]")
    console.print("[bold green]========================================================================[/bold green]")

    base_schedule = [
        {
            "flight_id": "6E-101",
            "tail": "VT-BLR01",
            "origin": "VOBL",
            "dest": "VIDP",
            "std": base_time.isoformat(),
            "sta": (base_time + timedelta(hours=2, minutes=30)).isoformat(),
            "seats": 180,
            "status": "SCHEDULED"
        }
    ]

    # Pilot started at 02:00 AM (WOCL encroachment -> max FDP is 660 mins / 11.0 hours)
    crew_roster_1 = [
        {
            "crew_id": "CREW-WOCL-01",
            "duty_record": {"duty_start": datetime(2026, 11, 1, 2, 0).isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    slot_windows_1 = [
        {
            "airport": "VOBL",
            "window_start": base_time.isoformat(),
            "window_end": (base_time + timedelta(hours=8)).isoformat(),
            "capacity": 20
        }
    ]

    state_success = {
        "run_id": "DEMO-SUCCESS-01",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "affected_flight_id": "6E-101",
            "initial_action": "excessive_delay",
            "delay_minutes": 320,  # 320m delay causes 725m FDP > 660m limit -> VETO!
            "counter_delay_minutes": 30  # Counter-proposal: 30m delay -> 435m FDP <= 660m -> PASS!
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster_1,
        "slot_windows": slot_windows_1
    }

    final_state_1 = graph.invoke(state_success)

    table1 = Table(title="Demo 1: Multi-Agent Deliberation Trace", border_style="green")
    table1.add_column("Round", justify="center")
    table1.add_column("Plan ID", style="cyan")
    table1.add_column("Proposed Action", style="white")
    table1.add_column("Status", justify="center")
    table1.add_column("Decision Rationale / Cited Clause", style="italic")

    for cand in final_state_1.get("candidates", []):
        vetoed = len(cand.get("vetoed_by", [])) > 0
        status_text = "[bold red]VETOED[/bold red]" if vetoed else "[bold green]PASS[/bold green]"
        reason = cand.get("veto_reasons", {}).get("crew") or cand.get("veto_reasons", {}).get("slot") or "Feasible & Legal (Surviving Plan)"
        table1.add_row(
            str(cand["round_created"]),
            cand["plan_id"],
            cand["operational_rationale"],
            status_text,
            reason
        )

    console.print(table1)

    selected_1 = final_state_1.get("selected_plan")
    if selected_1:
        scores = selected_1.get("scores", {})
        console.print(Panel(
            f"[bold green]RECOMMENDED PLAN FOR DUTY MANAGER APPROVAL:[/bold green]\n"
            f"Plan ID: [cyan]{selected_1['plan_id']}[/cyan] (Formulated in Round {selected_1['round_created']})\n"
            f"Operational Action: {selected_1['operational_rationale']}\n"
            f"Composite Penalty Score: [bold]{scores.get('composite_score', 'N/A')}[/bold] (Bounded [0, 1])\n"
            f"Component Penalties: Delay={scores.get('normalized_components', {}).get('delay')} | "
            f"Pax Disruption={scores.get('normalized_components', {}).get('pax')} | "
            f"Cost={scores.get('normalized_components', {}).get('cost')}",
            border_style="green"
        ))

    # =========================================================================
    # DEMO 2: FAILURE SCENARIO (Hard Constraints Trigger Mandatory Escalation)
    # =========================================================================
    console.print("\n[bold red]========================================================================[/bold red]")
    console.print("[bold red]=== DEMO 2: Severe Disruption Triggering Escalation (Round Exhaustion) ===[/bold red]")
    console.print("[bold red]========================================================================[/bold red]")

    # Crew member already exceeded duty limits (impossible to fly legally)
    crew_roster_2 = [
        {
            "crew_id": "CREW-EXHAUSTED",
            "duty_record": {"duty_start": (base_time - timedelta(hours=14)).isoformat()},
            "assigned_flights": ["6E-101"]
        }
    ]

    state_escalate = {
        "run_id": "DEMO-ESCALATE-02",
        "disruption": {
            "type": "fog",
            "airport": "VOBL",
            "affected_flight_id": "6E-101",
            "candidate_tail": "VT-BLR15"
        },
        "base_schedule": base_schedule,
        "active_crew": crew_roster_2,
        "slot_windows": slot_windows_1
    }

    final_state_2 = graph.invoke(state_escalate)

    table2 = Table(title="Demo 2: Deliberation Trace Resulting in Escalation", border_style="red")
    table2.add_column("Round", justify="center")
    table2.add_column("Plan ID", style="cyan")
    table2.add_column("Proposed Action", style="white")
    table2.add_column("Status", justify="center")
    table2.add_column("Rejection Rationale", style="italic")

    for cand in final_state_2.get("candidates", []):
        vetoed = len(cand.get("vetoed_by", [])) > 0
        status_text = "[bold red]VETOED[/bold red]" if vetoed else "[bold green]PASS[/bold green]"
        reason = cand.get("veto_reasons", {}).get("crew") or "Vetoed by hard constraint"
        table2.add_row(
            str(cand["round_created"]),
            cand["plan_id"],
            cand["operational_rationale"][:55] + "...",
            status_text,
            reason[:65] + "..."
        )

    console.print(table2)

    console.print(Panel(
        f"[bold red]DUTY MANAGER ESCALATION ALERT:[/bold red]\n"
        f"Status: [bold red]{final_state_2['status']}[/bold red]\n"
        f"Escalation Reason: {final_state_2.get('escalation_reason')}\n"
        f"Operational Impact: Zero plans survived hard constraint checks across {settings.MAX_NEGOTIATION_ROUNDS} rounds.",
        border_style="red"
    ))

    # =========================================================================
    # DEMO 3: NATURAL LANGUAGE DISRUPTION DISPATCH FROM DUTY MANAGER
    # =========================================================================
    console.print("\n[bold cyan]========================================================================[/bold cyan]")
    console.print("[bold cyan]=== DEMO 3: Natural Language Duty Manager Message Ingestion & Deliberation ===[/bold cyan]")
    console.print("[bold cyan]========================================================================[/bold cyan]")

    dm_message = (
        "Kempegowda BLR ground reports dense radiation fog dropping runway visual range below 250m. "
        "Flight 6E-101 is holding with estimated 180 min delay. Assess aircraft tail swap to VT-BLR15 or tactical delay."
    )

    console.print(Panel(
        f"[bold white]Duty Manager Dispatch Note:[/bold white]\n"
        f"[italic cyan]\"{dm_message}\"[/italic cyan]",
        title="[bold yellow]Human Duty Manager Ingestion[/bold yellow]",
        border_style="yellow"
    ))

    state_natural_lang = {
        "run_id": "DEMO-NL-DISPATCH-03",
        "duty_manager_message": dm_message,
        "base_schedule": base_schedule,
        "active_crew": crew_roster_1,
        "slot_windows": slot_windows_1
    }

    final_state_3 = graph.invoke(state_natural_lang)
    parsed = final_state_3.get("parsed_disruption") or {}

    console.print(Panel(
        f"[bold green]Mediator LLM Comprehension Breakdown:[/bold green]\n"
        f"• Tactical Summary: [white]{parsed.get('tactical_summary')}[/white]\n"
        f"• Disruption Class: [cyan]{parsed.get('disruption_type', '').upper()}[/cyan] | "
        f"Airport: [yellow]{parsed.get('airport')}[/yellow] | "
        f"Flight: [bold]{parsed.get('affected_flight_id')}[/bold]\n"
        f"• Severity: [red]{parsed.get('severity')}[/red] | "
        f"Impact Duration: [bold]{parsed.get('delay_minutes')}m[/bold] | "
        f"Initial Strategy: [italic]{parsed.get('initial_action')}[/italic]\n"
        f"• Standby Aircraft Identified: [green]{parsed.get('candidate_tail')}[/green] | "
        f"Parsed By: [dim]{parsed.get('parsed_by')}[/dim]",
        title="[bold green]Mediator Comprehension[/bold green]",
        border_style="cyan"
    ))

    table3 = Table(title="Demo 3: Deliberation Trace from Natural Language Dispatch", border_style="cyan")
    table3.add_column("Round", justify="center")
    table3.add_column("Plan ID", style="cyan")
    table3.add_column("Proposed Action", style="white")
    table3.add_column("Status", justify="center")
    table3.add_column("Compliance Decision", style="italic")

    for cand in final_state_3.get("candidates", []):
        vetoed = len(cand.get("vetoed_by", [])) > 0
        status_text = "[bold red]VETOED[/bold red]" if vetoed else "[bold green]PASS[/bold green]"
        reason = cand.get("veto_reasons", {}).get("crew") or cand.get("veto_reasons", {}).get("slot") or "Feasible & Compliant"
        table3.add_row(
            str(cand["round_created"]),
            cand["plan_id"],
            cand["operational_rationale"][:55] + "...",
            status_text,
            reason[:65] + "..."
        )

    console.print(table3)

    selected_3 = final_state_3.get("selected_plan")
    if selected_3:
        console.print(Panel(
            f"[bold green]AUTHORIZED OPERATIONAL PLAN:[/bold green]\n"
            f"Plan ID: [cyan]{selected_3['plan_id']}[/cyan]\n"
            f"Action: {selected_3['operational_rationale']}\n"
            f"Composite Score: {selected_3.get('scores', {}).get('composite_score', 'N/A')}\n\n"
            f"[bold]OCC Executive Briefing:[/bold]\n{selected_3.get('occ_briefing', 'N/A')}",
            border_style="green"
        ))


if __name__ == "__main__":
    run_vertical_slice_demo()
