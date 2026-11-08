# V2 publication and delivery audit

Feature branch only: `feat/router-v2`. Main remains `76e2463aa8f13bba20d43350886e761da2e100be`.
No merge, release, license or repository-visibility change is authorized here.

## Source and archive

The candidate `f82b7023b86f9ce8bdc007c92c6b565a12779a89` descends from the
sanitized public base. A reachable-history scan covered all six feature commits
through that candidate and 220 unique tracked text blobs, checking private host
paths and credential patterns. Only the auditor's own literal patterns were
excluded. The private development repository/history was not used for publication.

Explicit archive allowlisting, secret/path scanning, documentation link/SVG tests,
round-trip packaging and manifest checks pass. Images were visually inspected;
all 44 video frames were decoded independently. Reports/SVGs also regenerate
byte-identically from the extracted source archive without Git history. Checksums
are integrity evidence, not signed provenance attestations.

## Public media verification

The immutable candidate URL downloaded byte-for-byte equal to the reviewed local
MP4: 423,653 bytes, SHA256
`8f51cfc164c7afd7fc5b4f846844c4fccff0d1b6bf382a02197475bc2df79022`.
README uses that immutable URL. The film is 44 genuine browser stills targeted at
1 Hz, encoded 1 fps / 44 seconds / 1440x1300 H.264, without audio. It is sampled
live footage, not continuous full-frame-rate recording. Every source frame and
actual capture time is retained; no DOM or snapshot timestamps were synthesized.

## GitHub-rendered README

Inspected the actual public feature-branch rendering. Every article image loaded,
including both measured charts, ownership diagram and live poster. At 390px there
was no horizontal page overflow; long SVG detail remains available by opening the
full-resolution asset. [Mobile](qa/v2-publication/mobile.png) and
[desktop](qa/v2-publication/desktop.png) are actual rendered GitHub captures.
Performance regressions and the experimental/default distinction remain visible.

## Delivery boundaries

31 Rust tests (including native Linux), 66 Python tests, strict Clippy/Linux ABI,
formatting, JavaScript/DOM, shell and privacy/packaging gates pass. The actual live
current/stale/recovery/offline verifier passed; see [evidence](LIVE-V2-DEMO.md).
No repository CI workflow was added or paid service enabled. Owner PR review is
separate from these local/native gates and does not authorize merging.

VM stopped; owned namespaces, helpers, private live directory, localhost viewer
and capture tab were cleaned. Wider OS fault qualification, isolated steady fsync
cost, per-worker CPU and AF_XDP remain explicitly unverified/unimplemented.
