# Assignment submission checklist

Use this as a final handoff checklist. Do not publish rights-unverified
reference images or make claims about costs, consent, or audience sessions that
you cannot support.

## 1. Protect local secrets and generated files

- [ ] Do not open, edit, copy, or stage `.env` for submission. Keep API keys
  private.
- [ ] From the project root, check the exact paths:

  ```powershell
  git check-ignore -v .env logs/runs.jsonl outputs/final_9x16.mp4 outputs/final_16x9.mp4
  git status --short
  git status --short --ignored .env logs outputs
  ```

- [ ] Confirm `git check-ignore` reports `.env`, `logs/`, and `outputs/` as
  ignored. In the ignored-status output, expect `!!` entries for those paths;
  none should appear as added, modified, or untracked project files.
- [ ] If any secret or generated output is staged, unstage only that specific
  path before committing; never force-add `.env`.
- [ ] If the assignment requires run evidence, submit a reviewed copy or
  screenshot of the log summary separately. `logs/` is intentionally ignored
  by Git.

## 2. Resolve rights before a public repository

- [ ] Complete the provenance and permission review in [ETHICS.md](ETHICS.md)
  for all four files in `assets/refs/`.
- [ ] Obtain written permission for recognizable likenesses and for
  AI-reference use and distribution; record the source/license and attribution
  terms for the environment images too.
- [ ] Replace any asset whose rights or consent cannot be confirmed, update
  only the affected storyboard references, and regenerate dependent shots.
- [ ] Keep the GitHub repository **Private** until these checks are complete.
  Do not switch it to Public based only on the assets being present locally.

## 3. Verify project and media

- [ ] Run validation and tests from the project root:

  ```powershell
  .venv\Scripts\python.exe -m pipeline.validate
  .venv\Scripts\python.exe -m unittest discover -s tests
  .venv\Scripts\python.exe -m pipeline.summarize_logs
  ```

- [ ] Confirm the storyboard total remains between 60 and 90 seconds and that
  both final exports, English captions, and the end-card disclosure match the
  version being submitted.
- [ ] Review the final cuts by watching them, including the beginning, the
  shot 8–9 framing, subtitle-safe zones, audio balance, and closing card.
- [ ] Confirm the English SRT is available and the subtitle track is selectable
  after upload. Attach/upload the English subtitle file where the platform
  supports it, even though the film also has burned-in captions.

## 4. Publish required deliverables

- [ ] Upload `outputs/final_9x16.mp4` to YouTube and copy its accessible URL.
- [ ] Upload `outputs/final_16x9.mp4` and copy its accessible URL.
- [ ] Upload the walkthrough; verify it is **no longer than five minutes** and
  its link is accessible to the assessor.
- [ ] During YouTube upload, enable the current **AI/altered or synthetic
  content** disclosure setting. The visible end card is not a substitute.
- [ ] Confirm the English subtitles are attached/selectable and verify each
  published video plays with captions and end disclosure intact.
- [ ] Publish the public post, or save a screenshot of the published post if
  the assignment accepts screenshot evidence. See [SOCIAL_POST.md](SOCIAL_POST.md).
- [ ] Add the final film, walkthrough, post, and repository URLs to the
  assignment submission. Do not include an inaccessible local file path in
  place of a shareable link.

## 5. Final deadline and handoff

- [ ] Submit all required links and files by **Thursday, November 26, 2026,
  at 23:59 East Africa Time (EAT, UTC+3)**.
- [ ] Re-open every submitted URL in a private/incognito window or signed-out
  browser to verify access.
- [ ] Retain consent/licensing records, test notes, the verified run summary,
  and a copy/screenshot of the public post for your own records.
