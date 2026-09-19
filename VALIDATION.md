# Local deployment preparation check

Checked on 19 September 2026:

- 25 tests passed: 14 climate API tests and 11 deployment/snapshot tests.
- Private GitHub releases use the authenticated API. Tests confirm credentials
  are stripped from redirects, are restricted to api.github.com, and HTTPS is
  required for redirects.
- The Vercel handler returned a healthy status, 160 stations and a complete
  365-day Bucharest-Băneasa 2025 response using the prepared snapshot.
- Both release attachments were decompressed through the build script and
  matched the source databases' pinned SHA-256 checksums.
- Corrupt and oversized test snapshots were rejected without replacing an
  existing file; temporary output was removed.
- Invalid and ambiguous routes were rejected; source/database paths were not
  served by the API handler.
- Both frontend JavaScript files passed Node syntax checks. The WxProbs image
  credits are retained in the two shared PNG/SVG export paths.

This verifies local preparation. It does not include a remote GitHub upload,
Vercel build, Large Functions eligibility check, or cloud performance test.
Those happen when the owner follows DEPLOY.md. No account credentials are
included in this package. Private release downloads require a read-only token
in the Vercel environment.
