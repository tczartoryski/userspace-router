# Userspace Router

Real IPv4/UDP forwarding and endpoint-dependent SNAT through precreated Linux TUN
interfaces. Kernel forwarding/NAT does not perform the dataplane. No dependencies.
Repository: `tczartoryski/userspace-router` (private, owner-approved). License remains pending owner decision. No license grant.

Portable checks: `cargo test --locked --offline` and
`python3 -m unittest discover -s scripts -p 'test_*.py'`.
Linux requires an explicitly approved isolated environment with existing iproute2,
Python 3, Rust and /dev/net/tun. Never run namespace setup on a shared host.
Inside the approved Ubuntu lab: `bash scripts/guest-demo.sh` runs both extended
real-packet suites. `bash scripts/guest-demo.sh --retain` also retains real traffic
for QA until Ctrl-C cleans up namespaces and processes.

On the approved Lima host, `python3 scripts/demo.py` copies only the release
allowlist, starts the guest demo and localhost dashboard, and stops the VM on exit.
Use http://127.0.0.1:8765. Ctrl-C or SIGTERM stops and cleans up.
The dashboard is read-only; snapshots contain sensitive network tuples, hidden
by default. Stale and offline snapshots are labeled. No public listener or CDN.

See docs/ARCHITECTURE.md, docs/RELEASE-STATUS.md, docs/DEMO-VIDEO.md and
[architecture diagram](docs/architecture.svg). No production/throughput claim.
