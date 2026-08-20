# W1 — Read-only External Observation

W1 follows one rule: the conversation model does not get Internet access; the
Home performs one application-owned observation and gives the local model only
bounded, normalized, untrusted evidence.

## Runtime boundary

- default policy: `explicit`;
- default provider: `DDGSWebSearchProvider`;
- provider backend: DDGS metasearch transport `auto`;
- no API key, paid provider, background traffic or startup availability call;
- no Web Fetch, images, videos, extraction, MCP/API server or retry loop;
- maximum one DDGS call in W1, five sources and 5000 external-context characters;
- `BREAKING` uses `news()`, other freshness requirements use `text()`;
- the main `ModelRequest` remains `LOCAL_ONLY` with `tools=False`.

`ddgs` is a community metasearch dependency, not an official DuckDuckGo API.
Timeout, rate-limit and provider errors therefore become controlled unavailable
or failed observations and never break the conversation runtime.

## Source opening

The renderer never receives a source URL. It sends only `observation_id` and
`source_id`; the application resolves a previously saved HTTPS URL and opens it
in the system browser.

## Manual live smoke

The live smoke is opt-in and never runs in normal CI:

```powershell
$env:MASHA_RUN_DDGS_SMOKE = "1"
.\.venv\Scripts\python.exe -m pytest -s tests\test_ddgs_live_smoke.py
```

It performs three bounded English/Russian queries against the `auto` backend,
requires at least one real result set and prints only normalized evidence.
