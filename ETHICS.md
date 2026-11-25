# Ethics, rights, provenance, and disclosure

## Reference asset provenance and likeness

The project owner confirms that all four repository-local reference images are
AI-generated. This confirms their general origin, but the project does not
record the generating tool/model, generation date, prompt, or batch record.
AI-generated origin alone does not establish output rights or prove that an
image contains no real-person likeness or identifiable/private location.

| File | Asset type | Source / origin | License / terms | Likeness / consent |
| --- | --- | --- | --- | --- |
| `assets/refs/eden.jpeg` | Adult character reference (Eden) | AI-generated, confirmed by project owner; generator and prompt not recorded. | **UNVERIFIED** — applicable generator/model output terms not recorded. | **UNVERIFIED** — whether based on a real person's likeness and any consent are not recorded. |
| `assets/refs/girma.png` | Adult character reference (Ato Girma) | AI-generated, confirmed by project owner; generator and prompt not recorded. | **UNVERIFIED** — applicable generator/model output terms not recorded. | **UNVERIFIED** — whether based on a real person's likeness and any consent are not recorded. |
| `assets/refs/living_room.jpg` | Domestic environment | AI-generated, confirmed by project owner; generator and prompt not recorded. | **UNVERIFIED** — applicable generator/model output terms not recorded. | **UNVERIFIED** — whether based on a private/identifiable place or depicts people is not recorded. |
| `assets/refs/story_telling_area.jpg` | Domestic environment | AI-generated, confirmed by project owner; generator and prompt not recorded. | **UNVERIFIED** — applicable generator/model output terms not recorded. | **UNVERIFIED** — whether based on a private/identifiable place or depicts people is not recorded. |

Before public release, record for each image: generating tool/model and
version, generation date and available prompt/batch record, applicable output
terms and attribution obligations, and the result of a likeness/location
review. If an image was based on a real person's likeness, verify that
permission covers AI-reference use and publication. If terms or consent cannot
be verified, replace the image and regenerate affected shots.

**All four assets still have unverified output terms and likeness/location
checks. Keep the GitHub repository Private until those rights and consent
questions are verified or an affected image is replaced.** Never imply that a
real person spoke the fictional dialogue.

## Models, services, and software terms

Not legal advice. Review hosted-service terms alongside model and library licenses before publishing or redistributing:

* **Google Gemini API (`gemini-3.8-flash-tts`):** Subject to [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms), [Google APIs Terms](https://developers.google.com/terms), and the [Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy).
* **Cloudflare Workers AI:** Subject to [Cloudflare Workers AI docs](https://developers.cloudflare.com/workers-ai/) and [Cloudflare Terms of Use](https://www.cloudflare.com/terms/).
* **FLUX.1 `[schnell]` (`@cf/black-forest-labs/flux-1-schnell`):** Apache-2.0 model license ([Hugging Face model card](https://huggingface.co/black-forest-labs/FLUX.1-schnell)); hosted API use is also subject to Cloudflare terms.
* **Reference captioning (`@cf/meta/llama-4-scout-17b-16e-instruct`):** Subject to Cloudflare Workers AI terms and [Meta Llama](https://www.llama.com/) terms/license (replacing deprecated `@cf/unum/uform-gen2-qwen-500m`).
* **FFmpeg (`imageio-ffmpeg`):** Bundled executable reports **GNU GPL version 3** (`ffmpeg -L`); `imageio-ffmpeg` is BSD-2-Clause. Keep required notices if redistributing.
* **Python packages (`jsonschema`, `python-dotenv`, Pillow, `imageio-ffmpeg`):** MIT, BSD-3-Clause, HPND/PIL, and BSD-2-Clause respectively; preserve notices across dependencies.
* **Optional adapters (`kaggle_wan`, `ace_step`):** Not used for this cut; review their terms/licenses if enabled.

## AI disclosure and YouTube upload

Use both disclosures:
1. Keep the in-film end card (**“AI-assisted film”** / **“Created with the assistance of artificial intelligence.”**) in both `16:9` and `9:16` exports.
2. Enable YouTube's **AI/altered or synthetic content** disclosure in YouTube Studio per [Disclosing use of GenAI content](https://support.google.com/youtube/answer/14328491), and keep English subtitles accessible.

## Metadata, attribution, and data handling

Retain provenance/terms notes, keep required disclosures intact, and keep `.env`, `logs/`, and `outputs/` out of Git/public shares without API keys or sensitive log contents.