# Memory contract (memex)

- At task start, run `memex hook session-start` and treat its output as
  project context: it lists durable memories relevant to this repository.
- When the user states a durable fact, preference, or rule, record it:
  `memex write --type <entity|preference|procedure|summary> --title "..." --body "..."`
- The `memex_recall` MCP tool (or `memex recall "<query>"`) searches all
  stored memories; prefer it over re-asking the user.
- Transcripts are captured automatically at turn completion; you never
  need to ingest sessions manually.
