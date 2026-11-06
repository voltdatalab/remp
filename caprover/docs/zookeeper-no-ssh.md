# ZooKeeper: contained SSH-startup hotfix

## Scope

This is a candidate only. It does not authorize publication, a CapRover deploy,
service restarts, data export or a migration. It retains ZooKeeper 3.4.13 and the
audited parent filesystem, bypassing the parent's command that starts sshd.
It also execs the existing foreground ZooKeeper launcher, so Java receives
SIGTERM as PID 1. No packages, users, passwords, paths or data formats change.

The legacy OS/JRE/OpenSSH packages and inherited EXPOSE metadata remain in the
image. This is not a general vulnerability cleanup. No running sshd/listener is
the acceptance criterion. A durable supported-image/Kafka migration is separate.

## Reproducible build

From the repository root:

```sh
DOCKER_BUILDKIT=0 docker build --pull=false --network none \
  --memory 512m --memory-swap 512m --cpu-period 100000 --cpu-quota 100000 \
  -t nucleo-local/zookeeper-no-ssh:20261106 \
  -f caprover/apps/st-remp-zookeeper/Dockerfile \
  caprover/apps/st-remp-zookeeper
python3 -B caprover/scripts/validate-definitions.py
python3 -B caprover/scripts/test-zookeeper-contract.py
```

The base and Kafka fixture images must first be present by the digests in the
Dockerfile/integration script. Their image IDs are checked against the audited
runtime. Legacy builder was explicitly selected for local resource bounds; its
deprecation warning is not suppressed. This does not change daemon settings.

## Explicit isolated integration

```sh
python3 -B caprover/scripts/test-zookeeper-no-ssh.py \
  --allow-isolated-docker-tests --engine-name YOUR_VERIFIED_ENGINE_NAME \
  --candidate nucleo-local/zookeeper-no-ssh:20261106 \
  --report /YOUR_AUTHORIZED_WORKSPACE/isolated-zookeeper-test.json
```

The harness requires fresh UUID-owned volumes and an internal bridge, publishes
no ports, grants no host mounts/socket/privileged access and never joins a
CapRover overlay. Temporary objects are label-checked before removal. The daemon
and Docker storage are shared with the test host, not a VM isolation boundary.
ZooKeeper is limited to 512 MiB and one CPU, Kafka to 768 MiB and one CPU, with
no swap allowance above those limits. The control runs network-none and is
removed before Kafka starts. At least 8 GiB available RAM and 20 GiB disk are
required before the rehearsal. No real data or native app configuration is used.

Checks cover: original-image negative control; no SSH process/listener in the
candidate; ZooKeeper startup/version; Java PID 1; actual fixture create/read;
Kafka 2.8.1 connect/produce/consume; SIGTERM without OOM/forced kill; container
replacement retaining BOTH data and configuration; Kafka recovery; exact
fixture-resource absence after cleanup. The tiny stdlib client speaks only
connect/create/get/close for UUID-restricted disposable nodes and derives its
address from its own labelled fixture container. It is not an administration
client and has no production CLI.

An early CLI experiment did not establish verified readback (a session-establishment
race was a hypothesis, not a proven root cause), and the parent
image has a JRE but no javac. The final client requires neither a compiler nor
network package installation. The parent config directory is UID 501:GID 50;
tests drop all capabilities and add only DAC_OVERRIDE for ZooKeeper's inherited
config edits. Real deployment currently has Docker's default capability set.
Do not chmod existing production volumes to satisfy the fixture.

## Deployment method and acceptance gates

The native GitHub Method 3 remains the method: same repository and app-specific
captain-definition location. This candidate changes its source from a floating
imageName to dockerfilePath in this repository. It causes CapRover to build the
small derivative from the pinned parent; it does not use a CLI/tarball deploy or
require publishing a separate registry image.

The installed native loader resolves dockerfilePath AND the Docker build context
relative to the directory containing captain-definition, not the repository root.
Keep Dockerfile and its COPY source beside this app's definition. Parent-directory
dockerfilePath traversal is explicitly rejected by the native loader. The contract
tests cover this layout; root-context-only builds do not qualify Method 3 paths.

Before a separately approved reversible branch swap:

1. Revalidate current app/native/runtime definition, parent bytes, entrypoint,
   data and configuration volumes, Kafka dependency and app health.
2. Preserve BOTH the explicit data volume and anonymous configuration volume,
   with consistent acquisition and isolated recovery proof. The fixture test
   proves persistence through replacement, NOT recovery of a real backup.
3. Seal the candidate and prepare a rollback branch/definition referencing the
   original image by digest:
   `wurstmeister/zookeeper@sha256:7a7fd44a72104bfbd24a77844bad5fabc86485b036f988ea927d1780782a6680`.
   Returning to a floating imageName on the old branch alone is not immutable
   rollback. Preserve the original native settings, both volume bindings and
   Kafka state. Merely caching the old image is not a recovery certificate.
4. Approve the exact branch/image, temporary coordinator interruption and
   rollback policy. Never swap volumes to empty directories to get healthy.
5. After authorized deploy, verify Java/ZooKeeper, no SSH, metadata parity,
   Kafka reconnection and existing consumer health. Event-injection tests on
   real apps require separate scope; the rehearsal sends only fixture messages.
6. On failure, restore the pinned original artifact and preserved configuration
   and state, then verify consumers. Availability rollback reintroduces SSH and
   is not remediation of the original risk.

Do not publish this branch until its native deploy binding and all repository
workflow triggers have been rechecked; a push can have operational effects.
