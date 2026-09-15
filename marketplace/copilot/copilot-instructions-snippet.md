## Memory (memex)

This project uses memex for durable memory. Respect the memory workflow:

- Relevant project memories are surfaced automatically in CI feedback.
  Before assuming user preferences, tooling choices, or project rules,
  check the `memex MEMORY` blocks in this repository's memory exports.
- When your change relies on a durable fact (a preference, a tooling
  rule, a deployment constraint), record it in your PR description so a
  maintainer can persist it with
  `memex write --type <entity|preference|procedure> --title "..." --body "..."`.
- The `memex-verify` workflow on this repository reports memory health
  (index freshness, link integrity) for every PR.
