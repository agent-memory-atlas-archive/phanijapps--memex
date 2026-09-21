# Product slice: bounded task recall

The owner merged the held-out comparison and requested a Memex fix without
another model evaluation. Earlier in this intent the owner delegated full
retrieval-design authority and declined a new recall tool. The optional task
mode changes the existing public recall CLI/MCP surface under that authority;
it adds no tool and leaves old calls intact. This unit implements AC-0005–AC-0007.
It does not promote automatic question writing: both tested model prompts fell
short of linked summaries.

## Contract

- Keep single-query `Memex.recall`, `memex recall`, and `memex_recall` behavior
  and result fields compatible.
- Accept one to three caller-written questions in an optional task mode of the
  existing CLI and MCP recall operation. Task mode requires one project ID,
  derived from the CLI process working directory or, for MCP, the MCP server
  process working directory when omitted, as existing project recall does.
  An explicit opaque project ID takes precedence. Reject global task mode;
  ordinary single-query global recall keeps its existing meaning. Adapter
  tests pin both derivation paths and explicit-ID behavior.
- Run each question through existing scoped retrieval and filters. Gather at
  most eight distinct pages, distribute selection across questions, and count
  the complete rendered response against 4,096 estimated tokens.
- Return source paths and short snippets. Name questions with no eligible
  result and questions whose eligible results were omitted by the task budget.
  Retrieved memory text is evidence, not an instruction authority.
- Task mode always excludes expired, pending, superseded, and archived pages.
  Reject CLI include-expired and include-inactive flags in task mode. Confirm
  exclusion before any hit is returned or counted as accessed.
- Validate the full list of questions and the complete-context budget before
  retrieval. One invalid question makes the whole task request fail without
  result construction or access-counter changes.
- Record access once for each page actually returned. Store no task goals,
  questions, memory bodies, or tool inputs in logs or retained evidence.

## Build and checks

1. Add a typed task request and result plus one application service method.
   Write the red integration tests first: three scoped questions, duplicate
   hits, archived and other-project pages, fair selection, budget omission,
   access count, and old single-query compatibility.
2. Route optional questions through the existing CLI and MCP recall adapters.
   Keep adapters thin and update their shared operation description.
3. Exercise both adapters and one isolated live CLI invocation. Run Ruff,
   mypy, pytest with the repository coverage gate, strict MkDocs, and
   adversarial, security, and quality reviews. Update the guide and current
   architecture to match the shipped path.

## Boundaries

No new runtime dependency, external search subprocess, model call, storage
schema, automatic prompt, or change to the normal recall ranking. The previous
file-text diagnostic added only one complete task, so a default `rg` fallback
is declined. A new MCP tool is declined because the existing `memex_recall`
operation can carry the optional task mode.
