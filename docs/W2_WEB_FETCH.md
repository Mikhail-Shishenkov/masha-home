# W2 — Safe Web Fetch

W2 keeps the boundary from W1: the conversation model never receives network
authority. The Home validates and reads one page, saves bounded evidence, then
passes only extracted text as separate untrusted external information.

## Lifecycle

- Explicit URL: one public HTTPS `GET`.
- `прочитай S1`: one source from the latest W1 search in the same conversation.
- `найди … и прочитай`: one DDGS search followed by exactly one selected page.

There is no AUTO/background/task-scoped fetch, recursive browsing, browser
automation, JavaScript, cookie/session reuse, credentials, forms, downloads,
PDF, images, audio or video.

## Transport boundary

`SafePublicHttpsFetcher` accepts only HTTPS on port 443. It rejects URL
credentials, localhost/local names and every non-global DNS result. It resolves
A/AAAA records before every hop and rejects a mixed public/private answer set.
The actual TLS connection uses a previously validated numeric address while the
original hostname remains SNI, certificate-validation and Host-header truth.

Redirects are manual (at most three) and each target is fully revalidated.
Proxy environment variables are never read. TLS verification is always on.
Requests use `Accept-Encoding: identity`. If a public server nevertheless sends
one encoding, Home decodes only `gzip` or `deflate` itself with Python stdlib:
the encoded network body is capped at 2 MiB, decoding is incremental under the
same deadline, and the decoded representation has its own 2 MiB hard cap.
`br`, `zstd`, and multiple content encodings remain unsupported. Bodies are
held only in memory.

## Evidence and extraction

Only HTML, plain text and JSON are accepted. HTML is fetched by the safe
transport and then extracted locally through `trafilatura.extract`; its network
helpers are never used. Extraction receives only the bounded decoded HTTP
representation. `content_sha256` is the SHA-256 of that decoded representation,
while `raw_bytes_read` remains the encoded network byte count. No raw HTML,
compressed body, cookies, headers, TLS material or DNS data is written to the
external journal. Extracted text is capped at 8,000 characters.

The page is untrusted evidence, not an instruction. It cannot launch another
Skill or change Memory, Identity, permissions or the user’s task. A response may
say that Masha read a page only if the same turn has a completed `WEB_FETCH`
receipt.

## Manual live smoke

This test never runs in CI. It exercises a direct Python.org fetch and one DDGS
search followed by a single fetched result:

```powershell
$env:MASHA_RUN_W2_FETCH_SMOKE = "1"
.\.venv\Scripts\python.exe -m pytest -s tests\test_web_fetch_live_smoke.py
```
