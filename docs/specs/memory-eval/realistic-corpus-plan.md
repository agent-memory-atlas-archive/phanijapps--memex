# Realistic Synthetic Corpus — Design Plan

**Status:** planning only. Builds on `docs/specs/memory-eval/plan.md` phase 1.

## Problem with the current corpus

The existing generator produces 4 templates (entity/preference/procedure/summary) from a 28-tool vocabulary. At 10K+, it degenerates: 400 near-identical "Ansible configuration" pages. Real agent memory is nothing like this.

A real coding agent's memory after a month of work looks more like a project wiki written by someone who was there — architecture decisions with reasoning, debugging discoveries with root causes, API quirks, infrastructure topology, team conventions, temporal changes ("we used to X, now we Y"), and cross-referenced knowledge that links to other knowledge.

## What real agents actually store (evidence-based)

From the transcripts captured in `~/.memex/transcripts/` and from Hindsight/Letta research:

| Category | Example from real usage | Frequency |
|---|---|---|
| Architecture decisions | "The engram adapter composes semantic and lexical retrieval behind store traits" | High |
| Debugging discoveries | "The `no such column: w.status` error was caused by initialize() stamping schema v2 on a v1 table" | High |
| API contracts | "Codex rollouts carry session_id, timestamp, cwd, cli_version, git in session_meta" | Medium |
| Infrastructure facts | "The staging cluster has 3 nodes, prod has 12, both EKS 1.29" | Medium |
| Team conventions | "Always use uv for Python package management, never pip" | High |
| Temporal evolution | "We used to use MongoDB, migrated to PostgreSQL in March" | Low but critical |
| Cross-references | "The auth flow depends on the JWT rotation policy in [[auth-jwt-rotation]]" | High |
| Domain knowledge | "FTS5's bm25() returns lower=better; cross-encoders return higher=better" | Medium |
| Session episodic | "In the session on 2024-03-15 we migrated the payment service from Python to Go" | High |
| Ambiguous/contradictory | "User said they prefer tabs" (later: "User said they prefer spaces") | Low but discriminative |
| Performance insights | "The N+1 query in user-listing costs 2.3s at 10K users" | Medium |
| Security constraints | "Never log PII, use the redaction middleware" | Low but critical |

## Corpus design: 8 realistic domains

Instead of one tool-preference domain, generate from 8 distinct knowledge domains that mirror what a coding agent encounters across a multi-project career:

### Domain 1: Project Architecture (25%)
**Source pattern:** Kubernetes design docs, PostgreSQL internals, Django architecture.

```
Title: "{service} {component} design"
Body: "The {service} uses {pattern} for {concern}.

The {component} is responsible for {responsibility}. It receives
{input_description} and produces {output_description}.

Key invariants:
- {invariant_1}
- {invariant_2}

Trade-offs: we chose {pattern} over {alternative} because {reason}.
This decision was made in the {quarter} architecture review.

Related: [[{related_service}]], [[{shared_infra}]]"
```

**Realistic values for service names:** Use real open-source project naming conventions:
- Services: `ingest-api`, `query-engine`, `auth-gateway`, `stream-processor`, `index-builder`, `notification-relay`, `scheduler`, `config-service`
- Patterns: `event sourcing`, `CQRS`, `circuit breaker`, `saga`, `retry queue`, `bulkhead`, `sidecar`
- Concerns: `fault tolerance`, `data consistency`, `backpressure`, `service discovery`, `rate limiting`
- Alternatives: `CRUD with transactions`, `direct calls`, `synchronous HTTP`, `shared database`

### Domain 2: Debugging Discoverories (20%)
**Source pattern:** GitHub issues, incident postmortems, debugging session transcripts.

```
Title: "{symptom} in {context}"
Body: "When {trigger_condition}, the {system} exhibits {symptom}.

Root cause: {root_cause}. The issue manifests in {code_location}.

Fix: {fix_description}. This was discovered during {discovery_context}.

The underlying principle: {principle}. Watch for this pattern when
{similar_situation}.

Session: [[{session_reference}]]"
```

**Realistic values:**
- Symptoms: `intermittent 500 errors`, `memory leak after 48 hours`, `race condition during deploy`, `connection pool exhaustion`, `duplicate event delivery`, `clock skew breaking TTL checks`
- Root causes: `the poll interval was 30s not 3s`, `the goroutine wasn't releasing the connection`, `the retry didn't account for clock drift`, `the index wasn't rebuilt after migration`
- Systems: `kafka consumer`, `postgres connection pool`, `kubernetes health check`, `redis cache layer`, `grpc interceptor`

### Domain 3: API Contracts & Schemas (15%)
**Source pattern:** OpenAPI specs, gRPC proto files, internal API docs.

```
Title: "{endpoint} API contract"
Body: "The `{method} {path}` endpoint {purpose}.

Request: {request_schema}
Response: {response_schema}
Errors:
- `{status_1}`: {error_condition_1}
- `{status_2}`: {error_condition_2}

Rate limit: {rate_limit}. Idempotency: {idempotency_note}.

This contract changed in {change_note}. See [[{breaking_change_ref}}]]."
```

**Realistic values:**
- Endpoints: `POST /v1/users`, `GET /v1/sessions/{id}`, `PATCH /v1/deployments/{id}`
- Purposes: `creates a user`, `retrieves session metadata`, `triggers a canary deploy`
- Schemas: `{"id": "uuid", "email": "string", "created_at": "ISO8601"}`

### Domain 4: Team Conventions (12%)
**Source pattern:** CONTRIBUTING.md, team wikis, code review feedback.

```
Title: "{area} convention: {specific_rule}"
Body: "In this project, always {convention}. Never {anti_pattern}.

Reason: {reasoning}. This was established after {incident_or_review}.

Example:
```python
{code_example}
```

Exception: {exception_condition}. When in doubt, {default_action}."
```

**Realistic values:**
- Conventions: `use dataclasses over dicts at boundaries`, `prefer keyword-only for optional args`, `validate at the boundary, trust internally`, `prefer composition over inheritance`
- Anti-patterns: `pass raw dicts between layers`, `catch bare Exception`, `use `type: ignore` without a comment`

### Domain 5: Infrastructure & Deployment (10%)
**Source pattern:** Terraform configs, Kubernetes manifests, runbooks.

```
Title: "{environment} {resource} configuration"
Body: "The {environment} {resource} is configured as follows:

- {config_1}
- {config_2}
- {config_3}

Constraints: {constraint_1}. {constraint_2}.

This was last changed in {change_date}. Runbook: {runbook_ref}."
```

**Realistic values:**
- Environments: `staging`, `production`, `development`, `edge`
- Resources: `cluster autoscaling`, `database replication`, `CDN cache rules`, `DNS failover`
- Constraints: `max 3 concurrent deploys`, `zero-downtime required`, `PITR window 7 days`

### Domain 6: Domain-Specific Knowledge (8%)
**Source pattern:** technical documentation, RFC explanations, design discussions.

```
Title: "{concept} explained"
Body: "{concept} is {definition}.

In practice, this means:
1. {practical_implication_1}
2. {practical_implication_2}

Common misconception: {misconception}. The correct understanding is
{correction}.

This matters for {why_it_matters}.

Related concepts: [[{concept_1}]], [[{concept_2}]]"
```

**Realistic values:**
- Concepts: `idempotency keys`, `eventual consistency`, `CAP theorem trade-offs`, `LSM-tree compaction`, `WAL replay`, `vector clocks`, `consistent hashing`, `backpressure signals`
- Misconceptions: "eventual consistency means data is lost" (correction: it means convergence)

### Domain 7: Temporal Evolution (5%)
**Source pattern:** changelogs, migration guides, decision reversals.

```
Title: "{change_type}: {from} to {to}"
Body: "As of {date}, this project {change_description}.

Previously: {previous_state}. The migration was driven by {motivation}.

Migration notes:
- {migration_note_1}
- {migration_note_2}

The old approach is kept for {compatibility_note} until {deprecation_date}."
```

**Realistic values:**
- Changes: `migrated from MongoDB to PostgreSQL`, `switched from REST to GraphQL`, `replaced Celery with Kafka streams`, `moved from monolith to services`
- Motivations: `operational complexity`, `team familiarity`, `performance at scale`, `vendor lock-in`

### Domain 8: Cross-Project & Session Knowledge (5%)
**Source pattern:** episode transcripts, project summaries, multi-project agents.

```
Title: "Session {date}: {task_summary}"
Body: "In this session, the agent {session_summary}.

Key decisions:
- {decision_1}
- {decision_2}

Knowledge stored: {knowledge_refs}. The conversation covered
{topic_areas}.

Transcript: {transcript_ref}"
```

**Realistic values:**
- Tasks: `debugged the auth timeout in production`, `implemented the new notification service`, `migrated the CI pipeline from Jenkins to GitHub Actions`
- Topic areas: `authentication, rate limiting, monitoring`

## Query patterns that match real agent usage

Real agents don't search for "ansible". They search for:

| Query pattern | Example | What it tests |
|---|---|---|
| **Problem-first** | "why are pods getting evicted" | Matching symptoms to root cause |
| **Action-needed** | "how to rotate the API keys" | Procedure retrieval under time pressure |
| **Context-recall** | "what database does the payment service use" | Entity attribute lookup |
| **Constraint-check** | "what's the rate limit on the user API" | Specific fact retrieval |
| **Pattern-match** | "idempotency" | Concept lookup |
| **Decision-trace** | "why did we switch from Celery" | Temporal evolution |
| **Cross-reference** | "what depends on the auth gateway" | Link traversal |
| **Multi-hop** | "who owns the service that handles payments" | Chained knowledge |
| **Ambiguous** | "the deployment thing" | Vague query, BM25 must still surface it |
| **Contradictory** | "tabs or spaces" | Must find both, rank by recency |

## Implementation shape

```python
class RealisticCorpusGenerator:
    """Generates diverse, real-world-shaped memories."""

    DOMAINS = [
        ArchitectureDomain(weight=0.25),
        DebuggingDomain(weight=0.20),
        APIDomain(weight=0.15),
        ConventionDomain(weight=0.12),
        InfrastructureDomain(weight=0.10),
        DomainKnowledgeDomain(weight=0.08),
        TemporalEvolutionDomain(weight=0.05),
        SessionKnowledgeDomain(weight=0.05),
    ]

    def generate(self, size: int) -> CorpusResult:
        # Each domain generates its share
        # Cross-references created between domains
        # Temporal evolution creates BEFORE/AFTER pairs
        # Session knowledge links to architecture/debugging
        ...
```

## What this buys us

| Current corpus | Realistic corpus |
|---|---|
| 28 tool names | 8 knowledge domains × 50+ entities each |
| 4 body templates | 8+ body structures with code blocks, schemas, config lists |
| Uniform query patterns | 10 query patterns (problem-first, action-needed, constraint-check, etc.) |
| No cross-references | [[wiki-links]] between domains |
| No temporal data | BEFORE/AFTER evolution pairs |
| No contradictions | Deliberate contradictions for discrimination testing |
| No code blocks | Embedded code examples |
| No schemas | API contract details |
| No infra topology | Cluster configs, deployment rules |
| 0% real-world coverage | Matches actual agent memory patterns from session transcripts |

## Reference sources for templates

The templates should draw from real project documentation patterns:

| Source | What to extract |
|---|---|
| [Kubernetes docs](https://kubernetes.io/docs/concepts/) | Architecture component descriptions, design rationale |
| [PostgreSQL internals](https://www.postgresql.org/docs/current/internals.html) | System catalog knowledge, WAL, MVCC explanations |
| [Go project layout](https://github.com/golang-standards/project-layout) | Directory conventions and their reasoning |
| [12-Factor App](https://12factor.net/) | Deployment and config management principles |
| [AWS Well-Architected](https://aws.amazon.com/architecture/well-architected/) | Operational excellence patterns, failure modes |
| [Google SRE Book](https://sre.google/sre-book/) | Incident response, monitoring, alerting patterns |
| [Django documentation](https://docs.djangoproject.com/) | ORM patterns, middleware, authentication flows |
| Real GitHub issues | Bug reports, debugging narratives, resolution patterns |

These are canonical references whose structure (not content) informs the synthetic templates. The templates should feel like they were written by an agent who was actually debugging, deploying, and reviewing code.

---

## Results (v0.2.5, seed 42, BM25-only)

| Corpus | Recall@1 | Recall@5 | Recall@10 | MRR | Avg Latency |
|---|---|---|---|---|---|
| 1,000 realistic | 53.0% | 78.4% | 88.6% | 0.632 | 6.1ms |
| 10,000 realistic | 49.5% | 61.5% | 68.9% | 0.546 | 20.8ms |

### By difficulty (10K)

| Difficulty | n | R@5 | R@10 | MRR |
|---|---|---|---|---|
| easy (title-match) | 6,300 | 76.7% | 84.7% | 0.687 |
| medium (attribute) | 8,700 | 75.3% | 82.0% | 0.672 |
| hard (reasoning) | 5,800 | 24.2% | 32.0% | 0.205 |

### Findings

1. **BM25 handles title-match and attribute queries well** (82–85% R@10 even at 10K with ~17 near-duplicates per topic).
2. **Hard queries expose the semantic gap**: "why event sourcing instead of direct synchronous calls" requires matching the page that *reasons about* that trade-off — the pattern/alternative words appear once in the body while competing pages match on title. R@10 collapses to 32%. This is the strongest evidence yet for A1 (RRF fusion: body BM25 + title BM25) and A2 (importance/recency boosts).
3. **Ranking, not finding, is the bottleneck**: R@10 88.6% vs R@1 53.0% at 1K — the right page is in the top 10 but pure lexical scoring leaves it mid-list.
4. **Scale cost is linear**: 6.1ms → 20.8ms avg for 10× corpus; p99 stays under 50ms.

### Ground-truth design note

Expected slugs expand to *all pages of the same topic* (e.g., every
`stream-processor-rate-limiting-design*` copy). Exact-slug matching was
unfair to any ranker when a topic has near-duplicate pages: any duplicate
is an equally correct answer.

### Location note

The eval tooling lives outside the shipped package, in the repo-root
`eval/` directory (`eval/corpus.py`, `eval/realistic.py`, `eval/runner.py`,
`eval/run.py`). It is developer benchmarking, not product surface:

    uv run python -m eval.run corpus --realistic --size 10000 --seed 42
    uv run python -m eval.run retrieval --realistic --size 10000

The `memex` CLI no longer exposes an `eval` subcommand; `src/memex/`
contains only product code.
