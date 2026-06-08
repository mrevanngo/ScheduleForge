"""
ScheduleForge - Adaptive daily schedule optimizer
Command-line tool for busy student-athlete-traders.
"""

from __future__ import annotations
import json
from datetime import datetime, time
from pathlib import Path
from typing import Optional
import sys

import typer
import questionary
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from scheduleforge.scheduler import (
    BlockType,
    ClassEntry,
    DayScheduler,
    GYM_ROTATION,
    GYM_ROTATION_SHORT,
    UserProfile,
    SleepAnalysis,
    analyze_sleep,
    NAP_DURATION_MINUTES,
    SLEEP_SKIP_TRADE_THRESHOLD,
    SLEEP_WARN_THRESHOLD,
    EMOJI,
    COLOR,
    current_day_abbr,
    parse_time,
    _add_minutes,
    _minutes_between,
)

console = Console()

CONFIG_PATH = Path.home() / ".config" / "scheduleforge" / "profile.json"

app = typer.Typer(
    name="scheduleforge",
    help="[bold magenta]ScheduleForge[/] - Your adaptive daily schedule optimizer.",
    rich_markup_mode="rich",
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_profile() -> UserProfile:
    return UserProfile.load(CONFIG_PATH)


def save_profile(p: UserProfile) -> None:
    p.save(CONFIG_PATH)


def _fmt_time(t: time) -> str:
    hour = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {ampm}"


def _render_schedule(blocks, day_label: str, gym_info: str = "") -> None:
    """Render a beautiful schedule table to the terminal."""
    title_parts = [f"[bold white]ScheduleForge[/] [dim]|[/] [bold cyan]{day_label}[/]"]
    if gym_info:
        title_parts.append(f"[dim]  {gym_info}[/]")

    console.print()
    console.print(Panel(
        " ".join(title_parts),
        border_style="bright_blue",
        padding=(0, 2),
    ))

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold bright_white",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Time", style="dim", width=16, justify="right")
    table.add_column("Block", min_width=30)
    table.add_column("Duration", width=10, justify="center")
    table.add_column("Notes", style="dim italic", min_width=20)

    sorted_blocks = sorted(blocks, key=lambda b: b.start)
    prev_type = None

    for b in sorted_blocks:
        # Skip free time blocks that are very short (< 15 min) - just clutter
        if b.block_type == BlockType.FREE and b.duration_minutes() < 15:
            continue

        emoji = EMOJI.get(b.block_type, "")
        color = COLOR.get(b.block_type, "white")
        time_str = f"{_fmt_time(b.start)} - {_fmt_time(b.end)}"
        dur = b.duration_minutes()
        dur_str = f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60:02d}m" if dur % 60 else f"{dur // 60}h"

        # Separator before sleep / wind-down
        if b.block_type in (BlockType.SLEEP, BlockType.WIND_DOWN) and prev_type not in (BlockType.SLEEP, BlockType.WIND_DOWN):
            table.add_section()

        label_text = f"{emoji}  [bold {color}]{b.label}[/]"
        table.add_row(time_str, label_text, dur_str, b.notes or "")
        prev_type = b.block_type

    console.print(table)
    console.print()


def _prompt_wake_time() -> time:
    """Interactively ask for wake time with quick-pick options."""
    choices = [
        "5:00 AM",
        "5:30 AM",
        "6:00 AM",
        "6:30 AM",
        "7:00 AM",
        "7:30 AM",
        "8:00 AM",
        "8:30 AM",
        "9:00 AM",
        "9:30 AM",
        "10:00 AM",
        "Custom...",
    ]
    answer = questionary.select(
        "What time did you wake up (or are planning to start your day)?",
        choices=choices,
    ).ask()

    if answer is None:
        raise typer.Abort()

    if answer == "Custom...":
        raw = questionary.text("Enter time (e.g. 7:15am):").ask()
        if raw is None:
            raise typer.Abort()
        return parse_time(raw)

    # Parse from choice string like "7:30 AM"
    return parse_time(answer.replace(" ", "").lower())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("go", help="[bold]Generate today's optimized schedule.[/] Quick one-command usage.")
def go(
    wake: Optional[str] = typer.Option(None, "--wake", "-w", help="Wake time e.g. '7:30am'"),
    day: Optional[str] = typer.Option(None, "--day", "-d", help="Day override e.g. 'Mon'"),
    climb: bool = typer.Option(False, "--climb", "-c", help="Sub back day with rock climbing"),
    sleep: Optional[str] = typer.Option(None, "--sleep", "-s", help="Target sleep time e.g. '11pm'"),
    no_advance: bool = typer.Option(False, "--no-advance", help="Don't advance gym rotation after display"),
    nap: bool = typer.Option(False, "--nap", "-n", help="Insert a recovery nap block (25 min, post-lunch)"),
    deprived: bool = typer.Option(False, "--deprived", help="Flag day as sleep-deprived (shows warning banner)"),
):
    """The main command: generates and prints today's schedule."""
    profile = load_profile()

    if not profile.classes and not CONFIG_PATH.exists():
        console.print(
            Panel(
                "[yellow]No profile found.[/]\n"
                "Run [bold cyan]scheduleforge setup[/] first to configure your schedule.\n"
                "Or run [bold cyan]scheduleforge go[/] anyway for a demo with defaults.",
                title="First run",
                border_style="yellow",
            )
        )
        cont = questionary.confirm("Continue with default settings?", default=True).ask()
        if not cont:
            raise typer.Exit()

    # Resolve wake time
    if wake:
        wake_time = parse_time(wake)
    else:
        wake_time = _prompt_wake_time()

    # Resolve day
    dow = day if day else current_day_abbr()
    # Normalize
    dow = dow.capitalize()[:3]

    # Resolve sleep time
    target_sleep = parse_time(sleep) if sleep else None

    # Build schedule
    scheduler = DayScheduler(
        wake_time=wake_time,
        day_of_week=dow,
        profile=profile,
        rock_climbing=climb,
        target_sleep=target_sleep,
        sleep_deprived=deprived,
        place_nap=nap,
    )
    blocks = scheduler.build()

    # Gym rotation label
    gym_info = ""
    if dow in profile.gym_days:
        workout = GYM_ROTATION[profile.gym_rotation_index]
        short = GYM_ROTATION_SHORT[profile.gym_rotation_index]
        if profile.gym_rotation_index == 0 and climb:
            gym_info = "🧗 Rock Climbing day (sub for Back+Bi)"
        else:
            gym_info = f"Gym: {workout}"

    now = datetime.now()
    day_label = f"{dow}, {now.strftime('%B')} {now.day}"

    # Show sleep-deprived warning banner if flagged
    if deprived:
        console.print(Panel(
            "[bold yellow]⚠  Sleep-deprived day[/]\n"
            "[dim]Cognitive performance and reaction time are reduced. "
            "Keep position sizes small, set hard stop-losses, and take a nap if possible.[/]",
            border_style="yellow",
            padding=(0, 2),
        ))

    _render_schedule(blocks, day_label, gym_info)

    # Stats summary
    total_blocks = {bt: 0 for bt in BlockType}
    for b in blocks:
        total_blocks[b.block_type] += b.duration_minutes()

    sleep_min = total_blocks[BlockType.SLEEP]
    free_min  = total_blocks[BlockType.FREE]
    train_min = total_blocks[BlockType.SWIM] + total_blocks[BlockType.RUN] + total_blocks[BlockType.GYM]

    summary = Text()
    summary.append(f"Sleep: {sleep_min // 60}h {sleep_min % 60:02d}m  ", style="blue")
    summary.append(f"Training: {train_min}m  ", style="red")
    summary.append(f"Free: {free_min}m", style="bright_green")

    console.print(Panel(summary, title="[dim]Day summary[/]", border_style="dim", padding=(0, 2)))
    console.print()

    # Advance gym rotation for next gym day (unless suppressed)
    if dow in profile.gym_days and not no_advance:
        next_workout = GYM_ROTATION[(profile.gym_rotation_index + 1) % 3]
        profile.advance_gym_rotation()
        save_profile(profile)
        console.print(
            f"[dim]Gym rotation advanced. Next gym session: [bold]{next_workout}[/][/]"
        )
        console.print()


@app.command("week", help="Preview your schedule for the entire week.")
def week(
    wake: str = typer.Option("7:00am", "--wake", "-w", help="Default wake time for all days"),
    sleep: Optional[str] = typer.Option(None, "--sleep", "-s", help="Target sleep time"),
):
    """Show a high-level view of the whole week."""
    profile = load_profile()
    wake_time = parse_time(wake)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    table = Table(
        title="[bold]Weekly Overview[/]",
        box=box.SIMPLE_HEAD,
        border_style="dim",
        header_style="bold bright_white",
        expand=True,
    )
    table.add_column("Day", width=6, style="bold")
    table.add_column("Gym / Training", width=30)
    table.add_column("Classes", min_width=20)
    table.add_column("Market", width=8, justify="center")
    table.add_column("Internship", width=10, justify="center")

    rot_idx = profile.gym_rotation_index
    for d in days:
        # Gym
        if d in profile.gym_days:
            gym_label = f"🏋️  {GYM_ROTATION[rot_idx]}"
            rot_idx = (rot_idx + 1) % 3
        else:
            gym_label = ""

        # Triathlon
        tri_parts = []
        if d in profile.swim_days:
            tri_parts.append(f"🏊 Swim ({profile.swim_duration}m)")
        if d in profile.run_days:
            tri_parts.append(f"🏃 Run ({profile.run_duration}m)")
        tri_label = "  ".join(tri_parts)

        combined = "\n".join(filter(None, [gym_label, tri_label]))

        # Classes
        today_classes = [c for c in profile.classes if d in c.days]
        class_label = "\n".join(
            f"📚 {c.name} {_fmt_time(c.start)}-{_fmt_time(c.end)}" for c in today_classes
        ) or "[dim]No classes[/]"

        market = "✅" if profile.day_trade else ""
        intern = "✅" if d in profile.internship_days else ""

        table.add_row(d, combined or "[dim]-[/]", class_label, market, intern)

    console.print()
    console.print(table)
    console.print()


@app.command("setup", help="[bold]Interactive setup[/] to configure your weekly schedule.")
def setup():
    """Walk through initial (or updated) profile configuration."""
    console.print()
    console.print(Panel(
        "[bold]Welcome to ScheduleForge Setup[/]\n"
        "Answer a few questions to configure your personalized schedule optimizer.",
        border_style="bright_blue",
        padding=(1, 2),
    ))

    profile = load_profile()

    # --- Classes ---
    console.print("\n[bold cyan]Step 1: Classes[/]")
    if profile.classes:
        console.print(f"You currently have [bold]{len(profile.classes)}[/] class(es) configured.")
        redo = questionary.confirm("Re-configure classes?", default=False).ask()
        if redo:
            profile.classes = []
    
    if not profile.classes:
        console.print("Enter your UCSD class schedule. Type [bold]done[/] when finished.")
        while True:
            name = questionary.text("Class name (or 'done'):").ask()
            if name is None or name.lower() == "done":
                break
            if not name.strip():
                continue

            days_answer = questionary.checkbox(
                f"Which days does [bold]{name}[/] meet?",
                choices=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            ).ask()
            if not days_answer:
                continue

            start_str = questionary.text(f"Start time for {name} (e.g. 9:30am):").ask()
            end_str   = questionary.text(f"End time for {name} (e.g. 10:50am):").ask()
            location  = questionary.text(f"Location (optional):").ask() or ""

            try:
                entry = ClassEntry(
                    name=name,
                    days=days_answer,
                    start=parse_time(start_str),
                    end=parse_time(end_str),
                    location=location,
                )
                profile.classes.append(entry)
                console.print(f"[green]✓ Added {name}[/]")
            except Exception as e:
                console.print(f"[red]Error parsing times: {e}. Skipping.[/]")

    # --- Day trading ---
    console.print("\n[bold cyan]Step 2: Day Trading[/]")
    profile.day_trade = questionary.confirm(
        "Do you day trade (market open 6:30 AM PST)?",
        default=profile.day_trade,
    ).ask() or False

    # --- Gym ---
    console.print("\n[bold cyan]Step 3: Gym Schedule[/]")
    valid_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    gym_days = questionary.checkbox(
        "Which days do you go to the gym?",
        choices=valid_days,
    ).ask()
    if gym_days:
        profile.gym_days = gym_days

    profile.rock_climbing_substitutes = questionary.confirm(
        "Can back day be substituted with rock climbing?",
        default=profile.rock_climbing_substitutes,
    ).ask() or False

    dur_str = questionary.text(f"Gym session duration in minutes [{profile.gym_duration}]:").ask()
    if dur_str and dur_str.strip().isdigit():
        profile.gym_duration = int(dur_str.strip())

    # --- Triathlon ---
    console.print("\n[bold cyan]Step 4: Triathlon Training[/]")
    swim_days = questionary.checkbox(
        "Which days do you swim?",
        choices=valid_days,
    ).ask()
    if swim_days is not None:
        profile.swim_days = swim_days

    run_days = questionary.checkbox(
        "Which days do you run?",
        choices=valid_days,
    ).ask()
    if run_days is not None:
        profile.run_days = run_days

    swim_dur_str = questionary.text(f"Swim session duration in minutes [{profile.swim_duration}]:").ask()
    if swim_dur_str and swim_dur_str.strip().isdigit():
        profile.swim_duration = int(swim_dur_str.strip())

    run_dur_str = questionary.text(f"Run session duration in minutes [{profile.run_duration}]:").ask()
    if run_dur_str and run_dur_str.strip().isdigit():
        profile.run_duration = int(run_dur_str.strip())

    # --- Internship ---
    console.print("\n[bold cyan]Step 5: Internship Applications[/]")
    intern_days = questionary.checkbox(
        "Which days do you want to block time for internship apps?",
        choices=valid_days,
    ).ask()
    if intern_days is not None:
        profile.internship_days = intern_days

    internship_dur_str = questionary.text(f"Internship application block duration in minutes [{profile.internship_block}]:").ask()
    if internship_dur_str and internship_dur_str.strip().isdigit():
        profile.internship_block = int(internship_dur_str.strip())

    # --- Day Trading ---
    console.print("\n[bold cyan]Step 6: Day Trading[/]")
    market_dur_str = questionary.text(f"Market watch duration in minutes [{profile.market_watch_duration}]:").ask()
    if market_dur_str and market_dur_str.strip().isdigit():
        profile.market_watch_duration = int(market_dur_str.strip())

    # --- Sleep ---
    console.print("\n[bold cyan]Step 7: Sleep[/]")
    sleep_str = questionary.text(
        f"Target sleep time [{_fmt_time(profile.preferred_sleep_time)}]:"
    ).ask()
    if sleep_str and sleep_str.strip():
        try:
            profile.preferred_sleep_time = parse_time(sleep_str)
        except Exception:
            pass

    hrs_str = questionary.text(f"Target sleep hours [{profile.target_sleep_hours}]:").ask()
    if hrs_str and hrs_str.strip():
        try:
            profile.target_sleep_hours = float(hrs_str.strip())
        except Exception:
            pass

    save_profile(profile)
    console.print()
    console.print(Panel(
        "[bold green]✓ Profile saved![/]\n"
        "Run [bold cyan]scheduleforge go[/] to generate today's schedule.",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()


@app.command("gym", help="Show and manage the gym rotation.")
def gym(
    reset: bool = typer.Option(False, "--reset", help="Reset rotation to Back+Bi"),
    set_idx: Optional[int] = typer.Option(None, "--set", help="Set rotation index (0=Back, 1=Chest, 2=Legs)"),
    back: bool = typer.Option(False, "--back", "-b", help="Go back one in rotation"),
):
    """Manage the 3-day gym rotation."""
    profile = load_profile()

    if reset:
        profile.gym_rotation_index = 0
        save_profile(profile)
        console.print("[green]Gym rotation reset to Back+Bi.[/]")

    if set_idx is not None:
        if 0 <= set_idx <= 2:
            profile.gym_rotation_index = set_idx
            save_profile(profile)
            console.print(f"[green]Gym rotation set to: {GYM_ROTATION[set_idx]}[/]")
        else:
            console.print("[red]Index must be 0, 1, or 2.[/]")
            return

    if back:
        profile.gym_rotation_index = (profile.gym_rotation_index - 1) % 3
        save_profile(profile)
        console.print(f"[yellow]Backed up rotation to: {GYM_ROTATION[profile.gym_rotation_index]}[/]")

    # Display rotation
    console.print()
    table = Table(box=box.SIMPLE_HEAD, border_style="dim", header_style="bold")
    table.add_column("", width=4)
    table.add_column("Workout")
    table.add_column("Muscles", style="dim")

    workouts = [
        ("Back & Biceps",               "Lats, rhomboids, traps, biceps, rear delts"),
        ("Chest, Shoulders & Triceps",  "Pecs, anterior/lateral delts, triceps"),
        ("Legs",                        "Quads, hamstrings, glutes, calves"),
    ]

    for i, (name, muscles) in enumerate(workouts):
        is_active = (i == profile.gym_rotation_index)
        marker = "➤" if is_active else " "
        if is_active:
            table.add_row(
                f"[bold bright_yellow]{marker}[/]",
                f"[bold bright_yellow]{name}[/]",
                muscles,
            )
        else:
            table.add_row(marker, name, muscles)

    console.print(Panel(table, title="[bold]Gym Rotation[/]", border_style="dim"))
    console.print(
        f"[dim]Next session: [bold]{GYM_ROTATION[profile.gym_rotation_index]}[/][/]"
    )
    console.print()


@app.command("profile", help="Display current profile configuration.")
def show_profile():
    """Show the stored profile."""
    profile = load_profile()

    table = Table(box=box.ROUNDED, border_style="dim", show_header=False, padding=(0, 1))
    table.add_column("Key", style="dim", width=25)
    table.add_column("Value")

    table.add_row("Day trading", "✅ Yes" if profile.day_trade else "❌ No")
    table.add_row("Gym days", ", ".join(profile.gym_days) or "None")
    table.add_row("Swim days", ", ".join(profile.swim_days) or "None")
    table.add_row("Run days", ", ".join(profile.run_days) or "None")
    table.add_row("Internship days", ", ".join(profile.internship_days) or "None")
    table.add_row("Gym duration", f"{profile.gym_duration} min")
    table.add_row("Swim duration", f"{profile.swim_duration} min")
    table.add_row("Run duration", f"{profile.run_duration} min")
    table.add_row("Target sleep", _fmt_time(profile.preferred_sleep_time))
    table.add_row("Sleep hours", f"{profile.target_sleep_hours}h")
    table.add_row("Rock climbing sub", "✅ Yes" if profile.rock_climbing_substitutes else "❌ No")
    table.add_row("Next gym workout", GYM_ROTATION[profile.gym_rotation_index])

    if profile.classes:
        class_str = "\n".join(
            f"{c.name} ({', '.join(c.days)}) {_fmt_time(c.start)}-{_fmt_time(c.end)}"
            for c in profile.classes
        )
    else:
        class_str = "None configured"
    table.add_row("Classes", class_str)

    console.print()
    console.print(Panel(table, title="[bold]ScheduleForge Profile[/]", border_style="bright_blue"))
    console.print()



@app.command("bedtime", help="[bold]Sleep optimizer.[/] Run this right before bed to get tomorrow's plan.")
def bedtime(
    time_str: Optional[str] = typer.Argument(None, help="Bedtime e.g. '4am' or '11:30pm' (defaults to now)"),
    tomorrow: Optional[str] = typer.Option(None, "--day", "-d", help="Tomorrow's day e.g. 'Tue'"),
):
    """
    Analyze your sleep window and get a recommendation for tomorrow.

    Tell it when you're going to sleep and it calculates how much sleep you'll
    get before your first hard obligation (class or market open). If you're under
    5.5 hours it recommends skipping trading. If you trade anyway, it builds
    tomorrow's schedule with a recovery nap slotted in.
    """
    profile = load_profile()

    # Resolve bedtime
    if time_str:
        bed = parse_time(time_str)
    else:
        now = datetime.now()
        bed = now.time().replace(second=0, microsecond=0)
        console.print(f"[dim]Using current time as bedtime: {_fmt_time(bed)}[/]")

    # Resolve tomorrow's day
    if tomorrow:
        tmr_dow = tomorrow.capitalize()[:3]
    else:
        days_seq = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        today_idx = days_seq.index(current_day_abbr()) if current_day_abbr() in days_seq else 0
        tmr_dow = days_seq[(today_idx + 1) % 7]

    analysis = analyze_sleep(bed, tmr_dow, profile)

    # -----------------------------------------------------------------------
    # Render the analysis panel
    # -----------------------------------------------------------------------
    console.print()

    # Sleep hours display
    hrs = int(analysis.sleep_hours)
    mins = int((analysis.sleep_hours - hrs) * 60)
    sleep_str = f"{hrs}h {mins:02d}m"

    if analysis.sleep_hours < SLEEP_SKIP_TRADE_THRESHOLD:
        hours_color = "bold red"
    elif analysis.sleep_hours < SLEEP_WARN_THRESHOLD:
        hours_color = "bold yellow"
    else:
        hours_color = "bold green"

    lines = [
        f"  Bedtime:          [dim]{_fmt_time(bed)}[/]",
        f"  Next obligation:  [dim]{_fmt_time(analysis.next_obligation)} - {analysis.obligation_label}[/]",
        f"  Sleep available:  [{hours_color}]{sleep_str}[/]",
    ]
    console.print(Panel("\n".join(lines), title="[bold]Sleep Analysis[/]", border_style="bright_blue", padding=(0, 1)))

    # Trading recommendation
    console.print()
    if analysis.skip_trading:
        console.print(Panel(
            f"[bold red]Skip trading tomorrow.[/]\n[dim]{analysis.trading_reason}[/]",
            title="📈  Market recommendation",
            border_style="red",
            padding=(0, 2),
        ))
    else:
        color = "yellow" if analysis.sleep_hours < SLEEP_WARN_THRESHOLD else "green"
        console.print(Panel(
            f"[bold {color}]Trading is fine.[/]\n[dim]{analysis.trading_reason}[/]",
            title="📈  Market recommendation",
            border_style=color,
            padding=(0, 2),
        ))

    # Nap recommendation
    console.print()
    if analysis.nap_slots:
        nap_start, nap_end = analysis.nap_slots[0]
        console.print(Panel(
            f"[bold]Recommended nap:[/] {_fmt_time(nap_start)} - {_fmt_time(nap_end)} "
            f"[dim]({NAP_DURATION_MINUTES} min)[/]\n"
            "[dim]Post-lunch naps align with your natural circadian dip and restore "
            "alertness without disrupting night sleep. Set a firm alarm.[/]",
            title="💤  Recovery nap",
            border_style="bright_blue",
            padding=(0, 2),
        ))
    else:
        console.print("[dim]No nap needed based on your sleep window.[/]")

    # -----------------------------------------------------------------------
    # Ask what to do next
    # -----------------------------------------------------------------------
    console.print()
    if analysis.skip_trading:
        choices = [
            f"Generate tomorrow's schedule (no trading, {tmr_dow})",
            f"Generate tomorrow's schedule WITH trading anyway + nap ({tmr_dow})",
            "Exit - I'll decide in the morning",
        ]
    else:
        choices = [
            f"Generate tomorrow's schedule ({tmr_dow})",
            f"Generate with recovery nap block ({tmr_dow})",
            "Exit",
        ]

    answer = questionary.select("What would you like to do?", choices=choices).ask()
    if answer is None or "Exit" in answer:
        console.print()
        return

    use_nap     = "nap" in answer.lower()
    skip_market = analysis.skip_trading and "WITH trading" not in answer

    # Prompt wake time
    wake_str = questionary.text(
        f"What time do you plan to wake up tomorrow? (default: {_fmt_time(analysis.next_obligation)})"
    ).ask()
    if wake_str and wake_str.strip():
        try:
            wake_time = parse_time(wake_str.strip())
        except Exception:
            wake_time = analysis.next_obligation
    else:
        wake_time = analysis.next_obligation

    # Temporarily override day_trade if skipping market
    effective_profile = profile
    if skip_market and profile.day_trade:
        import copy
        effective_profile = copy.copy(profile)
        effective_profile.day_trade = False

    scheduler = DayScheduler(
        wake_time=wake_time,
        day_of_week=tmr_dow,
        profile=effective_profile,
        sleep_deprived=(analysis.sleep_hours < SLEEP_WARN_THRESHOLD),
        place_nap=use_nap,
    )
    blocks = scheduler.build()

    console.print()

    gym_info = ""
    if tmr_dow in profile.gym_days:
        gym_info = f"Gym: {GYM_ROTATION[profile.gym_rotation_index]}"

    day_label = f"{tmr_dow} (tomorrow)"

    if analysis.sleep_hours < SLEEP_WARN_THRESHOLD:
        console.print(Panel(
            "[bold yellow]⚠  Sleep-deprived day[/]\n"
            "[dim]Cognitive performance and reaction time are reduced. "
            "Keep position sizes small, set hard stop-losses, and take the nap.[/]",
            border_style="yellow",
            padding=(0, 2),
        ))

    _render_schedule(blocks, day_label, gym_info)
    console.print()


def main():
    app()


if __name__ == "__main__":
    main()
