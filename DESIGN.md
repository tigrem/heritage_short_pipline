# Ato Girma's Promise — Design Notes

## Audience and story intent

**Ato Girma's Promise** (የአያቴ ግርማ ቃል ኪዳን) is a short heritage drama for
young adults, families, and viewers interested in Ethiopian stories, including
diaspora audiences balancing personal ambitions with family ties.

Eden's wish to pursue her future is treated as valid, not as a rejection of her
family. Ato Girma shares the regret behind his promise without asking her to
stay. The intended takeaway is that ambition and care for loved ones can
coexist: success matters, but so do presence, kindness, forgiveness, and the
time we give one another. The film should leave viewers reflecting on which
promises they want to carry forward and which conversations they should not
put off.

## User Test 1 — Radio Cut

**Participants:** 3 audience members
**Cut reviewed:** Radio cut, approximately 84 seconds

| Viewer | Feedback |
| --- | --- |
| Young Adult / Diaspora | Eden's pushback felt relatable. Multi-line exchanges needed clear speaker attribution so the audience could follow who was speaking. |
| Elder / Heritage Drama | The grounded tone worked. Back-to-back lines would benefit from a little breathing room. |
| Short-Form / Creator | The approximately 84-second pace felt suitable. Review the visual framing in shots 8–9, especially for a short-form crop. |

### Storyboard changes recorded

- Corrected and tightened Amharic spelling and phrasing in the narration, while
  retaining speaker labels in dialogue-heavy shots; updated the corresponding
  English subtitles for clarity.
- Aligned each shot's `duration_sec` with its generated narration WAV. The
  storyboard total at the User Test 1 review was **84.43 seconds**, within both
  the 75–87-second target discussed in this review and the 60–90-second
  contract. The latest saved narration WAVs measure **85.36 seconds** in total;
  shot durations are now aligned to those files.
- Addressed the shots 8–9 framing feedback in the visual pass: shot 8 is now a
  medium close two-shot with both faces and joined hands visible, shot 9 has
  explicit character and location anchors, and both aspect ratios preserve the
  full keyframe without cropping heads. Revisit these shots with the near-final
  audience.

## User Test 2 — Near-Final Cut

**Participants:** 3 audience members
**Cut reviewed:** Near-final 16:9 and 9:16 cuts, approximately 85.36 seconds

### Viewer 1 — Young Adult / Diaspora Viewer (story & emotional arc)

> "The emotional arc lands much better now—seeing Eden in the blue dress and Ato Girma in his white shawl and patterned trim stay consistent through the conversation, especially when they sit together and talk about not putting off loved ones until tomorrow. Burning in the English subtitles makes it easy to follow every line right away."

### Viewer 2 — Elder / Heritage Drama Viewer (tone, pacing & clarity)

> "The Amharic narration is calm, clear, and respectful, and the closing AI disclosure card is very easy to read. One small polish detail: in the second shot's English subtitle, Eden:"Grandfather... is missing a space after the colon, and when one shot has two speakers back-to-back, a brief pause makes the turn feel slightly more natural."

### Viewer 3 — Short-Form / Content Creator Viewer (vertical & horizontal presentation)

> "Both the 16:9 cut and the 9:16 cut keep the characters' faces and expressions clearly framed without cutting off heads. On the vertical 9:16 cut, the blurred side bars work cleanly, though a slightly cleaner, more compact subtitle placement in the bottom safe zone will keep the center of the scene even less covered during longer lines."

### Post-test polish recorded

- Shot 2's subtitle now has an explicit space in `Eden: “Grandfather...` and a
  line break between Girma's and Eden's lines for quicker speaker attribution.
- Burned subtitle styling is smaller and closer to the bottom safe zone:
  16:9 uses font size 14 with 16-unit vertical margin; 9:16 uses font size 10
  with 18-unit vertical margin and wider usable line width. Both cuts retain
  the separate SRT and selectable English track.
- Rebuilt `outputs/subtitles.srt`, `outputs/final_16x9.mp4`, and
  `outputs/final_9x16.mp4` from the same 85.36-second storyboard.
- The request for a brief audible pause between speakers is recorded as a
  narration follow-up. This subtitle-only polish kept the existing Amharic WAVs
  and their duration alignment unchanged.

## Production pipeline

- `python -m pipeline.run --stage all` validates the storyboard, generates or
  reuses narration, reference-aware keyframes, motion shots, and a full-length
  instrumental score, then assembles the final film.
- The default keyframe model is Cloudflare Workers AI
  `@cf/black-forest-labs/flux-1-schnell`. Since Flux Schnell is text-to-image,
  listed reference images are passed to a multimodal caption model,
  `@cf/meta/llama-4-scout-17b-16e-instruct`; filename-specific character and
  location anchors are also included in each keyframe prompt. Selecting
  `@cf/stabilityai/stable-diffusion-xl-base-1.0` enables image conditioning with
  a contact sheet made only from that shot's listed refs. Both paths use
  content-based caches and image integrity checks; rejected generations are
  retried and persistent quality failures are recorded in `FAILURES.md`. The
  current Flux API rejects its documented `seed` field, so the shot seed is
  included in the prompt, cache key, and run log instead.
- `MOTION_BACKEND=ffmpeg` renders distinct 16:9 and 9:16 clips. Each full
  keyframe is contained inside a blurred, darkened background with a small
  safe margin and only subtle movement, avoiding center crops of heads/faces.
  `MOTION_BACKEND=kaggle_wan` requires a configured `KAGGLE_WAN_COMMAND`
  adapter that writes a compatible H.264 MP4. Commands may use `{image}`,
  `{prompt}`, `{duration}`, `{output}`, `{shot_id}`, `{seed}`, `{aspect_ratio}`,
  `{width}`, and `{height}` placeholders;
  otherwise the standard `--image/--prompt/--duration/--output` flags are added.
- The default `MUSIC_BACKEND=synth` creates a deterministic, vocal-free
  underscore. `MUSIC_BACKEND=ace_step` requires an `ACE_STEP_COMMAND` adapter
  using `{prompt}`, `{duration}`, `{output}`, and `{seed}` placeholders, or the
  equivalent command-line flags.
- Final assembly outputs `outputs/final_9x16.mp4` and
  `outputs/final_16x9.mp4`, with ducked and loudness-normalized narration/music,
  English subtitles burned into the picture and retained as a selectable track,
  and a programmatically typeset "AI-assisted film" end card. The standalone
  `outputs/subtitles.srt` is kept alongside the videos.
- `--shot shot_XX` on `--stage all` regenerates only that shot's narration,
  keyframe, and both aspect-specific motion renders when their inputs change;
  the score is refreshed only if its global inputs change, and both final aspect
  ratios are reassembled.
- Every model or media-tool call is appended to `logs/runs.jsonl`. Stage outputs
  are cached by SHA-256 hashes of their prompts, settings, and relevant input
  file contents.
