#!/usr/bin/env python3
"""Join the timing files from COLLAB_TIMING (#24) and print latency tables as Markdown.

    scripts/latency_report.py latency-results/idle latency-results/drag
    scripts/latency_report.py latency-results/create --kind create
    scripts/latency_report.py latency-results/drag --timeline 2
    scripts/latency_report.py latency-results/lan --rtt
    scripts/latency_report.py latency-results/docker --separate-server-clock

Each folder is one scenario, holding one .jsonl file per process. Stdlib only. Times from different
processes are only compared on the assumption that they share a clock, so that's one machine:
across machines use --rtt, which only reads one client's own clock.
"""

import argparse
import bisect
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# (label, from stage, to stage). They add up to the whole of end to end.
STAGES = (
    ("detect wait (50 ms tick)", "noticed", "flush_start"),
    ("diff + serialize", "flush_start", "queued"),
    ("writer wait (20 ms poll)", "queued", "dequeued"),
    ("socket send", "dequeued", "sent"),
    ("uplink", "sent", "server_received"),
    ("server: validate", "server_received", "server_parsed"),
    ("server: persist", "server_parsed", "server_persisted"),
    ("fan-out + downlink", "server_persisted", "received"),
    ("drain wait (20 ms tick)", "received", "drained"),
    ("parse + apply", "drained", "applied"),
)
# These stages cross between the server's clock and a client's.
CROSS_CLOCK_STAGES = {"uplink", "fan-out + downlink"}
CLOCK_SKEW_WARNING_NS = 1_000_000

Key = tuple[str, int, str]


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile: the smallest value with at least `percent`% of values at or below
    it. Always a real sample, and it never interpolates past what was measured."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
    }


@dataclass
class Timings:
    """Every recorded time: by key, then process, then stage (the first time wins, because a
    client's send retry can repeat one). Plus each process's viewport draws, if recorded."""

    by_key: dict[Key, dict[str, dict[str, int]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(dict))
    )
    kinds: dict[Key, str] = field(default_factory=dict)
    draws: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))


def load(folder: Path) -> Timings:
    timings = Timings()
    for path in sorted(folder.glob("*.jsonl")):
        with path.open(encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                if record["stage"] == "draw":
                    timings.draws[record["source"]].append(record["mono_ns"])
                    continue
                key = (record["origin"], record["lamport"], record["object"])
                timings.kinds[key] = record["kind"]
                timings.by_key[key][record["source"]].setdefault(record["stage"], record["mono_ns"])
    for draws in timings.draws.values():
        draws.sort()
    return timings


@dataclass
class Sample:
    key: Key
    sender: str
    receiver: str
    times: dict[str, int]  # the sender's, the server's and the receiver's stages together

    @property
    def end_to_end_ns(self) -> int:
        return self.times["applied"] - self.times["noticed"]


def _sender_of(sources: dict[str, dict[str, int]]) -> str | None:
    return next((source for source, stages in sources.items() if "noticed" in stages), None)


def samples(timings: Timings, kind: str | None = None) -> tuple[list[Sample], int]:
    """One sample per (operation, receiver) that was applied, and how many operations noticed by a
    client were never applied by anyone. Ops with no `noticed` come from simulated clients."""
    found: list[Sample] = []
    unapplied = 0
    for key, sources in timings.by_key.items():
        sender = _sender_of(sources)
        if sender is None or (kind and timings.kinds[key] != kind):
            continue
        receivers = [s for s, stages in sources.items() if s != sender and "applied" in stages]
        unapplied += not receivers
        for receiver in receivers:
            times = {**sources[sender], **sources.get("server", {}), **sources[receiver]}
            found.append(Sample(key, sender, receiver, times))
    found.sort(key=lambda sample: sample.times["noticed"])
    return found, unapplied


def drop_warmup(found: list[Sample], seconds: float) -> list[Sample]:
    if not found:
        return []
    cutoff = found[0].times["noticed"] + seconds * 1e9
    return [sample for sample in found if sample.times["noticed"] >= cutoff]


def stage_durations(found: list[Sample]) -> dict[str, list[float]]:
    """Each stage's durations in ms, skipping samples missing either end."""
    durations: dict[str, list[float]] = {}
    for label, start, end in STAGES:
        durations[label] = [
            (sample.times[end] - sample.times[start]) / 1e6
            for sample in found
            if start in sample.times and end in sample.times
        ]
    return durations


def draw_delays(found: list[Sample], timings: Timings) -> list[float]:
    """ms from `applied` to the receiver's next viewport draw."""
    delays = []
    for sample in found:
        draws = timings.draws.get(sample.receiver)
        if not draws:
            continue
        index = bisect.bisect_left(draws, sample.times["applied"])
        if index < len(draws):
            delays.append((draws[index] - sample.times["applied"]) / 1e6)
    return delays


def round_trips(timings: Timings) -> list[float]:
    """Round-trip times in ms, from one client's clock only: this client's `noticed` for an
    operation, to its `applied` for the probe's reply, which is by convention the same object at
    the next Lamport time from another origin (scripts/latency_probe.py)."""
    replies: dict[tuple[int, str], list[tuple[str, dict]]] = defaultdict(list)
    for (origin, lamport, obj), sources in timings.by_key.items():
        replies[(lamport, obj)].append((origin, sources))

    trips = []
    for (origin, lamport, obj), sources in timings.by_key.items():
        for source, stages in sources.items():
            if "noticed" not in stages:
                continue
            for reply_origin, reply_sources in replies.get((lamport + 1, obj), []):
                applied = reply_sources.get(source, {}).get("applied")
                if reply_origin != origin and applied is not None:
                    trips.append((applied - stages["noticed"]) / 1e6)
    return trips


def _row(label: str, values: list[float]) -> str:
    if not values:
        return f"| {label} | 0 | | | | |"
    stats = summarize(values)
    return (
        f"| {label} | {stats['n']} | {stats['p50']:.1f} | {stats['p95']:.1f} "
        f"| {stats['p99']:.1f} | {stats['max']:.1f} |"
    )


HEADER = "| | n | p50 ms | p95 ms | p99 ms | max ms |\n|---|---:|---:|---:|---:|---:|"


def report(folder: Path, args: argparse.Namespace) -> None:
    timings = load(folder)
    print(f"### {folder.name}\n")

    if args.rtt:
        trips = round_trips(timings)[args.warmup_samples :]
        print(HEADER)
        print(_row("round trip", trips))
        print(_row("round trip / 2", [trip / 2 for trip in trips]))
        print()
        return

    found, unapplied = samples(timings, args.kind)
    found = drop_warmup(found, args.warmup)
    end_to_end = [sample.end_to_end_ns / 1e6 for sample in found]
    print(HEADER)
    print(_row("**end to end**", end_to_end))
    print(_row("*extra: applied → next draw*", draw_delays(found, timings)))
    print()
    print(f"Never applied by anyone (whole run, including warmup): {unapplied}.\n")

    print(HEADER)
    durations = stage_durations(found)
    for label, values in durations.items():
        if args.separate_server_clock and label in CROSS_CLOCK_STAGES:
            print(f"| {label} | not comparable: separate clocks | | | | |")
        else:
            print(_row(label, values))
    print()

    skewed = [
        label
        for label, values in durations.items()
        if values
        and min(values) < -CLOCK_SKEW_WARNING_NS / 1e6
        and not (args.separate_server_clock and label in CROSS_CLOCK_STAGES)
    ]
    if skewed:
        print(f"**Warning:** negative durations in {skewed}: are these clocks really shared?\n")

    if args.timeline and found:
        print("| from start (s) | ops | p50 ms | p95 ms | max ms | writer wait max ms |")
        print("|---:|---:|---:|---:|---:|---:|")
        start = found[0].times["noticed"]
        buckets: dict[int, list[Sample]] = defaultdict(list)
        for sample in found:
            buckets[int((sample.times["noticed"] - start) / 1e9 // args.timeline)].append(sample)
        for index in sorted(buckets):
            values = [sample.end_to_end_ns / 1e6 for sample in buckets[index]]
            waits = [
                (sample.times["dequeued"] - sample.times["queued"]) / 1e6
                for sample in buckets[index]
            ]
            print(
                f"| {index * args.timeline:g} | {len(values)} | {percentile(values, 50):.1f} "
                f"| {percentile(values, 95):.1f} | {max(values):.1f} | {max(waits):.1f} |"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Join timing files and print latency tables.")
    parser.add_argument("folders", nargs="+", type=Path, help="one folder per scenario")
    parser.add_argument("--warmup", type=float, default=2.0, help="seconds to drop from the start")
    parser.add_argument("--kind", choices=["set", "create", "delete"], help="only this kind of op")
    parser.add_argument("--timeline", type=float, help="also break down by this many seconds")
    parser.add_argument("--rtt", action="store_true", help="round trips against latency_probe.py")
    parser.add_argument("--warmup-samples", type=int, default=5, help="round trips to drop (--rtt)")
    parser.add_argument(
        "--separate-server-clock",
        action="store_true",
        help="the server isn't on the clients' clock (Docker Desktop's VM): skip stages crossing it",
    )
    args = parser.parse_args(argv)
    for folder in args.folders:
        if not any(folder.glob("*.jsonl")):
            print(f"No .jsonl files in {folder}", file=sys.stderr)
            return 1
        report(folder, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
