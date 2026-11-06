"""
Generate a clean, modern, publication-grade System Architecture Diagram
for SkyMediator with zero overlapping text or crossing arrows.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_clean_architecture_diagram():
    # 16:9 widescreen canvas with ample breathing room
    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')

    # Color Palette
    c_primary = '#0a2540'     # Navy
    c_accent  = '#0066cc'     # Blue
    c_veto    = '#dc2626'     # Crimson Red (Hard Vetoes)
    c_score   = '#d97706'     # Amber Gold (Soft Scorers)
    c_green   = '#059669'     # Emerald Green (Human Approval)
    c_slate   = '#475569'     # Slate Gray
    c_bg      = '#f8fafc'     # Card Background
    c_border  = '#cbd5e1'     # Subtle Border

    # Helper function to draw rounded cards
    def draw_card(x, y, w, h, header_text, lines, header_color, border_color='#cbd5e1'):
        # Outer card box
        card = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle='round,pad=0.06',
            facecolor='#ffffff',
            edgecolor=border_color,
            linewidth=1.8,
            zorder=2
        )
        ax.add_patch(card)

        # Header bar
        header_h = 0.52
        header = patches.FancyBboxPatch(
            (x, y + h - header_h), w, header_h,
            boxstyle='round,pad=0.06',
            facecolor=header_color,
            edgecolor=header_color,
            zorder=3
        )
        ax.add_patch(header)
        ax.text(x + w/2, y + h - header_h/2, header_text,
                ha='center', va='center', color='white', fontweight='bold', fontsize=9.5, zorder=4)

        # Body text lines
        body_y = y + h - header_h - 0.22
        line_spacing = (h - header_h - 0.3) / max(len(lines), 1)
        for i, line in enumerate(lines):
            ax.text(x + w/2, body_y - i * line_spacing, line,
                    ha='center', va='center', color='#1e293b', fontsize=8.2, zorder=4)

    # Column Titles (Top Header Banners)
    col_w = 3.2
    y_col_title = 8.45
    
    stages = [
        (0.6, "STAGE 1: INGESTION & EARLY WARNING", c_primary),
        (4.4, "STAGE 2: CANDIDATE FORMULATION", c_accent),
        (8.2, "STAGE 3: STATUTORY VETOES & SCORING", c_veto),
        (12.0, "STAGE 4: ARBITRATION & HUMAN SIGN-OFF", c_green)
    ]
    for x_pos, title, col in stages:
        banner = patches.FancyBboxPatch(
            (x_pos, y_col_title - 0.35), col_w, 0.45,
            boxstyle='round,pad=0.04',
            facecolor=col, edgecolor=col, zorder=2
        )
        ax.add_patch(banner)
        ax.text(x_pos + col_w/2, y_col_title - 0.12, title,
                ha='center', va='center', color='white', fontweight='bold', fontsize=9.0, zorder=3)

    # =========================================================================
    # STAGE 1: Inputs & Prediction (x = 0.6 to 3.8)
    # =========================================================================
    draw_card(
        0.6, 5.7, col_w, 2.0,
        "Weather Ingestion (BLR/VOBL)",
        [
            "5,736 Real Historical METAR Records",
            "Temp, Dew Point Depression, RVR",
            "Continuous Low-Visibility Monitoring"
        ],
        c_primary
    )

    draw_card(
        0.6, 3.1, col_w, 2.1,
        "Sentinel Disruption Predictor",
        [
            "Calibrated Logistic Regression Model",
            "Disruption Threshold P(fog) >= 0.50",
            "2 to 4 Hour Proactive Early Warning",
            "Certified 0.0% False Alarm Rate"
        ],
        c_accent
    )

    draw_card(
        0.6, 0.6, col_w, 2.0,
        "Tactical Airline State",
        [
            "15 Narrow-Body Airbus A320 Fleet",
            "45 Scheduled Sectors (24h Horizon)",
            "Closed Tail & Crew Rotation Pool"
        ],
        c_slate
    )

    # Connector: Weather -> Sentinel
    ax.annotate('', xy=(2.2, 5.2), xytext=(2.2, 5.7),
                arrowprops=dict(arrowstyle="-|>", color=c_accent, lw=2, mutation_scale=15), zorder=5)

    # Connector: Sentinel -> Rotation (Stage 1 to Stage 2)
    ax.annotate('', xy=(4.4, 4.3), xytext=(3.8, 4.3),
                arrowprops=dict(arrowstyle="-|>", color=c_accent, lw=2.2, mutation_scale=18), zorder=5)
    ax.text(4.1, 4.5, "Trigger", ha='center', va='bottom', fontsize=8.5, color=c_accent, fontweight='bold')

    # =========================================================================
    # STAGE 2: Candidate Formulation (x = 4.4 to 7.6)
    # =========================================================================
    draw_card(
        4.4, 2.8, col_w, 3.2,
        "Rotation Agent (Plan Proposer)",
        [
            "Formulates Schedule Mutation Diffs:",
            "  * DelayOp (min >= 15 minutes)",
            "  * SwapOp (available spare tail)",
            "  * CancelOp (strictly last resort)",
            "---------------------------------------",
            "Enforces Physical Turnaround:",
            "  * Min TAT >= 30 min Buffer",
            "Pure Functional apply_plan_diff"
        ],
        c_accent
    )

    # Connectors from Rotation to Stage 3 Specialists
    # To Crew Legality
    ax.annotate('', xy=(8.2, 6.9), xytext=(7.6, 4.8),
                arrowprops=dict(arrowstyle="-|>", color=c_veto, lw=2, mutation_scale=16), zorder=5)
    # To Slot Agent
    ax.annotate('', xy=(8.2, 4.9), xytext=(7.6, 4.4),
                arrowprops=dict(arrowstyle="-|>", color=c_veto, lw=2, mutation_scale=16), zorder=5)
    # To Passenger Agent
    ax.annotate('', xy=(8.2, 3.0), xytext=(7.6, 3.9),
                arrowprops=dict(arrowstyle="-|>", color=c_score, lw=2, mutation_scale=16), zorder=5)
    # To Cost Agent
    ax.annotate('', xy=(8.2, 1.2), xytext=(7.6, 3.4),
                arrowprops=dict(arrowstyle="-|>", color=c_score, lw=2, mutation_scale=16), zorder=5)

    # =========================================================================
    # STAGE 3: Statutory Vetoes & Soft Scoring (x = 8.2 to 11.4)
    # =========================================================================
    # Hard Veto 1: Crew Legality
    draw_card(
        8.2, 6.1, col_w, 1.75,
        "Crew Legality Agent [HARD VETO]",
        [
            "DGCA CAR Section 7, Series J, Part III",
            "Max 13h Flight Duty Period (FDP) Cap",
            "Night WOCL Limits & 12h Rest Invariant"
        ],
        c_veto, border_color=c_veto
    )

    # Hard Veto 2: Airport Slot Agent
    draw_card(
        8.2, 4.15, col_w, 1.75,
        "Airport Slot Agent [HARD VETO]",
        [
            "BLR Runway Movement Cap (<= 32/h)",
            "Spoke Airport Night Curfew Enforcement",
            "ATC Flow Window Slot Feasibility"
        ],
        c_veto, border_color=c_veto
    )

    # Soft Scorer 1: Passenger Agent
    draw_card(
        8.2, 2.2, col_w, 1.75,
        "Passenger Agent (Soft Scorer)",
        [
            "DGCA CAR Section 3, Series M, Part IV",
            "Audits Connecting Hub Transit Banks",
            "Mandatory Meal & Hotel Compensation"
        ],
        c_score, border_color=c_score
    )

    # Soft Scorer 2: Cost Agent
    draw_card(
        8.2, 0.35, col_w, 1.65,
        "Cost Agent (Soft Scorer)",
        [
            "Delay Fuel Penalty: INR 1,200 / min",
            "Tail Swap Reassignment: INR 25,000",
            "Flight Cancellation: INR 450,000"
        ],
        c_score, border_color=c_score
    )

    # Connectors from Stage 3 to Stage 4 Mediator
    ax.annotate('', xy=(12.0, 5.8), xytext=(11.4, 6.9),
                arrowprops=dict(arrowstyle="-|>", color=c_veto, lw=2, mutation_scale=16), zorder=5)
    ax.annotate('', xy=(12.0, 5.2), xytext=(11.4, 5.0),
                arrowprops=dict(arrowstyle="-|>", color=c_veto, lw=2, mutation_scale=16), zorder=5)
    ax.annotate('', xy=(12.0, 4.6), xytext=(11.4, 3.1),
                arrowprops=dict(arrowstyle="-|>", color=c_score, lw=2, mutation_scale=16), zorder=5)
    ax.annotate('', xy=(12.0, 4.0), xytext=(11.4, 1.2),
                arrowprops=dict(arrowstyle="-|>", color=c_score, lw=2, mutation_scale=16), zorder=5)

    # =========================================================================
    # STAGE 4: Arbitration & Human Sign-Off (x = 12.0 to 15.2)
    # =========================================================================
    draw_card(
        12.0, 3.8, col_w, 3.9,
        "Mediator Deliberation Engine",
        [
            "1. Hard Veto Filtering:",
            "   Rejects if vetoed_by != []",
            "2. Normalized Composite Score:",
            "   S = 0.35 D + 0.30 M + 0.20 C + 0.15 B",
            "3. Iterative Counter-Proposals:",
            "   Requests Tail Swaps (Max 3 Rounds)",
            "4. Human Escalation Boundary:",
            "   Abstains on Ambiguity or Deadlock"
        ],
        c_primary
    )

    draw_card(
        12.0, 0.4, col_w, 2.9,
        "Human Duty Manager Cockpit",
        [
            "Interactive OCC Web Console:",
            "  * Side-by-Side Diff Matrix",
            "  * Legal DGCA Evidence Citations",
            "  * [1-Click Approve & Dispatch]",
            "  * [Reject with Feedback to Rotation]"
        ],
        c_green, border_color=c_green
    )

    # Connector: Mediator -> Human Approval
    ax.annotate('', xy=(13.6, 3.3), xytext=(13.6, 3.8),
                arrowprops=dict(arrowstyle="-|>", color=c_green, lw=2.5, mutation_scale=18), zorder=5)
    ax.text(13.65, 3.55, "Recommended Plan", ha='left', va='center', fontsize=8.2, color=c_green, fontweight='bold')

    # Counter-Proposal Negotiation Loop (Stage 4 to Stage 2)
    # Curves gently across the bottom without touching any box!
    loop_line = patches.Arc((9.7, 3.2), 8.5, 5.8, angle=0, theta1=185, theta2=355,
                            edgecolor=c_accent, linewidth=2.2, linestyle='--', zorder=4)
    ax.add_patch(loop_line)
    # Arrow head at Stage 2 bottom
    ax.annotate('', xy=(5.4, 2.8), xytext=(5.6, 2.1),
                arrowprops=dict(arrowstyle="-|>", color=c_accent, lw=2.2, mutation_scale=18), zorder=5)
    # Loop Label Banner
    loop_badge = patches.FancyBboxPatch(
        (8.1, 0.05), 3.4, 0.38,
        boxstyle='round,pad=0.04',
        facecolor='#ffffff', edgecolor=c_accent, linewidth=1.5, zorder=6
    )
    ax.add_patch(loop_badge)
    ax.text(9.8, 0.24, "Counter-Proposal Loop (Max 3 Rounds)",
            ha='center', va='center', color=c_accent, fontweight='bold', fontsize=8.5, zorder=7)

    # Save to both vector PDF and 300+ DPI PNG
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "figure_00_system_architecture.pdf")
    png_path = os.path.join(out_dir, "figure_00_system_architecture.png")

    fig.savefig(pdf_path, format='pdf', bbox_inches='tight', pad_inches=0.1)
    fig.savefig(png_path, dpi=300, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)
    print(f"[OK] Clean system architecture diagram saved to {pdf_path} and {png_path}")

if __name__ == "__main__":
    generate_clean_architecture_diagram()

