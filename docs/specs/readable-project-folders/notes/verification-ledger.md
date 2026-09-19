# Verification Ledger: Readable Project Folders

## 2026-09-19

- Isolated CLI smoke used an enterprise GitLab-style origin whose repository
  basename was `memex`. The write produced
  `docs/projects/git-memex/preferences/readable-locator-smoke.md`, scoped recall
  found the page, and front matter retained the opaque `project_id` plus display
  label.
- Installed migration skill validation passed with `quick_validate`.
- Synthetic migration dry-run preview used an old-layout fixture at
  `docs/projects/abcdefabcdefabcdefabcdef/preferences/example.md` with matching
  24-hex `project_id`. The preview proposed
  `docs/projects/git-memex/preferences/example.md`, found exactly one source,
  and confirmed the target path did not exist.
- The smoke and preview used isolated directories. No existing store was moved,
  renamed, or deleted during those checks.
- The owner chose a fresh store instead of migration. On 2026-09-19, the
  450-file, 73 MB `~/.memex` store was renamed to
  `~/.memex-before-reset-20260919T185014Z`; an empty
  `~/.memex` directory was created. The backup still contains 450 files.
  No legacy page or transcript was transformed or moved into the new store.
- Final link lookup and guide fixes pass the full quality gates: 651 tests
  passed, 1 skipped, 90.53% coverage; Ruff lint and format, mypy, and the
  strict docs build passed. `git diff --check` passed.
- A later adversarial pass found a same-slug source page with no outgoing
  links could escape ambiguity detection. Index-backed source namespace
  checking and a regression test now cover that case in outgoing links,
  backlinks, and the link graph. Final adversarial, quality, and scoped
  security reviews were clean.
