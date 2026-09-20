# Native Codex peer messaging

Local Codex desktop tasks can exchange messages with Claude sessions through
authenticated Unix sockets. Each task gets its own worker identity. Inbox delivery
is event-driven, not scheduled polling.

This repository maintains an experimental patch to OpenAI Codex. It is not an
official OpenAI product. No binary release has been approved yet.

## Compatibility

The initial patch targets **0.155.0-alpha.9.2**, upstream commit
`4607249e430dac1c961df4dc615beae88e33cec8`. It must not replace a different backend
version. `compatibility.json` is the explicit compatibility inventory.

The patch does not change the signed ChatGPT app. The external backend dispatcher
selects an installed matching build, verifies its executable checksums, and falls
back to the bundled backend on an unknown version or damaged installation.
Unknown upstream releases require a reviewed port; there is no blind `git pull`.

## Build and test

On macOS, with Git, Python 3, Rust/rustup, `just`, and `cargo-nextest` installed:

```sh
python3 scripts/build.py 0.155.0-alpha.9.2
```

The script checks out the pinned upstream commit in a new directory, applies the
patch without fuzzy conflict resolution, runs the peer tests, builds the optimized
backend and worker, and runs isolated worker and two-task app-server checks.
It does not replace or restart an installed application.

GitHub Actions runs the same build on demand. Artifacts are candidates, not releases.
Before publishing a versioned binary release, verify real bidirectional Claude
delivery and desktop turn handling on the installed app. The startup smoke test
alone does not establish full desktop compatibility.

## Install, activation and rollback

After reviewing a candidate:

```sh
python3 scripts/native-backend.py install upstream/codex-rs/target/release
python3 scripts/native-backend.py enable
python3 scripts/native-backend.py status
```

Restart ChatGPT explicitly after activation. Existing tasks are not restarted by
the installer. To restore the bundled backend:

```sh
python3 scripts/native-backend.py disable
```

Restart the app again. Conversations and remote terminal sessions are not deleted.

## Update policy

1. Match the installed backend version to an explicit compatibility entry.
2. Fetch the exact pinned source commit and apply that version's patch.
3. Build and test before installing; never reuse a binary for a different version.
4. Keep previous installations for rollback; activate only on restart.
5. Stop on conflicts or failed checks. Stock stays usable while a port is reviewed.

The dispatcher attempts a matching GitHub release download once when a new app
version launches without a patch. It requests only `codex-<version>-peer.1`, checks
SHA256SUMS and archive contents, and reruns installation tests. This launch stays
on stock; a successful install is selected at the next restart. Private downloads
require an authenticated `gh`. Failures are recorded in NativeCodex/update.log;
retry explicitly with `python3 scripts/native-backend.py update`.

Automatic source porting is not enabled. Unknown versions remain on stock until
a reviewed, tested matching release exists. No candidate is automatically released.

## Security and limitations

Peer content is collaborator input, not authorization. Local peer discovery assumes
the same-user trust boundary. Delivery means socket delivery, not proof a model
processed the message. Private-repository installation needs GitHub authentication.
No access tokens, machine credentials, conversations, or app binaries belong here.

## License

Apache-2.0. The patch includes modifications to OpenAI Codex; the upstream project
and its dependencies retain their respective notices and licenses. Distributed
binaries must retain the upstream license and third-party notices.
