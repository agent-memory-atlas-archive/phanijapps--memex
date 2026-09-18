# ADR-0003: Use one LLM port with API and harness providers

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Consolidation needs an LLM, but ordinary memory operations do not. The original
design considered separate HTTP clients for individual local and remote
providers. That would duplicate request, error, configuration, and test
behavior while still failing to cover the many services that implement an
OpenAI-compatible API. Installed coding harnesses already have model access,
credentials, and billing that users may prefer to reuse.

## Decision

Expose one application-level `LLMClient` port.

Use the official OpenAI Python SDK for OpenAI-compatible HTTP providers,
selected through provider defaults or an explicit API base. Support Claude
Code, Codex, and pi as consolidation providers through their non-interactive
CLI modes behind the same port.

Do not import or initialize an LLM client for write, recall, forget, transcript,
backup, restore, status, or verification operations. Consolidation remains
explicit or opt-in and degrades to a partial report on provider failure.

## Consequences

- OpenAI, Ollama, LM Studio, OpenRouter, and compatible endpoints share one
  maintained client path.
- Harness providers can reuse a user's existing model access without adding API
  credentials to Memex configuration.
- Provider-specific behavior stays behind one port and can be tested with a
  fake client.
- The OpenAI SDK is a declared package dependency even though core memory
  operations do not import it at runtime.
- Providers with incompatible APIs require either a port implementation or a
  compatibility layer; they are not supported by adding one-off logic to the
  facade.

## Alternatives considered

- **Hand-written client per provider:** rejected because it duplicates protocol
  and failure handling.
- **OpenAI-compatible endpoints only:** rejected because it prevents users from
  reusing installed harness credentials and billing.
- **LLM calls on every write or session:** rejected because deterministic,
  local memory operations must remain useful without a model.
