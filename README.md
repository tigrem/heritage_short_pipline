# Ato Girma's Promise

An Amharic heritage short with English subtitles, generated from a validated
10-shot storyboard. The current storyboard totals 85.36 seconds and contains
the four approved references in `assets/refs/`: `eden.jpeg`, `girma.png`,
`living_room.jpg`, and `story_telling_area.jpg`.

## Setup

1. Install Python 3.11 or newer and FFmpeg-capable dependencies from
   `requirements.txt`:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Create a local `.env` file with `GEMINI_API_KEY` for uncached narration
   generation and Cloudflare account credentials for uncached keyframe
   generation. Do not commit `.env`. By default, keyframes use
   image-conditioned generation from each shot's original character and room
   images as separate references. Prompts preserve identity, wardrobe, hair,
   body build, and the approved room while adapting pose, gesture, and
   expression to the shot. Generated details can still vary and must be reviewed.

Set `KEYFRAME_MODE=reference_locked` to compose the exact original character
and location images for every shot. This mode preserves their original poses
and does not adapt gestures or expressions.
`KEYFRAME_MODE=ai` is available only for experimental text-to-image generation
and may drift from the references.

## Run

Validate the storyboard:

```powershell
.\.venv\Scripts\python.exe -m pipeline.validate
```

Run the documented end-to-end pipeline:

```powershell
.\.venv\Scripts\python.exe -m pipeline.run --stage all
```

For the early radio cut, run:

```powershell
.\.venv\Scripts\python.exe -m pipeline.run --stage radio
```

To select one shot and reuse unchanged cached work:

```powershell
.\.venv\Scripts\python.exe -m pipeline.run --stage all --shot shot_08
```

The pipeline writes narration, keyframes, shot renders, music, subtitles, and
final 16:9 and 9:16 MP4s under `outputs/`. Runtime logs are appended to
`logs/runs.jsonl`; both directories and `.env` are Git-ignored. Summarize
logged work with `python -m pipeline.summarize_logs`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for stage behavior, caching, and the
visual-consistency tradeoffs.
