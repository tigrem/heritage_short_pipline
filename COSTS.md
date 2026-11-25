# Cost and cache report

## Recorded run snapshot

The latest `python -m pipeline.summarize_logs` run read 240 records from
`logs/runs.jsonl`:

- **136** successful model/tool calls
- **65** explicit SHA-256 cache-hit records
- **29** retry-attempt records
- **10** logged failures (historical failures; the current final exports were
  assembled successfully)
- **1,647.733 seconds** of summed recorded latency (**27.462 minutes**)
- **57** cache entries currently present; this is a point-in-time count, not a
  historical count of avoided generations

Latency totals include attempts that later failed and exclude no model/tool
work represented by the log. Cache-hit events have zero latency. They do not
measure wall-clock pipeline duration or prove that every avoided call would
have incurred a charge.

The 240 records comprise **175 non-cache events** (successful calls, retries,
and failures) plus the 65 cache-hit events.

## Estimated spend

**Estimated direct service spend for the recorded run: $0 under the configured
free-tier usage assumption.** This is an estimate, not a billing statement.
The run log has no provider billing fields, and therefore cannot independently
verify charges, discounts, or account-level quotas. In particular,
`est_gpu_minutes` was not recorded for any of the 240 entries; the logged
27.462 minutes is latency, not GPU time or billable compute.

The log records Gemini free-tier quota/rate-limit failures and subsequent
successful narration generation after the API key update. Check the Gemini
and Cloudflare account usage pages for authoritative billing before
distribution or additional generation.

## Cache savings

The summarizer records cache reuse separately from model/tool executions.
This run produced 65 cache-hit events alongside 175 non-cache records, showing
reuse for unchanged inputs. Cache hits are recorded events, not a measured
dollar saving or proof that every avoided call would otherwise have incurred a
charge. Cache entries are keyed by stage/shot inputs and are local under the
ignored `outputs/cache/` directory. Cache counts and the $0 estimate are not
substitutes for provider usage reports.
