# Architecture and feasibility

## Existing solutions preflight
smoltcp is a maintained standalone TCP/IP endpoint stack (Rust 1.91+, project README inspected 2026-11-06); it does not provide the requested small transparent IPv4 forwarding+SNAT dataplane. rust-tun 0.8 provides maintained cross-platform TUN access but automatically manipulates routes on some platforms; Linux-only attachment to explicitly precreated interfaces avoids host side effects. Prefer libc for minimal Linux ABI or tun crate if its attach-only semantics are proved. A custom bounded UDP translation core is appropriate for the explicitly requested implementation, not a replacement general TCP/IP stack.

## Dataplane
Two precreated Linux IFF_TUN|IFF_NO_PI devices (inside/outside). Kernel endpoint routes deliver packets into TUN; the program alone reads, validates, translates and writes the opposite TUN. Kernel ip_forward is disabled in the integration router namespace and no iptables/nft NAT is used. Longest-prefix route lookup chooses inside/outside egress; ingress/egress policy rejects reflection/hairpin and spoofed inside sources. IPv4 version/IHL/length/header checksum and UDP length/checksum are validated before mutation; TTL <=1, IPv4 options, fragments including MF/offset/reserved bits, non-UDP, multicast/broadcast, and malformed packets are explicit drops. Decrement TTL, rewrite IPv4/UDP checksums. No ICMP generation in MVP; TTL and MTU failures drop with counters.

## NAT
Endpoint-dependent key (internal address/port, remote address/port), external address and unique bounded port allocation; reverse traffic requires exact remote tuple and allocated external port. Monotonic idle expiry, configured maximum flows, port exhaustion fails closed, bounded routes/counters. Invalid and rejected inbound packets never refresh mapping state. Translation precedes return-route selection for replies; outbound route selection precedes SNAT. No kernel forwarding or proxy sockets in dataplane.

## Runtime and safety
Portable pure Rust packet/routing/NAT core; Linux runtime polls two TUN descriptors and reports counters. Practical explicit CLI, no automatic host network configuration. The initial MVP deferred the UI; the authorized read-only extension is specified below. Isolated integration script creates ephemeral namespaces and TUN endpoints, executes controlled UDP echo with sender and server in separate namespaces, asserts observed external source and reply delivery and TTL, then stops program and requires path failure. Cleans up only its named resources.

## Namespace attachment refinement (before harness implementation)
The CLI also accepts inherited, already attached TUN descriptors. This permits the
inside TUN to reside in the client namespace and the outside TUN in the server
namespace while the forwarding process stays in a third namespace. The isolated
harness opens precreated TUN devices in their respective namespaces, returns to
the router namespace, and execs the router with those descriptors. Runtime checks
TUNGETIFF, distinct device identities, read/write access and nonblocking mode.
No veth-to-TUN kernel forwarding is required; each endpoint sends directly into
its TUN, and only this process transfers packets between descriptors. The normal
name attachment mode drops all capabilities before TUNSETIFF, preventing device
creation even across a preexistence-check race. Inherited descriptors transfer
ownership to the CLI and must be distinct and at least 3.

## Implemented structure and present evidence
`src/lib.rs` contains the OS-independent packet parser/checksums, bounded route
lookup, policy, port allocator, reverse port map, monotonic expiry and counters.
`src/linux.rs` provides the poll-based CLI adapter through small explicit Linux
FFI declarations with no Cargo dependencies. It supports x86_64/aarch64 Linux;
the `linux-abi-check` feature permits host static analysis only. `scripts/`
contains an opt-in namespace harness and standard-library Python endpoint/setup
helper. The helper passes TUN descriptors; it never forwards UDP on behalf of
the router. Endpoint interfaces have distinct names, and name equality is also
rejected for inherited descriptors as a conservative device-alias check.

Routes are immutable after construction. A BTreeMap indexed by the unique
external port is the reverse mapping; outbound tuple lookup and expiry scan
bounded state. Allocation cycles within the configured port range. Route count
is capped at 128 and flow count at 65,535; receive buffers are fixed-size and
outputs have no unbounded backlog. Drop and total counters saturate. Core
`forwarded` means a forwarding decision, with runtime backpressure accounted
separately as `io_drops`.

The address policy rejects loopback, link-local, 0/8, multicast/reserved space,
and network/broadcast endpoints of all matching configured /1../30 routes.
Directed-broadcast detection requires the relevant configured subnet route.
There is no individual-host authentication, ICMP, packet fragmentation or
protection against delayed UDP datagrams after port reuse. Routing configuration
must reserve the external translation IP and supply the desired return routes.

Portable core tests and static checks pass on the current macOS host. Historical MVP and coordinator-supplied extended live tests passed. See [release status](RELEASE-STATUS.md).

## Authorized runtime observability and extended lab (2026-11-06)

Implemented and verified in the isolated lab: real kernel UDP cases for overlapping longest-prefix
routes, distinct internal addresses sharing a port, separate flow/port limits,
and monotonic expiry with rejected late replies and subsequent allocation.
The existing namespace/TUN topology remains the only forwarding path.

The router optionally emits versioned JSON once per reporting interval and at
shutdown, by create-new 0600 temporary file and atomic rename in a pre-existing
private directory. Snapshots include sensitive internal/remote tuples: use only
task-owned storage. Routes and attached interface identities come from the actual
running configuration/FDs; mappings and counters come directly from the core.
Bound output to 1 MiB, truncate mapping enumeration explicitly, never infer rates.
Snapshot timestamps and running/stopped state distinguish stale and offline data.

A dependency-free Python stdlib dashboard binds only 127.0.0.1. Exact Host and
Origin checks, GET-only allowlisted static/API routes, no CORS, strict CSP, bounded
reads and subprocess deadlines protect the localhost boundary. Optional guest
reads use an argv-only fixed limactl shell command for one task-owned snapshot;
no arbitrary path or command comes from HTTP. UI uses textContent, semantic tables,
keyboard controls, responsive CSS and no external assets. No telemetry means
explicit offline state; old telemetry is stale. No fabricated samples.

Demo lifecycle owns namespace processes and private artifacts, supports retained
traffic for coordinator QA, and provides explicit stop/cleanup. Host orchestration
copies only allowlisted task files, with no mounts, installs or host networking.
Release packaging uses an explicit file allowlist and audits secrets/internal
paths; historical local evidence remains outside the release archive. Repository name `tczartoryski/userspace-router` and private visibility are owner-approved. Licensing remains pending; no license grant is implied.
