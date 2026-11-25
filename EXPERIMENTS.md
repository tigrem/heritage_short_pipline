# Production experiments

Results below describe the current project run and its recorded audience
feedback; they are production notes, not controlled scientific trials.

## 1. Amharic narration duration alignment

- **Hypothesis:** Matching each shot slot to its Amharic WAV will keep the film
  inside the 60–90-second brief without rushing the emotional arc.
- **Change:** Measured the generated WAVs and aligned `duration_sec` to the
  narration, then set the storyboard total to their sum.
- **Result:** The current total is 85.36 seconds; schema/runtime validation
  passes.
- **Keep/Revert:** Keep. Retain the duration-sum check on future edits.

## 2. Measured pauses in dialogue pacing

- **Hypothesis:** Calm, measured Amharic delivery and readable speaker labels
  will make multi-line exchanges easier to follow.
- **Change:** Kept clear speaker attribution and pauses expressed by the
  narration punctuation; aligned slots to actual WAV lengths.
- **Result:** User Test 2 described the Amharic narration as calm, clear, and
  respectful. A brief additional audible pause between speakers remains a
  follow-up rather than a change to the already aligned WAVs.
- **Keep/Revert:** Keep the current pacing; assess a deliberate pause in a
  future narration revision.

## 3. Cloudflare Flux seed handling

- **Hypothesis:** Sending a fixed seed parameter to Flux Schnell would make
  repeated keyframes deterministic.
- **Change:** Tested the API parameter; the selected Flux endpoint rejected
  `seed`. Kept the shot seed in the prompt, cache inputs, and run record rather
  than sending an unsupported field.
- **Result:** Requests succeed without the rejected parameter; changing the
  seed still changes the prompt/cache identity.
- **Keep/Revert:** Keep prompt/cache/log seed tracking; do not send `seed` to
  the current Flux model.

## 4. Filename-specific reference anchors

- **Hypothesis:** Explicitly tying the approved refs to character and room
  traits will reduce visual drift compared with generic prompt text alone.
- **Change:** Added distinct cues for `eden.jpeg`, `girma.png`,
  `living_room.jpg`, and `story_telling_area.jpg`, and used only each shot's
  listed refs.
- **Result:** The visual review showed Eden's teal/blue dress and Girma's white
  shawl with patterned trim more consistently in the revised conversation
  shots.
- **Keep/Revert:** Keep; continue checking generated frames manually.

## 5. Optional image-conditioned keyframes

- **Hypothesis:** A supported image-to-image model can use the listed refs more
  directly than a text-only generator.
- **Change:** Added an opt-in Stable Diffusion XL Workers AI branch that passes
  a contact sheet made from only the shot's refs; Flux Schnell remains default.
- **Result:** The configured production run used Flux and filename-specific
  anchors; the conditional branch remains selectable but was not used for
  these final exports.
- **Keep/Revert:** Keep as an explicit optional model path; do not imply that
  Flux itself receives image inputs.

## 6. Keyframe anatomy and integrity checks

- **Hypothesis:** Prompt guardrails plus basic image validation will catch
  unusable frames before motion rendering.
- **Change:** Required complete, visible faces/headroom and natural anatomy;
  rejected undersized, malformed, extreme-aspect, or near-blank images and
  retried transient quality failures.
- **Result:** Focused tests confirm blank/undersized images are rejected and a
  rejected generation is retried. Semantic likeness still requires visual
  review.
- **Keep/Revert:** Keep the guard and checks; do not treat them as a substitute
  for reviewing generated media.

## 7. Portrait-safe framing

- **Hypothesis:** A full-frame contained image over a blurred background will
  preserve faces better than center-cropping a landscape shot for 9:16.
- **Change:** Rendered separate 16:9 and 9:16 clips with safe margins and
  subtle movement.
- **Result:** Both final exports have the expected 1920×1080 and 1080×1920
  dimensions; User Test 2 reported no heads cut off and accepted the blurred
  side bars.
- **Keep/Revert:** Keep both aspect-specific renders and their independent
  caches.

## 8. Burned-in subtitles

- **Hypothesis:** Burned English captions will be immediately readable on
  short-form platforms while a selectable track and SRT preserve flexibility.
- **Change:** Burned the SRT into both final aspect ratios and retained the
  English `mov_text` stream and standalone SRT.
- **Result:** Frame inspection confirms visible captions in both exports; the
  final files retain a subtitle stream and match the 85.36-second duration.
- **Keep/Revert:** Keep all three subtitle forms.

## 9. User Test 2 subtitle polish

- **Hypothesis:** A speaker-turn line break and smaller bottom-safe captions
  will improve clarity while covering less of the vertical center.
- **Change:** Made shot 2's `Eden: “Grandfather...` spacing explicit, separated
  its speaker turns onto two subtitle lines, and reduced the 16:9/9:16
  subtitle font sizes and vertical margins.
- **Result:** The compact styles were checked on actual shot frames; the 9:16
  caption sits in the lower blurred safe area. Rebuilt SRT and both films.
- **Keep/Revert:** Keep. Preserve the audience's audible-pause suggestion as a
  narration follow-up.

## 10. Selective regeneration and cache logging

- **Hypothesis:** Stage/shot SHA-256 cache keys will avoid repeating unrelated
  generation when one prompt changes.
- **Change:** Used per-shot keyframe/narration keys, aspect-specific shot keys,
  assembly dependency hashes, and explicit `cache_hit` log events.
- **Result:** Selected-shot regeneration updated the requested shot and
  reassembled both finals; the log summarizer separates cache events from
  executed model/tool calls.
- **Keep/Revert:** Keep; retain cache and log summaries as part of routine
  production checks.
