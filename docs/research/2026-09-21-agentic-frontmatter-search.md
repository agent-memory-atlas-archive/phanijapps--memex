# Agentic front matter search

**Date:** 2026-09-21
**Question:** Which ideas from OKF, Letta MemFS, LLM Wiki, and second brain
methods should improve Memex search without replacing Markdown or adding
speculative infrastructure?

## Finding

Memex already has the main structural pieces: Markdown pages, strict front
matter, project scope, lifecycle status, tags, links, source paths, and a
rebuildable lexical index. Two OKF conventions fill a real discovery gap: an
optional one-sentence `description` on each page and generated `index.md` files
that list those descriptions one directory at a time.

A description gives an agent a cheap statement of what a page contains and
when it is useful. It can be searched before the full body is read, returned
with recall results, and edited directly in Markdown. This matches the existing
OKF v0.2, which uses descriptions in indexes, search snippets, and previews,
and Letta MemFS, where every memory file has a description that acts as a
signpost in the visible memory tree.

## Evidence

### Open Knowledge Format v0.2

OKF reserves two structural filenames at every directory level. `index.md`
lists that directory's concepts and subdirectories for progressive disclosure.
Its entries should carry each concept's front-matter description. Only the
bundle-root index may have front matter, limited to `okf_version`. Producers may
generate indexes, and consumers must continue when an index is absent.

`log.md` is an optional, newest-first history for its directory scope. It uses
`YYYY-MM-DD` headings and prose entries such as Creation, Update, and
Deprecation. It is history rather than a concept or search document.

Source: [official Open Knowledge Format v0.2 specification](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md),
especially sections 3.1, 4.1, 8, and 9. The official repository describes
generated indexes as a way for agents to navigate a hierarchy without loading
the full bundle.

**Applicable to Memex:** generate deterministic directory indexes from memory
pages and reserve both filenames so neither enters FTS, the link graph, or
consolidation. Memex should not automatically create `log.md` in this slice.
Its page timestamps, lifecycle fields, transcript provenance, and run logs
already record overlapping facts, while a faithful chronological history
cannot be reconstructed from current page state after the fact.

### Letta MemFS

Letta stores long-term memory as Markdown with YAML front matter. A non-empty
`description` explains the purpose of each file. The agent sees the memory tree,
uses ordinary file search and read operations, and loads full file content only
when relevant. Keyword search works without a vector index; semantic and hybrid
search are optional additions.

Source: [Letta MemFS documentation](https://github.com/letta-ai/letta-docs-md/blob/main/concepts/memfs/index.md)
and the [Letta Code memory prompt](https://github.com/letta-ai/letta-code/blob/main/src/agent/prompts/letta_local_memfs.md).

**Applicable to Memex:** searchable descriptions, visible file paths, and
ordinary file reading. Memex should keep SQLite FTS5 as its default search
engine and should not require Letta's directory layout or optional semantic
search.

### LLM Wiki

LLM Wiki frames retrieval as a sequence of search, read, link-following, and a
decision that enough evidence has been gathered. Its pages are structured and
linked rather than flattened into unrelated chunks. The accompanying results
are promising, but the paper is recent and its benchmark claims should not be
treated as Memex product proof.

Source: [Retrieval as Reasoning: Self-Evolving Agent-Native Retrieval via
LLM-Wiki](https://arxiv.org/abs/2605.25480).

**Applicable to Memex:** make the existing `links` and `file_path` fields easy
for an agent to act on after recall. The host agent can read the returned file,
follow a link with another bounded recall, or use its own `rg` for exact
front-matter inspection. Memex does not need an embedded autonomous retrieval
agent or an LLM call in the ordinary recall path.

### Compilation quality caution

Research on wiki compilation reports that blind summarization can lose facts
and that targeted diagnosis is more useful than random retention. This supports
keeping descriptions short and additive: the body remains authoritative, and a
description must never replace it.

Source: [WiCER: Wiki-Compilation Error Recovery](https://arxiv.org/abs/2605.07068).

### Second brain methods

Building a Second Brain emphasizes making notes discoverable for a later real
task. Progressive Summarization adds layers as a note is reused, while PARA
organizes material by Projects, Areas, Resources, and Archives.

Sources: [Progressive Summarization](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)
and [Forte Labs' official resource index](https://fortelabs.com/our-best-free-resources/).

**Applicable to Memex:** the description is a compact first layer, and existing
project scope, page type, lifecycle status, and links already cover most of the
useful organization. A new PARA field would duplicate those dimensions and
would force ambiguous classification on agent memories.

## Recommendation

1. Add optional `description` front matter to memory pages and every shared
   write/read/export path.
2. Index the description as its own FTS5 field without changing the relative
   weights of title, body, or tags.
3. Return the description in recall hits and use it as the snippet when the
   query matched that field.
4. Generate `index.md` in the memory root and every populated descendant
   directory. Each file should list direct pages with title and description,
   then link child indexes. Indexes remain disposable views over pages.
5. Reserve `index.md` and `log.md` everywhere. Exclude both from memory scans,
   FTS, links, exports, and consolidation when they are structural files.
   Preserve a structural `log.md` but do not generate or mutate one.
6. Document a bounded agent search loop: descend from the root index, recall,
   inspect description, read the returned file when needed, follow existing
   links with another recall, and state when evidence remains missing.
7. Keep host-provided `rg` as an optional exact-search aid over returned file
   paths and paths reached from returned links. Do not add a required `rg`
   subprocess to Memex.

Existing Memex stores need a compatibility exception: a valid memory page may
already have the slug `index` or `log`. Such a page must remain a memory and
block structural-file generation at that path with a visible diagnostic. New
writes can avoid the reserved slug through the existing collision-suffix
behavior. This preserves data while allowing new stores to follow OKF.

Because page titles and descriptions are untrusted, generated indexes must
escape them as inert Markdown text. The generator owns every navigation link
and confines its resolved target to the Memex docs tree; page metadata cannot
mint a link for an agent to follow.

## Fields considered but not selected

- `aliases`: tags and a well-written description can carry acronyms and common
  names. Add aliases only after a measured lexical mismatch remains.
- `para` or `category`: project scope, node type, status, and tags already
  express the useful distinctions without a second taxonomy.
- `summary_layers`: the page body and description provide two layers. More
  generated layers risk fact loss and need separate consolidation evidence.
- automatic `log.md`: useful history must be appended at the time of change;
  synthesizing it from current pages would look complete while omitting prior
  changes. Memex already retains transcripts and page lifecycle timestamps.
- OKF `resource`, `sources`, `generated`, `verified`, and `stale_after`: Memex
  already has narrower source, transcript, harness, confidence, timestamp,
  status, expiry, and validity fields. Adopting the nested OKF v0.2 shapes is a
  separate provenance and interoperability decision, not a search prerequisite.
- `retrieval_instructions`: stored memories are untrusted evidence. Front
  matter must not grant authority or tell an agent which tools to execute.
- embeddings or a graph database: none of the selected behavior requires them.

## Expected effect

This change improves discovery when a query describes a page's purpose but the
same words do not appear in its title or tags. Generated indexes also give an
agent a cheap filesystem map before it invokes recall or spends context on a
body. It will not by itself make an agent form better questions or guarantee
complete task evidence.
