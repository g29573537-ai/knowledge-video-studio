# Semgrep scan report (branch: security/semgrep-mcp)

Command:
`semgrep scan --config auto .`

Result: 7 findings.

1. `.github/workflows/tests.yml:9` — mutable action tag `actions/checkout@v4`
2. `.github/workflows/tests.yml:12` — mutable action tag `actions/setup-python@v5`
3. `.github/workflows/tests.yml:15` — mutable action tag `actions/setup-node@v4`
4. `narration_video/voice.py:29` — dynamic urllib use (OmniVoice base URL)
5. `scripts/install.py:75` — dynamic urllib use (fixed Node download URL)
6. `scripts/install.py:77` — dynamic urllib use (fixed SHASUMS URL)
7. `scripts/install.py:86` — tarfile extractall traversal (mitigated by `filter="data"`)

No secrets were found by Semgrep. `.env` is ignored by Git and was not part of the committed scan context.

Recommendation before enabling in the permanent pipeline:
- pin GitHub Actions to immutable commit SHAs;
- keep urllib calls limited to fixed trusted URLs or migrate to `requests`;
- retain `filter="data"` for tar extraction and add an explicit path check if the source archive can change.
