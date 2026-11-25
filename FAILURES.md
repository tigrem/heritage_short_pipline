
## Radio narration failures — 2026-11-25T16:56:39.150329Z


| Shot | Error |
| --- | --- |
| `shot_05` | HTTPError: HTTP Error 429: Too Many Requests |
| `shot_06` | HTTPError: HTTP Error 429: Too Many Requests |
| `shot_07` | HTTPError: HTTP Error 429: Too Many Requests |
| `shot_08` | HTTPError: HTTP Error 429: Too Many Requests |

## Radio narration failures — 2026-11-25T17:04:42.360079Z


| Shot | Error |
| --- | --- |
| `shot_05` | TTSAPIError: Gemini TTS HTTP 429: Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier). Please retry in 14h58m23s or upgrade your tier at https://ai.dev/rate-limit. |
| `shot_06` | TTSAPIError: Gemini TTS HTTP 429: Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier). Please retry in 14h57m16s or upgrade your tier at https://ai.dev/rate-limit. |
| `shot_07` | TTSAPIError: Gemini TTS HTTP 429: Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier). Please retry in 14h56m14s or upgrade your tier at https://ai.dev/rate-limit. |
| `shot_08` | TTSAPIError: Gemini TTS HTTP 429: Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier). Please retry in 14h55m17s or upgrade your tier at https://ai.dev/rate-limit. |

## Resolution

On 2026-11-25, shots 05–08 were regenerated successfully after updating the API key. All 10 narration WAVs now match the current storyboard.

## Additional pipeline findings and resolutions

### Run-log failure snapshot

The current 240-record run-log summary contains 10 historical `failure`
records: eight `radio_tts` failures (two each for `shot_05` through `shot_08`),
one `keyframe_reference` failure for `shot_01`, and one `keyframes` failure
for `shot_01`. The final outputs were subsequently assembled successfully.
These historical records are retained as failures, not relabeled as successes;
the exact attempt details remain in the local, Git-ignored
`logs/runs.jsonl`.

### Transient TTS throttling and quota exhaustion

The run log records transient HTTP 429 responses for narration shots 05–08,
followed by Gemini's explicit free-tier daily-limit response for the same
shots. The retry wrapper logged individual attempts and the exhausted calls
were recorded as failures; they were not reported as successful generations.
After the API key was updated, the four WAVs were generated successfully.
Cached narration is reused unless the shot's narration inputs change.

### Cloudflare keyframe generation

- The reference-caption model `@cf/unum/uform-gen2-qwen-500m` returned HTTP
  410 after deprecation. The reference-description step was moved to the
  current configured Cloudflare reference model.
- Flux Schnell returned HTTP 400 when passed a `seed` request property
  (`Additional or unevaluated properties '/seed'`). The pipeline now keeps the
  shot seed in the prompt, SHA-256 cache identity, and run log, but omits the
  unsupported API property.

### Framing, faces, and unwanted props

Earlier visual review found clipped heads, unclear/blank faces, inconsistent
character appearance, and occasional unrequested props. Keyframe prompts now
require complete visible heads and faces, natural headroom, complete anatomy,
and no unrequested objects; only the shot's listed approved refs are used.
Image dimensions and pixel variance are checked, with invalid images retried
or surfaced as failures. Motion rendering contains the full keyframe over a
blurred background with subtle movement rather than center-cropping people.
The near-final review reported faces and expressions clearly framed in both
aspect ratios.

### English subtitle spacing and placement

User Test 2 flagged the missing space after `Eden:` in shot 2 and captions
covering too much of the vertical scene. The shot 2 subtitle now uses the
spaced speaker label and separates Girma's and Eden's turns onto separate
lines. Captions use compact bottom-safe styles (16:9: font size 14, margin 16;
9:16: font size 10, margin 18). The SRT and both exports were regenerated
together; the standalone SRT and selectable subtitle stream remain available.
