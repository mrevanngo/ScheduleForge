"""
Core scheduling engine for ScheduleForge.
Handles constraint satisfaction and intelligent block placement.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
import json
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------

class BlockType(str, Enum):
    SLEEP       = "sleep"
    MARKET      = "market"
    CLASS       = "class"
    GYM         = "gym"
    SWIM        = "swim"
    RUN         = "run"
    INTERNSHIP  = "internship"
    MEAL        = "meal"
    BUFFER      = "buffer"
    FREE        = "free"
    WIND_DOWN   = "wind_down"
    NAP         = "nap"


GYM_ROTATION = ["Back & Biceps", "Chest, Shoulders & Triceps", "Legs"]
GYM_ROTATION_SHORT = ["Back+Bi", "Chest+Tri", "Legs"]

EMOJI = {
    BlockType.SLEEP:      "😴",
    BlockType.MARKET:     "📈",
    BlockType.CLASS:      "📚",
    BlockType.GYM:        "🏋️",
    BlockType.SWIM:       "🏊",
    BlockType.RUN:        "🏃",
    BlockType.INTERNSHIP: "💼",
    BlockType.MEAL:       "🍽️",
    BlockType.BUFFER:     "☕",
    BlockType.FREE:       "🎯",
    BlockType.WIND_DOWN:  "🌙",
    BlockType.NAP:        "💤",
}

COLOR = {
    BlockType.SLEEP:      "blue",
    BlockType.MARKET:     "green",
    BlockType.CLASS:      "cyan",
    BlockType.GYM:        "red",
    BlockType.SWIM:       "bright_blue",
    BlockType.RUN:        "yellow",
    BlockType.INTERNSHIP: "magenta",
    BlockType.MEAL:       "bright_yellow",
    BlockType.BUFFER:     "white",
    BlockType.FREE:       "bright_green",
    BlockType.WIND_DOWN:  "bright_black",
    BlockType.NAP:        "bright_blue",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TimeBlock:
    start: time
    end: time
    block_type: BlockType
    label: str
    notes: str = ""
    optional: bool = False

    def duration_minutes(self) -> int:
        s = datetime.combine(date.today(), self.start)
        e = datetime.combine(date.today(), self.end)
        if e < s:
            e += timedelta(days=1)
        return int((e - s).total_seconds() / 60)

    def overlaps(self, other: "TimeBlock") -> bool:
        return self.start < other.end and other.start < self.end

    def __repr__(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')} [{self.label}]"


@dataclass
class ClassEntry:
    name: str
    days: list[str]
    start: time
    end: time
    location: str = ""


@dataclass
class UserProfile:
    classes: list[ClassEntry] = field(default_factory=list)
    gym_days: list[str] = field(default_factory=lambda: ["Mon", "Wed", "Fri"])
    triathlon_days: list[str] = field(default_factory=lambda: ["Tue", "Thu", "Sat"])
    swim_days: list[str] = field(default_factory=lambda: ["Tue", "Sat"])
    run_days: list[str] = field(default_factory=lambda: ["Thu", "Sat"])
    internship_days: list[str] = field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])
    gym_rotation_index: int = 0
    rock_climbing_substitutes: bool = True
    day_trade: bool = True
    target_sleep_hours: float = 7.5
    preferred_sleep_time: time = field(default_factory=lambda: time(23, 0))
    gym_duration: int = 75
    swim_duration: int = 60
    run_duration: int = 45
    internship_block: int = 90
    market_watch_duration: int = 90

    @classmethod
    def load(cls, path: Path) -> "UserProfile":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        p = cls()
        p.classes = [
            ClassEntry(
                name=c["name"],
                days=c["days"],
                start=time.fromisoformat(c["start"]),
                end=time.fromisoformat(c["end"]),
                location=c.get("location", ""),
            )
            for c in data.get("classes", [])
        ]
        p.gym_days              = data.get("gym_days", p.gym_days)
        p.triathlon_days        = data.get("triathlon_days", p.triathlon_days)
        p.swim_days             = data.get("swim_days", p.swim_days)
        p.run_days              = data.get("run_days", p.run_days)
        p.internship_days       = data.get("internship_days", p.internship_days)
        p.gym_rotation_index    = data.get("gym_rotation_index", 0)
        p.rock_climbing_substitutes = data.get("rock_climbing_substitutes", True)
        p.day_trade             = data.get("day_trade", True)
        p.target_sleep_hours    = data.get("target_sleep_hours", 7.5)
        p.preferred_sleep_time  = time.fromisoformat(data.get("preferred_sleep_time", "23:00"))
        p.gym_duration          = data.get("gym_duration", 75)
        p.swim_duration         = data.get("swim_duration", 60)
        p.run_duration          = data.get("run_duration", 45)
        p.internship_block      = data.get("internship_block", 90)
        p.market_watch_duration = data.get("market_watch_duration", 90)
        return p

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "classes": [
                {
                    "name": c.name,
                    "days": c.days,
                    "start": c.start.isoformat(),
                    "end": c.end.isoformat(),
                    "location": c.location,
                }
                for c in self.classes
            ],
            "gym_days":           self.gym_days,
            "triathlon_days":     self.triathlon_days,
            "swim_days":          self.swim_days,
            "run_days":           self.run_days,
            "internship_days":    self.internship_days,
            "gym_rotation_index": self.gym_rotation_index,
            "rock_climbing_substitutes": self.rock_climbing_substitutes,
            "day_trade":          self.day_trade,
            "target_sleep_hours": self.target_sleep_hours,
            "preferred_sleep_time": self.preferred_sleep_time.isoformat(),
            "gym_duration":       self.gym_duration,
            "swim_duration":      self.swim_duration,
            "run_duration":       self.run_duration,
            "internship_block":   self.internship_block,
            "market_watch_duration": self.market_watch_duration,
        }
        path.write_text(json.dumps(data, indent=2))

    def advance_gym_rotation(self) -> None:
        self.gym_rotation_index = (self.gym_rotation_index + 1) % len(GYM_ROTATION)


# ---------------------------------------------------------------------------
# Sleep analysis
# ---------------------------------------------------------------------------

@dataclass
class SleepAnalysis:
    """Result of the bedtime sleep optimizer."""
    bedtime: time
    next_obligation: time           # first hard commitment next day
    obligation_label: str           # what the obligation is
    sleep_hours: float
    skip_trading: bool              # recommendation
    trading_reason: str             # human-readable explanation
    nap_slots: list[tuple[time, time]]   # recommended nap windows if trading anyway


# Thresholds (hours)
SLEEP_SKIP_TRADE_THRESHOLD = 5.5   # below this: recommend skipping market
SLEEP_WARN_THRESHOLD       = 6.5   # below this: warn but don't block
NAP_DURATION_MINUTES       = 25    # science-backed: ~20-25 min avoids sleep inertia


def analyze_sleep(
    bedtime: time,
    day_of_week: str,            # the NEXT day (tomorrow)
    profile: "UserProfile",
) -> SleepAnalysis:
    """
    Given a bedtime right now, figure out how much sleep is possible before
    the next hard obligation tomorrow and advise accordingly.

    Logic:
    - Next obligation = earliest of: first class, market open (if trading day), 
      or a sane default wake (10 AM).
    - If sleep < SLEEP_SKIP_TRADE_THRESHOLD: strongly recommend skipping trading.
    - Nap slots: post-lunch (12:30-3 PM window) in 25-min blocks, avoiding classes.
    """
    market_open = time(6, 30)  # PST

    # Find tomorrow's classes
    tomorrow_classes = sorted(
        [c for c in profile.classes if day_of_week in c.days],
        key=lambda c: c.start,
    )
    first_class = tomorrow_classes[0].start if tomorrow_classes else None

    # Determine next hard obligation
    is_trading_day = profile.day_trade  # trading every weekday by default
    weekdays = {"Mon", "Tue", "Wed", "Thu", "Fri"}
    if day_of_week not in weekdays:
        is_trading_day = False

    candidates: list[tuple[time, str]] = []
    if is_trading_day:
        candidates.append((market_open, "market open (6:30 AM)"))
    if first_class:
        candidates.append((first_class, f"{tomorrow_classes[0].name} class"))

    if candidates:
        next_obligation, obligation_label = min(candidates, key=lambda x: x[0])
    else:
        # No hard obligations - assume reasonable wake around 10 AM
        next_obligation = time(10, 0)
        obligation_label = "no fixed obligations (default 10 AM)"

    # Calculate sleep hours (bedtime may be after midnight)
    sleep_min = _minutes_between(bedtime, next_obligation)
    sleep_hours = sleep_min / 60.0

    # Trading recommendation
    if sleep_hours < SLEEP_SKIP_TRADE_THRESHOLD:
        skip_trading = True
        trading_reason = (
            f"Only {sleep_hours:.1f}h before market open. "
            f"Trading on <{SLEEP_SKIP_TRADE_THRESHOLD}h impairs reaction time and "
            f"decision quality - the risk/reward does not justify it today."
        )
    elif sleep_hours < SLEEP_WARN_THRESHOLD:
        skip_trading = False
        trading_reason = (
            f"{sleep_hours:.1f}h is marginal. Consider paper-trading only, "
            f"keeping position sizes small, and having a hard stop-loss rule set before open."
        )
    else:
        skip_trading = False
        trading_reason = f"{sleep_hours:.1f}h - adequate for trading."

    # Nap slots: 25-min windows in 12:30-3 PM range, avoiding classes
    nap_slots: list[tuple[time, time]] = []
    nap_window_start = time(12, 30)
    nap_window_end   = time(15, 0)
    candidate_nap    = nap_window_start

    while _minutes_between(candidate_nap, nap_window_end) >= NAP_DURATION_MINUTES:
        nap_end = _add_minutes(candidate_nap, NAP_DURATION_MINUTES)
        # Check collision with any class
        collision = False
        for c in tomorrow_classes:
            if c.start < nap_end and candidate_nap < c.end:
                collision = True
                candidate_nap = c.end
                break
        if not collision:
            nap_slots.append((candidate_nap, nap_end))
            break  # one recommended nap is enough; user can pick

    return SleepAnalysis(
        bedtime=bedtime,
        next_obligation=next_obligation,
        obligation_label=obligation_label,
        sleep_hours=sleep_hours,
        skip_trading=skip_trading,
        trading_reason=trading_reason,
        nap_slots=nap_slots,
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _add_minutes(t: time, minutes: int) -> time:
    dt = datetime.combine(date.today(), t) + timedelta(minutes=minutes)
    return dt.time()


def _minutes_between(a: time, b: time) -> int:
    """Minutes from a to b (b may be next day if b < a)."""
    da = datetime.combine(date.today(), a)
    db = datetime.combine(date.today(), b)
    if db < da:
        db += timedelta(days=1)
    return max(0, int((db - da).total_seconds() / 60))


DAY_ABBRS = {
    "monday":    "Mon",
    "tuesday":   "Tue",
    "wednesday": "Wed",
    "thursday":  "Thu",
    "friday":    "Fri",
    "saturday":  "Sat",
    "sunday":    "Sun",
}


def current_day_abbr() -> str:
    return datetime.now().strftime("%a")


def parse_time(s: str) -> time:
    """Parse a time string like '6:30', '630', '6:30am', '18:00'."""
    s = s.strip().lower().replace(" ", "")
    am_pm = None
    if s.endswith("am"):
        am_pm = "am"
        s = s[:-2]
    elif s.endswith("pm"):
        am_pm = "pm"
        s = s[:-2]

    if ":" in s:
        h, m = s.split(":")
    elif len(s) == 4:
        h, m = s[:2], s[2:]
    elif len(s) <= 2:
        h, m = s, "0"
    else:
        raise ValueError(f"Cannot parse time: {s!r}")

    h, m = int(h), int(m)
    if am_pm == "pm" and h != 12:
        h += 12
    elif am_pm == "am" and h == 12:
        h = 0

    return time(h, m)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

# Priority windows for flexible blocks (hour, hour)
GYM_WINDOW     = (time(10, 0), time(15, 0))
TRAIN_WINDOW   = (time(8, 0),  time(13, 0))
INTERN_WINDOW  = (time(13, 0), time(17, 0))

class DayScheduler:
    """
    Builds an optimized daily schedule given wake time, day of week, and profile.
    Uses a greedy slot-filling approach with hard constraints for fixed events
    (classes, market hours) and soft-priority placement for flexible activities.
    """

    def __init__(
        self,
        wake_time: time,
        day_of_week: str,
        profile: UserProfile,
        rock_climbing: bool = False,
        target_sleep: Optional[time] = None,
        sleep_deprived: bool = False,
        place_nap: bool = False,
    ):
        self.wake           = wake_time
        self.dow            = day_of_week
        self.p              = profile
        self.rock_climbing  = rock_climbing
        self.target_sleep   = target_sleep or profile.preferred_sleep_time
        self.sleep_deprived = sleep_deprived   # affects warnings in output
        self.place_nap      = place_nap        # insert a recovery nap block
        self.blocks: list[TimeBlock] = []
        self._cursor: time  = wake_time

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> list[TimeBlock]:
        self.blocks   = []
        self._cursor  = self.wake

        # Step 1: Fixed hard constraints - classes (placed first so everything else avoids them)
        self._place_classes()

        # Step 2: Market (fixed time window)
        if self.p.day_trade:
            self._place_market_block()

        # Step 3: Triathlon training - prefer morning slots
        self._place_triathlon()

        # Step 4: Gym - prefer midday
        self._place_gym()

        # Step 5: Meals
        self._ensure_meal("Lunch", target_hour=12, duration=40)
        self._ensure_meal("Dinner", target_hour=18, duration=40)

        # Step 6: Recovery nap (if sleep-deprived and user chose to trade anyway)
        if self.place_nap:
            self._place_nap()

        # Step 7: Internship block
        self._place_internship()

        # Step 8: Wind-down + sleep
        self._place_sleep()

        # Step 9: Fill remaining gaps
        self._fill_free_time()

        self.blocks.sort(key=lambda b: b.start)
        return self.blocks

    # ------------------------------------------------------------------
    # Placement helpers
    # ------------------------------------------------------------------

    def _insert_at(
        self,
        start: time,
        block_type: BlockType,
        label: str,
        duration: int,
        notes: str = "",
        optional: bool = False,
    ) -> Optional[TimeBlock]:
        """Insert a block at a specific start time (ignores cursor, used for fixed events)."""
        end = _add_minutes(start, duration)
        block = TimeBlock(start, end, block_type, label, notes=notes, optional=optional)
        self.blocks.append(block)
        return block

    def _find_free_slot(self, duration: int, not_before: time, not_after: Optional[time] = None) -> Optional[time]:
        """
        Find the earliest free gap of at least `duration` minutes
        starting at or after `not_before` (never before wake time),
        stopping before `not_after` (default: target_sleep).
        """
        ceiling = not_after or self.target_sleep
        candidate = not_before if not_before >= self.wake else self.wake
        sorted_blocks = sorted(self.blocks, key=lambda b: b.start)

        for _ in range(200):  # safety limit
            if candidate >= ceiling:
                return None
            candidate_end = _add_minutes(candidate, duration)
            collision = None
            for b in sorted_blocks:
                if b.start < candidate_end and candidate < b.end:
                    collision = b
                    break
            if collision is None:
                if candidate_end <= ceiling or candidate_end <= _add_minutes(ceiling, 30):
                    return candidate
                return None
            # Jump past the collision
            candidate = collision.end

        return None

    def _place_classes(self) -> None:
        """Hard-constraint: insert all classes for today."""
        today_classes = [c for c in self.p.classes if self.dow in c.days]
        today_classes.sort(key=lambda c: c.start)
        for c in today_classes:
            self._insert_at(
                c.start, BlockType.CLASS, c.name, _minutes_between(c.start, c.end),
                notes=c.location,
            )

    def _place_market_block(self) -> None:
        """
        Market opens 9:30 ET = 6:30 AM PST.
        Pre-market: 6:00-6:30. Active trading: 6:30-8:00 (most volatile 90 min).
        Adapts based on wake time.
        """
        premarket = time(6, 0)
        mkt_open  = time(6, 30)
        mkt_end   = time(8, 0)

        if self.wake <= premarket:
            slot = self._find_free_slot(30, premarket, mkt_open)
            if slot:
                self._insert_at(slot, BlockType.MARKET, "Pre-market prep", 30,
                                notes="Scan watchlist, check overnight news")
            slot2 = self._find_free_slot(90, mkt_open, mkt_end)
            if slot2:
                self._insert_at(slot2, BlockType.MARKET, "Market open (active trading)", 90,
                                notes="First 90 min: highest volatility window")
        elif self.wake <= mkt_open:
            slot = self._find_free_slot(90, mkt_open, mkt_end)
            if slot:
                self._insert_at(slot, BlockType.MARKET, "Market open (active trading)", 90,
                                notes="First 90 min: highest volatility window")
        elif self.wake < mkt_end:
            remaining = _minutes_between(self.wake, mkt_end)
            if remaining >= 20:
                slot = self._find_free_slot(remaining, self.wake, mkt_end)
                if slot:
                    self._insert_at(slot, BlockType.MARKET, "Market session (late start)",
                                    remaining, notes="Reduced window today")

    def _place_triathlon(self) -> None:
        """Place swim and/or run blocks for triathlon training."""
        do_swim = self.dow in self.p.swim_days
        do_run  = self.dow in self.p.run_days
        if not do_swim and not do_run:
            return

        # Prefer post-market morning window (8 AM - noon) for training
        train_start = time(8, 0)

        if do_swim:
            slot = self._find_free_slot(self.p.swim_duration + 10, train_start, time(13, 0))
            if slot is None:
                slot = self._find_free_slot(self.p.swim_duration + 10, train_start)
            if slot:
                self._insert_at(slot, BlockType.SWIM, "Swim training",
                                self.p.swim_duration, notes="Triathlon prep - endurance sets")
                self._insert_at(_add_minutes(slot, self.p.swim_duration),
                                BlockType.BUFFER, "Post-swim change", 10)

        if do_run:
            # Run after swim if both today; otherwise same window
            run_earliest = time(8, 0)
            slot = self._find_free_slot(self.p.run_duration, run_earliest, time(14, 0))
            if slot is None:
                slot = self._find_free_slot(self.p.run_duration, run_earliest)
            if slot:
                self._insert_at(slot, BlockType.RUN, "Run training",
                                self.p.run_duration, notes="Triathlon prep - aerobic base")

    def _place_gym(self) -> None:
        """Place gym block on gym days."""
        if self.dow not in self.p.gym_days:
            return

        workout = GYM_ROTATION[self.p.gym_rotation_index]
        is_back = self.p.gym_rotation_index == 0
        if is_back and self.rock_climbing:
            label = "Rock Climbing"
            notes = "Substituting back day with climbing"
        else:
            label = f"Gym: {workout}"
            notes = GYM_ROTATION_SHORT[self.p.gym_rotation_index]

        # Prefer 10 AM - 3 PM midday window
        slot = self._find_free_slot(self.p.gym_duration + 15, time(10, 0), time(15, 0))
        if slot is None:
            slot = self._find_free_slot(self.p.gym_duration + 15, time(8, 0))
        if slot:
            self._insert_at(slot, BlockType.GYM, label, self.p.gym_duration, notes=notes)
            self._insert_at(_add_minutes(slot, self.p.gym_duration),
                            BlockType.BUFFER, "Post-gym", 15,
                            notes="Shower, protein shake")

    def _ensure_meal(self, name: str, target_hour: int, duration: int) -> None:
        """Place a meal near the target hour if none exists in a 2-hr window."""
        window_start = time(max(0, target_hour - 1), 0)
        window_end   = time(min(23, target_hour + 2), 0)

        for b in self.blocks:
            if b.block_type == BlockType.MEAL and window_start <= b.start < window_end:
                return

        slot = self._find_free_slot(duration, window_start, window_end)
        if slot is None:
            slot = self._find_free_slot(duration, window_start)
        if slot and slot < time(21, 0):
            self._insert_at(slot, BlockType.MEAL, name, duration)

    def _place_internship(self) -> None:
        """Place internship applications block on weekdays."""
        if self.dow not in self.p.internship_days:
            return
        # Prefer 1-5 PM afternoon window
        slot = self._find_free_slot(self.p.internship_block, time(13, 0), time(17, 0))
        if slot is None:
            slot = self._find_free_slot(self.p.internship_block, time(10, 0), time(19, 0))
        if slot:
            self._insert_at(slot, BlockType.INTERNSHIP, "Internship applications",
                            self.p.internship_block,
                            notes="Job boards, tailoring resumes, networking outreach")

    def _place_nap(self) -> None:
        """
        Place a 25-min recovery nap in the post-lunch window (12:30-3 PM).
        Science note: 20-25 min avoids slow-wave sleep and the grogginess (sleep inertia)
        that comes with longer naps. Post-lunch is optimal due to natural circadian dip.
        """
        slot = self._find_free_slot(NAP_DURATION_MINUTES, time(12, 30), time(15, 0))
        if slot is None:
            # Fall back to any afternoon slot
            slot = self._find_free_slot(NAP_DURATION_MINUTES, time(12, 0), time(16, 0))
        if slot:
            self._insert_at(
                slot, BlockType.NAP, "Recovery nap", NAP_DURATION_MINUTES,
                notes="25 min max - set an alarm to avoid sleep inertia",
            )

    def _place_sleep(self) -> None:
        """Place wind-down and sleep."""
        wind_start = _add_minutes(self.target_sleep, -30)
        # Only add wind-down if slot is free
        slot = self._find_free_slot(30, wind_start, self.target_sleep)
        if slot and slot >= wind_start:
            self._insert_at(wind_start, BlockType.WIND_DOWN, "Wind-down", 30,
                            notes="No screens, light reading, prep for tomorrow")
        self._insert_at(self.target_sleep, BlockType.SLEEP, "Sleep",
                        int(self.p.target_sleep_hours * 60),
                        notes=f"Target: {self.p.target_sleep_hours:.1f}h")

    def _fill_free_time(self) -> None:
        """Find all gaps >= 15 min and label them as free time."""
        sorted_blocks = sorted(self.blocks, key=lambda b: b.start)
        gaps: list[tuple[time, time]] = []

        cursor = self.wake
        for b in sorted_blocks:
            if b.start > cursor:
                gap_min = _minutes_between(cursor, b.start)
                if gap_min >= 15:
                    gaps.append((cursor, b.start))
            if b.end > cursor:
                cursor = b.end

        for start, end in gaps:
            dur = _minutes_between(start, end)
            label = "Study / deep work / relax" if dur >= 60 else "Free time"
            self.blocks.append(
                TimeBlock(start, end, BlockType.FREE, label, optional=True)
            )
