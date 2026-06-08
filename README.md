# ScheduleForge

ScheduleForge is an adaptive daily schedule optimizer for busy student-athlete-traders. Tell it when you woke up and it generates a realistic, conflict-free schedule that fits in day trading (market open 6:30 AM PST), your UCSD class times, gym sessions (3-day rotation: Back+Bi, Chest+Tri, Legs), triathlon training (swim/run), and internship application blocks -- all automatically adjusted around each other.

## Installation

```bash
uv add "git+https://github.com/<your-username>/scheduleforge.git"
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Usage

### First-time setup

Run the interactive setup wizard to configure your class schedule, gym days, training preferences, and sleep targets:

```bash
scheduleforge setup
```

### Generate today's schedule

```bash
scheduleforge go
```

This prompts you for your wake time and outputs a full optimized day. Every activity is slotted around your fixed classes and the market open window.

**Options:**

```bash
# Specify wake time directly (skip the prompt)
scheduleforge go --wake 6:30am

# Override the day (useful for planning ahead)
scheduleforge go --wake 7:00am --day Tue

# Substitute back day with rock climbing
scheduleforge go --wake 6:00am --climb

# Set a custom sleep target for tonight
scheduleforge go --wake 7:30am --sleep 10:30pm

# Don't advance the gym rotation after displaying
scheduleforge go --no-advance
```

### Preview the whole week

```bash
scheduleforge week
```

Shows a high-level grid of your entire week: which days have gym, swim, run, classes, market hours, and internship blocks.

### Manage the gym rotation

```bash
# See where you are in the rotation
scheduleforge gym

# Manually correct the rotation if needed
scheduleforge gym --set 1     # 0=Back+Bi, 1=Chest+Tri, 2=Legs
scheduleforge gym --back      # undo last advance
scheduleforge gym --reset     # restart from Back+Bi
```

### View your stored profile

```bash
scheduleforge profile
```

## How it works

The scheduler treats your day as a constraint-satisfaction problem. Hard constraints (class times, market open window) are placed first and cannot be moved. Flexible activities (gym, swim, run, meals, internship block) are then slotted into remaining free time using priority windows -- gym prefers 10 AM-3 PM, training prefers the post-market morning, internship apps prefer the early afternoon. Gaps of 15+ minutes become labeled free/study blocks. Sleep and wind-down are anchored to your configured target bedtime.

Your gym rotation (Back+Bi → Chest+Tri → Legs) advances automatically each time you generate a schedule on a gym day. The profile is stored in `~/.config/scheduleforge/profile.json`.

## Example output

```
╭──────────────────────────────────────────────────────╮
│ ScheduleForge | Mon, June 9   Gym: Back & Biceps     │
╰──────────────────────────────────────────────────────╯
 Time              Block                   Duration  Notes
 5:45 AM - 6:05 AM  ☕  Morning routine      20m
 6:05 AM - 6:35 AM  📈  Pre-market prep      30m     Scan watchlist
 6:35 AM - 8:05 AM  📈  Market open          1h 30m  First 90 min: peak vol
 8:05 AM - 11:00 AM 🎯  Study / deep work    2h 55m
11:00 AM - 12:20 PM 📚  DSC 148             1h 20m
12:20 PM - 1:35 PM  🏋️  Gym: Back & Biceps  1h 15m
 1:35 PM - 1:50 PM  ☕  Post-gym            15m     Shower, protein shake
 1:50 PM - 2:30 PM  🍽️  Lunch              40m
 2:30 PM - 4:00 PM  💼  Internship apps     1h 30m  Job boards, networking
...
```

## Configuration file

Your profile lives at `~/.config/scheduleforge/profile.json` and can be edited directly or updated via `scheduleforge setup`. The gym rotation index persists between sessions so you never lose track of which workout is next.

## Tips

- Run `scheduleforge go --wake $(date +%H:%M)` to use your current time as the wake input on Unix/macOS.
- Use `--no-advance` when testing or re-running the same day so the gym rotation does not advance twice.
- The `--climb` flag only activates on Back+Bi days; on other gym days it is ignored.

## Sleep optimizer

Run this right before bed and ScheduleForge will tell you exactly how much sleep you'll get before your first hard obligation tomorrow (class or market open), then advise you accordingly:

```bash
scheduleforge bedtime 4am
scheduleforge bedtime 11:30pm
scheduleforge bedtime          # uses current time
```

**What it does:**

- **< 5.5h before market open** - recommends skipping trading. Impaired reaction time and decision quality mean the risk/reward isn't there.
- **5.5 - 6.5h** - marginal: recommends paper-trading only, small position sizes, and a hard stop-loss rule set before open.
- **> 6.5h** - you're good.

After the analysis, it offers to generate tomorrow's full schedule. If you're trading on low sleep (or just want one), it slots a **25-minute recovery nap** in the 12:30-3 PM post-lunch window - the optimal time based on your natural circadian dip, short enough to avoid sleep inertia.

You can also add a nap to any `go` schedule manually:

```bash
scheduleforge go --wake 6:30am --nap
scheduleforge go --wake 6:30am --nap --deprived   # also shows warning banner
```
