# Query-aware Memory Retrieval v0.2

## Runtime boundary

Ordinary conversation follows this application-owned order:

```text
current utterance
  -> explicit reflection/capability routing
  -> MemoryRetrievalRequest(query, project_id, limit, lens, budgets)
  -> status/scope filtering
  -> query-aware scoring and threshold
  -> bounded WorkingMemory
  -> ConversationContextCompiler
  -> LOCAL_ONLY ModelRequest
```

The retriever reads the existing validated repository view. It never gives the
model SQLite access, never reconstructs memory from conversation history, and
never performs a mutation. A missing result means only that a record was not
selected for this bounded context.

## Lenses and searchable fields

- `general`: Fact, Decision, Commitment, Episode, RelationshipMemory and
  ContinuityState. Reflection is excluded and shared records are never forced.
- `shared_continuity`: RelationshipMemory and readable open ContinuityState
  only.
- `masha_perspective`: MashaReflection only.

Searchable text contains only the user-meaningful fields specified for each
record type: fact subject/key/value; decision title/decision; commitment text;
episode title/summary; relationship title/content; readable current focus and
open follow-up topic/summary/reason; reflection text/meaning. IDs, audit fields
and storage metadata are excluded.

Russian-aware normalization is shared with conversational memory reference
matching. It case-folds, normalizes `ё`, punctuation, underscores and hyphens,
removes conversational stop words, and applies the existing conservative suffix
stemming strategy.

## Deterministic score

For a specific query:

```text
lexical =
    0.68 * weighted_query_coverage
  + 0.12 * bounded_record_coverage
  + 0.15 * ordered_phrase_coverage
  + 0.05 * distinctive_token_match

total =
    10.00 * lexical
  +  3.00 * optional_semantic
  +  0.55 * stored_or_default_importance
  +  0.30 * recency_bucket
  +  0.25 * lens_scope
  +          controlled_type_signal
```

`optional_semantic` is zero in the shipped configuration. The lexical term is
therefore the dominant production signal. Recency buckets are `1.0` (one day),
`0.66` (seven days), `0.33` (thirty days), then zero. Type base signals are
Decision `0.15`, Episode `0.10`, Fact/Reflection `0.06`,
RelationshipMemory/ContinuityState `0.05`, and Commitment `0.03`. A query that
explicitly asks what was decided/chosen or discussed adds a bounded `0.25`
type-intent tie-breaker to Decision or Episode respectively. It cannot rescue a
lexically unrelated record.

The lexical pass thresholds are `0.30` for `general` and `0.26` for the two
special lenses. An optional semantic scorer may pass at `0.72`. Broad explicit
shared-history or perspective questions use their already restricted lens as
the candidate boundary and allow low-specificity results. A specific no-match
query returns an empty list; there is no best-available or fill-to-limit
fallback.

Ordering is deterministic: total score descending, meaningful timestamp
descending, record type, then record ID.

## Bounds and trace

Ordinary conversation defaults to six records, a 3,600-character total memory
budget, and a 2,000-character per-record budget. The estimate serializes the
same semantic payload shape compiled into Memory Context and adds a small fixed
wrapper allowance. A record that does not fit is skipped; selection continues
with the next ranked record until the record limit or budget is exhausted.

`retrieve_with_trace` exposes ID/type, total, lexical/semantic/importance/
recency/lens/type components, threshold outcome, selection state, size estimate
and deterministic reasons. Normal Home conversation receives only compiled
records and short grounding reasons, not the raw score trace.

## Semantic extension and deferrals

No suitable existing local embeddings stack was present. v0.2 therefore adds
no model, dependency, index, remote API or ordinary-turn call. A local-only
batch `SemanticRelevanceScorer` protocol is the extension point; absence,
invalid output or failure produces all-zero semantic scores and deterministic
lexical fallback. A real semantic provider is deliberately deferred.

Memory provenance/category migration is also deferred. Query relevance prevents
unrelated developer records from contaminating ordinary turns, but provenance
should later be represented as data rather than hard-coded content filters.
