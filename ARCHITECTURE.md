# Pipeline architecture

## Storyboard contract

`storyboard.json` is checked against `schema/storyboard.schema.json` before
pipeline execution. It contains the title and language metadata, declared
`total_duration_sec`, and ten sequential shots (`shot_01` through `shot_10`).
Each shot defines its type, positive duration, visual/keyframe/motion prompts,
music cue, deterministic seed, Amharic narration, English subtitle, refs, and
location anchor. A shot may reference no more than three approved files from
`assets/refs/`; `location_anchor` is one approved filename or `null`.

The validator also checks that the duration sum matches the declared total and
is within 60–90 seconds. The current storyboard totals 85.36 seconds.

## Stage flow

`python -m pipeline.run --stage all` validates first, then runs:

1. **narration** — generate or reuse one Amharic WAV per shot.
2. **keyframes** — describe only the shot's listed reference images, add
   filename-specific visual anchors, then generate and quality-check its PNG.
3. **shots** — render cached 16:9 and 9:16 variants with contained foreground
   imagery, blurred backgrounds, and subtle motion.
4. **music** — create or reuse an instrumental score matching the film length.
5. **assemble** — regenerate the English SRT, mix ducked music with narration,
   normalize loudness, burn in subtitles, retain a selectable subtitle track,
   and export both final aspect ratios with the AI disclosure end card.

`--stage radio` runs narration and produces the early radio cut. Individual
stages are available for targeted work. With `--stage all --shot shot_08`, only
that shot's narration/keyframe/shot outputs are checked or generated; changed
inputs invalidate only dependent stages, while final assembly updates both
aspect ratios.

## SHA-256 caching

`pipeline/cache.py` canonicalizes stage, shot ID, settings, prompt values, and
the SHA-256 digest of every file input. Cache entries live under
`outputs/cache/`, which is ignored by Git. Landscape and portrait clips use
separate stage keys. A cache entry is reused only when its input hash and
recorded output digest match. The log summarizer distinguishes cache-hit events
from actual model/tool executions; its current cache-entry total is a snapshot,
not a count of historical hits.

## Retries and failures

`pipeline/retry.py` retries transient network/service errors using exponential
backoff and jitter. Stage wrappers log each attempt. Permanent errors (for
example a provider's daily quota rejection) are surfaced rather than silently
retried. Invalid keyframe images are retried; exhausted image-quality failures
are recorded in `FAILURES.md` as well as the run log.

## Run log schema

`logs/runs.jsonl` is append-only UTF-8 JSON Lines. Every record has:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC ISO-8601 time |
| `stage` | Stage or substage name |
| `shot_id` | Shot ID, `film`, or `null` for a film-wide action |
| `model` | Model/tool name; `sha256-cache` marks reuse events |
| `seed` | Shot seed or `null` |
| `latency_sec` | Attempt latency; cache-hit records use zero |
| `status` | `success`, `retrying`, `failure`, or `cache_hit` |
| `error` | Error detail or `null` |
| `est_gpu_minutes` | Optional estimate; currently many local/provider calls leave it `null` |

Run `python -m pipeline.summarize_logs` for counts by stage/status, latency,
logged cache hits versus executions, current cache-entry count, and any recorded
GPU-minute estimates. It also supports `--json` and `--log-file PATH`.
