# Memory contract (memex)

- At task start, run `memex hook session-start` and treat its output as
  project context: it lists durable memories relevant to this repository.
- When the user states a durable fact, preference, or rule, or asks to memorize
  one, write it with `memex_write` (or `memex write`). Choose project scope
  for workspace architecture, conventions, and decisions; choose global scope
  for facts intended across projects. If unclear, choose project. Pass
  `scope="project"` or `scope="global"` to the tool, or the matching `--scope`
  to the CLI. Check the returned file path.
- The `memex_recall` MCP tool (or `memex recall "<query>"`) searches all
  stored memories; prefer it over re-asking the user.
- Transcripts are captured automatically at turn completion; you never
  need to ingest sessions manually.
