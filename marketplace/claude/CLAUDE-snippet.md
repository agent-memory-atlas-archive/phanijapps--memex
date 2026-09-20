## Memory (memex)

- When the user states a durable fact, preference, or rule, or asks to memorize
  one, write it with `memex_write` (or `memex write`). Choose project scope for
  workspace architecture, conventions, and decisions; choose global scope for
  facts intended across projects. If unclear, choose project. Pass
  `scope="project"` or `scope="global"` to the tool, or the matching `--scope`
  to the CLI. Check the returned file path.
