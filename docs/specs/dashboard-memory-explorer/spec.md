# Spec: Dashboard memory explorer

- **Status:** Shipped
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001
- **Brief:** `docs/product/briefs/modern-htmx-dashboard.md`
- **Discovery:** none
- **Contract:** none — localhost read-only UI
- **Shape:** ui

## Objective

A developer can browse a large Memex store in the local dashboard without losing
their type or project selection, scan captured sessions by date and origin, and
read a chronological replay whose User, AI assistant, and Tool turns are easy to
tell apart. Direct links and HTMX interactions show the same data.

## Durable Outputs

| Role | Destination | Evidence | Closeout |
| --- | --- | --- | --- |
| User guide | `docs/gitpages/guide.md` | Pagination and replay instructions | Strict docs build |
| Entry point | `README.md` | Dashboard capabilities | Review |
| Architecture | `docs/architecture/overview.md` | Module ownership and read-only boundary | Strict docs build |

## Boundaries

### Always do

- Use 20 newest-first memory cards per page after filtering by type and scope.
- Keep browser history, direct URLs, and HTMX controls coherent for every
  selection.
- Render sessions by capture date, project label when safely available, and
  harness; render User, AI assistant, and Tool replay cards separately.
- Treat all page, query, metadata, and transcript values as untrusted.

### Ask first

- Add a dependency, remote asset, build step, dashboard write action, or
  transcript format change.
- Change the pagination size or search semantics.

### Never do

- Execute captured tools or mutate memory, transcripts, or index access counters
  in a dashboard GET.
- Use raw local paths, repository remotes, or unescaped untrusted values as
  visible UI metadata.
- Serve the dashboard beyond localhost.

## Testing Strategy

Live-server route tests with an isolated store verify pagination boundaries,
selection preservation, search scope, grouped sessions, replay roles, malformed
records, escaping, and the read-only GET invariant. Static checks verify the
package includes the local CSS and adds no dependency. A real browser walkthrough
at desktop, 320px width, and 200% zoom verifies presentation, controls, and
keyboard closing; observations live in `notes/verification-ledger.md`.

## Acceptance Criteria

- [x] AC-0001: A selected type and scope returns at most 20 cards ordered by
  descending update time with a deterministic slug tie-break; pages do not
  overlap and the current page and total result count are visible.
- [x] AC-0002: Previous and Next preserve type and scope through a styled direct
  `/view/memories` URL and matching HTMX fragment request.
- [x] AC-0003: Changing type or scope starts at page one; invalid page values
  use page one and out-of-range values clamp to the last valid page.
- [x] AC-0004: “All memory” includes global and project pages, “Global only”
  includes only global pages, and a project selection includes only that
  project; cards identify a safe display label.
- [x] AC-0005: Search supports `best`, `global`, and `project`: best tries
  the selected project before all-memory fallback, global searches all
  namespaces, and project searches only that project. Results identify origin.
- [x] AC-0006: Sessions appear under descending capture-date headings, then
  project-label and harness groups, with a direct replay link for each session.
- [x] AC-0007: A replay preserves transcript order and gives each User, AI
  assistant, and Tool turn a named visual card and available timestamp.
- [x] AC-0008: User and tool text is escaped; AI Markdown uses the existing safe
  renderer; long tool fields show a 500-character preview, at most 2,000
  characters of expandable display, and a truncation notice.
- [x] AC-0009: Malformed transcript lines are skipped safely; missing or
  path-like session identifiers and invalid project identifiers reveal no
  transcript or page outside their namespace.
- [x] AC-0010: The served shell and CSS use the reference's white surfaces,
  navy panels, cyan accents, magenta actions, compact cards, and distinct replay
  roles without remote assets or new runtime dependencies.
- [x] AC-0011: At 320px width and 200% zoom, navigation, pagination, session
  headings, role labels, and close control remain visible and keyboard reachable.
- [x] AC-0012: Dashboard GET requests leave page, transcript, and SQLite data
  unchanged in an isolated store.

## Follow-ons

- Project and harness filter controls for sessions require a separate accepted
  session-metadata contract; grouping uses the existing data only.

## Assumptions

- Technical: `viz.py` is a localhost stdlib server, and transcript summaries
  carry session IDs and timestamps (`src/memex/infrastructure/viz.py`,
  `src/memex/infrastructure/transcript_hook.py`, inspected 2026-09-19).
- Product: 20 cards, date groups, and rich User/AI/Tool replay are confirmed by
  the user (2026-09-19).
- Process: this is a follow-on slice of the Ready dashboard brief, with no new
  storage or deployment contract (user approval 2026-09-19).
