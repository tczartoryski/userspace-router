# Publication audit

Audit date: November 7, 2026. Scope: the sanitized checkout at `868a585`,
its two reachable commits (`45f6f54` and `868a585`), and the documentation/package
changes prepared on top. Public visibility is requested after audit; it has not
been verified or changed here. No commit, push, release or deployment was performed.

## Reachable history and source

`python3 scripts/test_documentation.py --audit-history` read every reachable
commit tree and every unique blob: 2 commits, 56 unique blobs, 59 distinct tree
entries. All entries are regular files (including executable scripts); no symlinks,
submodules, GitHub workflows, credential/configuration files or binary archives
were found. The only binary blobs are the 13 unique existing image/movie blobs
at 17 allowlisted media paths. All were scanned for credential/path candidates;
visual content, embedded metadata and movie verification remain with the coordinator.
The helper inventories binary hashes and paths so that review can cover history,
including content no longer present in the current tree.

Text review covered source, scripts, dashboard, documentation, timestamps and
manifests in both revisions, with credential/private-path patterns and contextual
review of account, URL and network literals. No actual secret, personal filesystem
path, private account identifier or real LAN configuration was identified in text.
The two private-path scan candidates are the packaging auditor's own literal
rejection patterns in the two versions of `scripts/package.py`, not exposed paths.
Pattern scanning is heuristic and cannot certify absence of every possible secret.

Both author and committer identities are the intentional public GitHub owner
`tczartoryski`, using `117608669+tczartoryski@users.noreply.github.com`. Both commit
messages and their November 6–7, 2026 timestamps were reviewed. The public repository
name and requested reference repository owner are intentional identifiers.

## Network and runtime literals

`10.0.0.0/24` and its addresses are RFC1918 test fixtures, explicitly configured
inside the isolated namespace harness; they are not evidence of the owner's LAN.
`198.51.100.0/24` is TEST-NET-2 and `192.0.2.2` is TEST-NET-1 test data.
The broader `198.51.0.0/16` route is an intentional overlapping-prefix lab fixture;
that entire /16 is **not** reserved TEST-NET space. It is used only in the isolated
harness. Loopback addresses and port 8765 describe the local dashboard. Unspecified,
link-local, multicast, reserved and broadcast literals exercise rejection policy.
No external service or real LAN endpoint was identified. `evil.example` is a
negative Origin test. Relative user-home Lima tool paths contain no personal name;
`router-lab` and temporary guest staging paths are fixed local lab resource names.
Runtime snapshots can contain sensitive tuples and must remain private.

## Documentation and packaging

The original banner and its provenance are explicit allowlist entries. The README
is preserved byte-for-byte during packaging rather than replaced by a stale embedded
constant. No raw evidence directory sweep was added. The helper checks local Markdown
and HTML image/link targets against the package allowlist and rejects active/external
SVG content. The existing round-trip test verifies identical extracted/repacked
content and SHA-256 manifests, including the aesthetic README.

The existing `MANIFEST.sha256` describes the earlier packaged content. The coordinator
must regenerate publication manifests after final documentation/media review; this
change does not claim that the checked-in manifest already covers these edits.

## Local validation

The updated checkout passed all 17 Rust tests and all 29 Python tests (the existing
27 plus two documentation checks), including archive extraction and repackaging
with identical content/manifests. Rust build output used a separate temporary
location, preserving the preexisting untracked `target/`. `git diff --check` passed.
No live Linux suite or browser acceptance was rerun for this documentation change;
recorded Linux and UI results remain historical evidence with their stated scope.

## Remaining publication gates

No text finding currently requires a private-data owner decision. Licensing remains
an owner decision: no license is selected, no license grant is made and no open-source
license badge is claimed. The coordinator separately reviews all actual media,
GitHub surfaces and browser rendering, regenerates final manifests, and verifies
public visibility after the authorized publication step. This local audit does not
assert that those checks or publication have completed.

## Independent coordinator gate — before visibility change

All 12 actual captured frames and all desktop/mobile/offline images were visually inspected. The view contains only controlled lab fixture routes, interface names, redacted endpoint tuples and genuine counters; no account UI, notifications, personal desktop, private LAN addresses or credentials. Every audited media file was byte-compared with the original inspected capture. The H.264 movie decoded all 12 frames (1280×960, 12 seconds at 1 FPS); extracted first/middle/last frames matched. AVFoundation independently reported one video track, zero audio tracks and zero asset metadata items. Media strings scans found no private-path or credential candidates. No unreviewed historical media version exists in the two-commit baseline.

GitHub review found only main, no tags/releases, issues/pull requests, workflows, Actions artifacts or deployments. Wiki, Pages and Discussions are disabled; forks=0. Description and empty homepage were reviewed. Reachable author/committer metadata uses only the intentional public GitHub handle and GitHub noreply email. No tracked archive exists; packaged source is generated only from the explicit audited allowlist, with extraction/repackaging and SHA-256 verification. The original development repository remains unchanged, clean and without a remote; its raw evidence/history is never part of this repository.

No privacy finding blocks the owner-authorized visibility change. This is a bounded manual/heuristic audit, not a claim of formal secret-free certification. Public visibility and unauthenticated rendering are verified separately after the change.

## Public visibility and README render verification — November 7, 2026

After the full pre-change audit, candidate `2b33e0d0c01ac0cae95e04342301b73a04c77060` preserved the sanitized ancestry: 3 commits, 66 unique blobs and 69 distinct tree entries were inventoried. The only private-path candidates remained the packaging auditor rejection-pattern literals in its three versions. The candidate was pushed without rewriting history; GitHub visibility was then changed to PUBLIC with the owner’s explicit authorization. GitHub metadata confirmed PUBLIC and an unauthenticated HTTPS retrieval of the exact-revision README matched local bytes. No release, tag or deployment was created.

The actual GitHub README was rendered and visually inspected in Chromium at 1440×1000 and 375×812. The original banner, all factual badges and genuine overview capture loaded at both widths. Document scroll widths matched the viewport (1440 and 375); navigation wrapped cleanly on mobile, the Quickstart link navigated to its anchor, and GitHub’s Mermaid architecture rendered without an error. Local Markdown/HTML image-link checks, SVG safety and extracted/repacked README preservation passed. Screenshot evidence is retained separately from source history. The original private development repository was not modified or connected to GitHub.

The final documentation-only follow-up records these observed results and regenerates the package manifest; it introduces no new media or runtime behavior. License remains unselected and no license grant is made.

## Explanatory NAT story publication — November 7, 2026

The owner authorized a more explanatory demo and publication of sanitized code,
documentation and media. Native Codex Sol implemented the collector/UI; the
coordinator ran the real kernel UDP experiment in the existing isolated Ubuntu
ARM64 lab. Passive AF_PACKET captures, both endpoint receipts and final router
counters jointly pass all four checks. Only fixed fixture payloads and
10.0.0.0/24 / 198.51.100.0/24 lab tuples appear in the reviewed observations.
No raw process logs, guest paths, PIDs, credentials or personal files are included.
The original private repository/history remains separate and untouched.

The movie continuously records an actual ephemeral Chromium page rendering those
verified observations. All 13 editorial substages and the finish state were
observed; their captions, highlights and schematic arrows are explicitly
distinguished from observed traffic. Real packet acquisition occurred before
playback. Source VP9 WebM and final H.264 MP4 each decode all 1,427 frames at
25 FPS (57.08 seconds, 1440×900); no time scaling, intermediate-frame invention
or cuts were applied. First/middle/last and key-event decoded frames and each
distinct rendered state were visually inspected. MP4 asset metadata is empty
and there are no audio tracks. The poster is an actual decoded movie frame.
Source recorder logs, task-local compatibility tools and bulk frames stay private.

An explicit source/UI/media package allowlist includes only the four reviewed
story assets. All package text is scanned; old reachable history remains
sanitized. The earlier audit-pattern literal exceptions in scripts/package.py
remain intentional. This bounded manual/heuristic review is not formal
secret-free certification. No license, release, tag, deployment, host-route
change or new dependency installation is part of this publication.
