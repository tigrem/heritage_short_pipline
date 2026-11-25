# Written assignment report — draft to personalize

> The detailed report prepared for submission is in [REPORT.md](REPORT.md).
> Keep this file as working notes if you continue revising your personal
> reflections.

> **Do not submit this unchanged.** This draft uses the facts documented in the
> project. Before submission, add your own first-person reflections, verify
> audience-session details against your notes, and correct anything that does
> not match what you actually did. Do not invent dates, participant identities,
> consent, provenance, licenses, or quotations.

## Intended audience and story

**Ato Girma's Promise** (የአያቴ ግርማ ቃል ኪዳን) is a 10-shot Amharic
heritage short with English subtitles. The storyboard and rendered cut are
85.36 seconds. The intended audience documented in the project is young
adults, families, viewers interested in Ethiopian heritage stories, and
diaspora audiences balancing personal ambition and family ties.

The story follows Eden as she weighs leaving to pursue her future and Ato
Girma as he shares regret about a promise to give loved ones his time. Eden's
ambition is not treated as a rejection of family; Girma does not ask her to
abandon her plans. The emotional intention is to invite reflection on how
ambition and care can coexist, and on the conversations and acts of care we
should not postpone.

**Personalize:** Explain why you selected this story and audience, and what
you hoped viewers would feel or discuss afterward.

## Audience testing and resulting changes

The existing project notes record **three viewers for each of two sessions**.
Participant names and session dates are not recorded in the notes reviewed
here; add dates only from your own records. Keep viewers anonymous unless they
gave permission to be identified.

### User Test 1 — Radio Cut

The notes identify the participants by audience role: a young-adult/diaspora
viewer, an elder/heritage-drama viewer, and a short-form/creator viewer. The
radio cut was described as approximately 84 seconds. The recorded feedback is
summarized here, not presented as verbatim quotations:

- The young-adult/diaspora viewer found Eden's pushback relatable and noted
  that speaker attribution needed to be clear in multi-line exchanges.
- The elder/heritage-drama viewer responded positively to the grounded tone
  and suggested breathing room between back-to-back lines.
- The short-form/creator viewer found the pacing suitable and asked for
  particular attention to framing in shots 8–9.

The project notes say the Amharic spelling/phrasing and corresponding English
subtitles were tightened, dialogue speaker labels were retained, and shot
durations were aligned to the narration WAVs. The total at that review is
recorded as 84.43 seconds; the current saved narration and storyboard total
85.36 seconds. The visual pass adjusted shots 8–9 for clearer face framing and
location/character continuity.

### User Test 2 — Near-Final Cut

The notes record three viewer roles and review of the near-final 16:9 and
9:16 cuts at approximately 85.36 seconds. The comments below are transcribed
from the project notes supplied for this project. **Before submitting, compare
them with your original session notes or recordings. Keep quotation marks only
if each is verbatim and you have permission to quote; otherwise paraphrase
anonymously.**

**Viewer 1 — Young Adult / Diaspora Viewer (story & emotional arc):**

> “The emotional arc lands much better now—seeing Eden in the blue dress and Ato Girma in his white shawl and patterned trim stay consistent through the conversation, especially when they sit together and talk about not putting off loved ones until tomorrow. Burning in the English subtitles makes it easy to follow every line right away.”

**Viewer 2 — Elder / Heritage Drama Viewer (tone, pacing & clarity):**

> “The Amharic narration is calm, clear, and respectful, and the closing AI disclosure card is very easy to read. One small polish detail: in the second shot's English subtitle, Eden:"Grandfather... is missing a space after the colon, and when one shot has two speakers back-to-back, a brief pause makes the turn feel slightly more natural.”

**Viewer 3 — Short-Form / Content Creator Viewer (vertical & horizontal presentation):**

> “Both the 16:9 cut and the 9:16 cut keep the characters' faces and expressions clearly framed without cutting off heads. On the vertical 9:16 cut, the blurred side bars work cleanly, though a slightly cleaner, more compact subtitle placement in the bottom safe zone will keep the center of the scene even less covered during longer lines.”

The documented polish changed shot 2's subtitle to include a space after
`Eden:` and a line break between speakers, compacted the subtitle styling in
both aspect ratios, and regenerated the SRT and final exports. The feedback
also asked for a brief audible pause between speakers; the project notes say
that suggestion was retained as follow-up and the narration WAVs were not
changed during this subtitle-only polish.

**Personalize:** State how the actual sessions were run and what you learned
that was not captured in these notes. Do not turn summaries into invented
direct quotations.

## Hardest technical or creative problem

**Draft reflection to verify:** One of the main production challenges was
preserving character/location consistency and clear face framing across
generated keyframes and both 16:9 and 9:16 exports. The workflow used
shot-specific reference anchors, headroom/anatomy prompt guards, image-quality
checks, and full-frame contained motion renders rather than aggressive
portrait crops.

A separate documented API issue was that the default Cloudflare Flux endpoint
rejected a `seed` request field. The pipeline kept the shot seed in the prompt,
SHA-256 cache identity, and run log, and stopped sending the unsupported API
field.

**Personalize:** Which problem was hardest for you personally? Describe what
you tried, how you recognized the failure, and what tradeoff you accepted.

## One practice that helped and one that did not

- **Helpful practice — draft:** Use only the shot's listed character/location
  references and make composition requirements explicit. The documented
  production review reports more consistent character details and safer
  framing; describe your own observations and limits.
- **Unhelpful practice — draft:** Sending a `seed` field directly to the
  selected Flux endpoint failed because that endpoint rejected it. The working
  alternative in this project was to retain the seed in the prompt, cache
  identity, and log. Explain what you would check earlier next time.

Replace these examples if they do not represent your own experience.

## Ceiling work and constraints

The project reached a validated 85.36-second cut in both 16:9 and 9:16, with
Amharic narration, English subtitles, an instrumental score mixed under the
narration, and a visible AI end card. The pipeline includes per-stage/shot
SHA-256 caching, retries, run logging, and selective shot regeneration.

The current run summary records 240 events: 65 cache hits, 136 successes, 29
retry events, and 10 historical failures. The log does not record GPU minutes
or provider billing. The documented `$0` figure is a free-tier estimate, not
verified account billing. The failures file records Gemini rate/quota limits
and an unsupported Flux seed field; it also records that the narration was
later regenerated and the seed handling changed.

**Personalize:** Describe what you did to push quality as far as you could
within your actual time, quota, tools, and budget. State what still fell short
or remains unfinished. Do not claim that free-tier use proves a zero bill.

## Next steps

1. The project owner confirms all four references are AI-generated. Record
   each tool/model/version, generation date, available prompt/batch record,
   output terms, and likeness/location check. Keep the GitHub repository
   Private until rights and any consent questions are resolved or an affected
   image is replaced.
2. Rewatch both final exports and verify captions, audio, framing, and the
   end card after upload. Apply YouTube's current AI/altered-content disclosure
   and confirm English subtitles are attached/selectable.
3. Decide whether to revise the narration to add the suggested speaker-turn
   pause. If changed, regenerate the affected audio, recheck shot timing and
   the 60–90-second total, and rebuild both exports.
4. Finish the report with only personal observations, submit accessible video,
   walkthrough, post, and repository links, and meet the assignment deadline.

**Personalize:** Add concrete next actions and dates you can meet. Mark any
step that is still pending as pending.

## Optional figures to add after rights review

Do not embed reference photos or recognizable generated likenesses in a public
report until their use is permitted. If permitted, add:

- **Figure 1:** Screenshot of `python -m pipeline.validate` reporting success.
- **Figure 2:** A frame from each final aspect ratio showing subtitle placement
  and the end card.
- **Figure 3:** A before/after record of a single-shot prompt edit, showing
  that only the selected shot's media regenerated and final assembly updated.

The final MP4s and generated frames are in the Git-ignored `outputs/` folder;
include separate image files with the report if required by the submission
portal.
