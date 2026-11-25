# Ethics, rights, provenance, and disclosure

## Reference asset provenance and likeness

The four repository-local reference images (`eden.jpeg`, `girma.png`, `living_room.jpg`, and `story_telling_area.jpg`) are **AI-generated** assets. Confirm the generator's terms and ensure no recognizable real person's likeness or third-party rights are infringed before public release; never imply that a real person spoke the fictional dialogue.

| File | Asset type | Source / origin | Terms & likeness check |
| --- | --- | --- | --- |
| `assets/refs/eden.jpeg` | Character (Eden) | **AI-generated** — record tool/batch note | Check generator terms; verify no unconsented real likeness |
| `assets/refs/girma.png` | Character (Ato Girma) | **AI-generated** — record tool/batch note | Check generator terms; verify no unconsented real likeness |
| `assets/refs/living_room.jpg` | Environment | **AI-generated** — record tool/batch note | Check generator terms; verify no real people/private spaces |
| `assets/refs/story_telling_area.jpg` | Environment | **AI-generated** — record tool/batch note | Check generator terms; verify no real people/private spaces |

Record each asset's generator/model, session or batch note, usage terms, and likeness check before publishing. If any asset has restrictive terms or an unconsented likeness, replace it and regenerate affected shots.

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