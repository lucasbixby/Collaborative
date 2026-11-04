# Sync latency (#24)

Success criterion: **under 200 ms on a local network.**

**Status:** on one machine, every scenario is well under 200 ms: the worst p95 is 92.6 ms and the
worst single sample 106.9 ms. **The criterion itself isn't met yet, because the real-network run
(scenario 5) hasn't been done.** The steps are below. The expected network cost is small next to the
margin, but that's an expectation, not a measurement.

## What's measured

End to end runs from the moment Blender reports the change on A (the first depsgraph handler call
that marks the scene dirty since the last flush) to the moment B's add-on has set the value in its
scene.

| Stage | From → to | What it is |
|---|---|---|
| Detect wait | `noticed` → `flush_start` | Waiting for the 50 ms detect tick |
| Diff + serialize | `flush_start` → `queued` | Comparing the scene with the cache, building the message |
| Writer wait | `queued` → `dequeued` | The writer thread sleeps `DRAIN_INTERVAL` when its outbox is empty |
| Socket send | `dequeued` → `sent` | |
| Uplink | `sent` → `server_received` | Network, and the server's event loop getting to it |
| Server: validate | `server_received` → `server_parsed` | Size, schema and origin checks |
| Server: persist | `server_parsed` → `server_persisted` | SQLite commit |
| Fan-out + downlink | `server_persisted` → `received` | Re-serializing, sending, network |
| Drain wait | `received` → `drained` | Waiting for the 20 ms drain tick |
| Parse + apply | `drained` → `applied` | JSON parse, then the setter or mesh build |

**Three timers, not two.** The detect tick (50 ms) and drain tick (20 ms) were expected. The third is
the writer thread's idle sleep, also `DRAIN_INTERVAL`.

**Not included:** the time before the depsgraph handler runs (input handling, evaluation) and
everything after the draw, such as the display's own refresh. `applied` isn't the same as visible, so
the driver also logs viewport draws, and "applied → next draw" appears as an extra row outside this
definition.

## Method

- **Timing is out of band.** The schema forbids extra fields, so each process appends JSONL lines keyed
  by (`origin`, `lamport`, `object`), and `scripts/latency_report.py` joins them afterwards. Enable it
  with `COLLAB_TIMING=<file>` on the add-on or server.
- **Cost.** Off: no clock reads and no file, about 50 ns per mark. On: about 160 ns per mark
  (server's Python, `timeit`), appending to a list; a background thread writes the file once a second.
- **Clock.** `time.perf_counter_ns()`. On this Mac it's one clock across processes: `wall − mono`
  differed by 36 µs between Blender's Python and the server's. The report warns about negative stages.
- **Real Blender.** Two Blender GUI windows, with the add-on running on Blender's own timers, driven by
  `scripts/latency_blender.py`, with `scripts/latency_run.py` starting everything. Throwaway settings, and
  a temporary database. Edits go through real operators, not direct property writes.
- **Percentiles** are nearest-rank, so each is a real sample. The first 2 s of each run are dropped as
  warmup (1 s for `create`, which only drops the small setup cube).

**Environment:** Apple M2, 8 cores, 8 GB, on AC power, macOS 15.7.3, Blender 5.2.2 LTS,
server on Python 3.12 with SQLite, loopback only. Not otherwise idle: Docker Desktop was running, and
the load average was 4.3 at the start. Windows at the default size, in solid shading.

## Results: one machine (shared clock)

| Scenario | n | p50 ms | p95 ms | p99 ms | max ms | Timers' share of the mean | Applied → draw, p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. Idle, single nudges | 214 | 58.0 | 89.1 | 94.3 | 98.7 | 97% | 1.6 |
| 1. Idle, repeat run | 214 | 57.3 | 92.3 | 100.0 | 106.9 | 97% | 1.6 |
| 1b. Idle, 500 extra objects per scene | 214 | 53.3 | 80.2 | 87.3 | 91.1 | 93% | 6.3 |
| 2. Sustained drag, 3 grabs of about 10 s | 515 | 76.2 | 92.6 | 100.8 | 105.4 | 97% | 1.8 |
| 3. `create` of about 62 KB | 59 | 61.5 | 82.0 | 97.0 | 97.0 | 72% | 3.1 |
| 4. Nudges with 4 simulated clients (80 msg/s) | 220 | 48.9 | 73.7 | 86.3 | 105.8 | 96% | 1.8 |
| 4. Nudges with 8 simulated clients (160 msg/s) | 220 | 47.9 | 73.0 | 77.9 | 80.7 | 97% | 2.2 |

Every sent operation was applied in every run. **Verdict on this machine: under 200 ms in all of them,
with about 100 ms to spare at p99.**

### Where the time goes (p50 ms, p95 in brackets)

| Stage | Idle | Drag | `create` | 8 clients |
|---|---:|---:|---:|---:|
| Detect wait | 37.0 (61.2) | 50.5 (56.4) | 23.8 (46.2) | 26.2 (29.4) |
| Diff + serialize | 0.1 (0.1) | 0.1 (0.1) | 4.6 (5.0) | 0.1 (0.2) |
| Writer wait | 11.0 (23.4) | 11.7 (26.4) | 13.2 (25.3) | 11.3 (24.4) |
| Socket send | 0.1 (0.2) | 0.1 (0.2) | 0.2 (1.3) | 0.1 (0.2) |
| Uplink | 0.1 (0.2) | 0.2 (0.3) | 0.2 (0.4) | 0.1 (0.3) |
| Server: validate | 0.0 (0.1) | 0.1 (0.1) | 0.8 (1.8) | 0.0 (0.1) |
| Server: persist | 1.0 (1.6) | 1.4 (2.2) | 1.3 (3.4) | 0.8 (2.5) |
| Fan-out + downlink | 0.1 (0.3) | 0.2 (0.3) | 6.2 (7.2) | 0.2 (0.5) |
| Drain wait | 8.0 (19.1) | 12.6 (21.8) | 3.4 (12.7) | 12.9 (25.3) |
| Parse + apply | 0.1 (0.1) | 0.1 (0.2) | 1.9 (2.3) | 0.0 (0.2) |

Stage percentiles don't add up to the end-to-end percentile, since each is ranked on its own.

### What this shows

- **The timers are the latency, as expected.** Everything from `sent` to `received`, including the
  database write, averages 1.5 ms in the idle run. The write before broadcast (D-070) costs about 1 ms.
- **Nothing backs up.** During the drag the client sends about 18 messages/s, and the writer's wait
  stays under 30 ms through all three grabs. With 8 clients the p95 stays between 65 and 75 ms over the
  whole 77 s run. The server wasn't pushed to its limit: 160 msg/s isn't a capacity figure.
- **A drag reads higher because of the definition.** `noticed` is the *oldest* change in a batch, and
  while dragging the scene goes dirty right after each flush, so the detect wait is close to a full
  tick. The newest change in that batch waits much less.
- **A big `create` costs about 15 ms of real work,** in serializing (4.6 ms on A's main thread), server
  validation, re-serializing and the mesh build (1.9 ms on B's main thread). One sample had 19.9 ms in
  validation and another 12.1 ms in persist. Size is capped at 64 KiB, so this can't grow further (#27).

### Not explained

In an idle, near-empty scene the detect wait reaches 62 to 67 ms, longer than the 50 ms tick, and it
did so in both runs. With 500 objects or a `create` it stays under 50 ms, and with simulated clients
the p95 is around 30 ms, narrower than a 50 ms tick should give. So the tick isn't evenly phased with
Blender's main loop, and how busy that loop is seems to matter. I didn't investigate further, since
it doesn't threaten the criterion.

## Scenario 5: over the LAN (not run yet)

Clocks on two machines don't agree, so this uses a round trip, measured on one clock: Blender A's
`noticed` → the probe's reply `applied` in A. The probe replies at the next Lamport time, and that's how
the report pairs them.

**RTT/2 understates this system.** The probe answers instantly, so a round trip skips a receiving
Blender's timers. On one machine, RTT/2 is 26.2 ms at p50, against a real end to end of 58 ms. So
report two numbers:
- **RTT/2**, assuming both directions take the same time.
- **Estimated LAN end to end** = scenario 1's p95 + (LAN RTT p95 − same-machine RTT p95) / 2. Timers
  don't change with distance, so the difference between the two round trips is what the network adds.
  Adding p95s is an approximation.

Same-machine control, through the LAN IP from the probe to the server:

| | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|---:|
| Round trip | 115 | 52.3 | 78.4 | 91.9 | 98.4 |
| Round trip / 2 | 115 | 26.2 | 39.2 | 45.9 | 49.2 |

**Steps** (machine 1 runs the server and Blender; machine 2 only needs Python):

1. Machine 1: `ipconfig getifaddr en0` gives its IP. Allow incoming connections if the firewall asks.
2. Machine 1, from the repo root: `scripts/latency_run.py rtt --name rtt-lan --host 0.0.0.0`
3. When it prompts, on machine 2, with `scripts/latency_probe.py` copied over:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install websockets
   .venv/bin/python latency_probe.py latency --url ws://<machine-1-ip>:8000
   ```
4. Once machine 2 says `Connected`, press Enter on machine 1. It takes about 80 s. Don't touch Blender.
5. Machine 1: `scripts/latency_report.py latency-results/rtt-lan --rtt`
6. Paste the table here, with whether it was Wi-Fi or Ethernet, then compute the estimate above.

## Scenario 6: Docker (follow-up)

Waiting on #23's merge. Compose would need to pass `COLLAB_TIMING` through to a file on the volume. On
Docker Desktop the server runs on the VM's clock, so its stages only compare with each other: use
`latency_report.py --separate-server-clock`. End to end stays valid, because both Blenders are on the Mac.
`scripts/latency_run.py idle --url ws://localhost:8000 --name docker` runs the scenario.

## Caveats

- **Simulated drag.** A real modal transform moved by simulated mouse events at about 60 Hz, not a hand.
  To do it by hand: `scripts/latency_run.py drag --manual --name drag-hand`, then
  `scripts/latency_report.py latency-results/drag-hand --timeline 5`.
- **Small scenes.** Apart from 1b, a scene is one cube plus simulated objects. 1b adds empty meshes, so
  500 objects costs 2 ms in the diff (it's linear in the number of objects), but says nothing about heavy
  geometry in the viewport.
- **Sample sizes.** With n around 214, p99 rests on 2 or 3 samples, and with n = 59 it's nearly the
  maximum. Treat those as rough. Medians and p95s moved by about 3 ms between the two idle runs.
- **One Mac, loopback.** Both Blenders and the server share 8 cores and one GPU. A real network adds
  delay but removes that contention.
- **One direction.** All samples are A → B, with B idle, apart from drawing.

## If this ever needs to be faster

Not proposed for now, as nothing misses the target. `INTERVAL` and `DRAIN_INTERVAL` are unchanged (D-019).
The cheapest gain is the writer's wait: waking the thread with a `threading.Event` when something is queued,
rather than polling, would remove about 11 ms at p50 and 25 ms at worst, and would use less CPU, not more.
