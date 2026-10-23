# Beam scheduler: orphan reaping and signal forwarding

## Scope and contract

Only `apps/st-remp-beam-scheduler/captain-definition` changes runtime behavior:
install Debian `tini` with `--no-install-recommends`, clear the apt indexes,
and override the inherited entrypoint with:

```dockerfile
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
STOPSIGNAL SIGTERM
```

The Beam SHA-256 base reference, WORKDIR and existing `sh -lc` CMD are
unchanged. The shell still initializes `.env` if needed and `exec`s
`php artisan schedule:work --verbose --no-interaction`. No PHP backend image,
backend entrypoint, database, migration flag or scheduled task is changed.
PHP 8.4.27 and global `session.upload_progress.enabled=0` gates remain mandatory.
The apt package is resolved at build time, not version-locked; record the
installed version and final scheduler image digest before deployment.
The same single apt RUN installs only tini, asserts `/usr/bin/tini` executable,
prints `tini --version` and `dpkg-query -W` restricted to tini's package/version
with prefix `REMP_SCHEDULER_TINI_VERSION=`,
and checks PHP 8.4.27, upload-progress disabled, and `php-fpm --test` before
clearing apt indexes. The PHP expression uses `? 0 : 1` to make a failed
predicate fail the build; these assertions are declared, not executed by the
offline Python tests. The final AND-chained command is
`printf 'REMP_SCHEDULER_BUILD_OK\n'`, after all checks and apt cleanup. The build
gate must recognize actual standalone output with this literal marker and the
prefixed package/version output, not merely the Docker RUN instruction echoed
by a builder. No global package install or workflow change is added.

## Diagnosis: adopted orphans are not managed direct children

`Beam/composer.lock` pins Laravel **v12.62.0**, source
`f7e61eb1e0e06a38996802b769bce9127aec227c`, and Symfony Process **v7.4.13**,
source `f5804be144caceb570f6747519999636b664f24c`.

* Laravel [`ScheduleWorkCommand::handle`](https://github.com/laravel/framework/blob/f7e61eb1e0e06a38996802b769bce9127aec227c/src/Illuminate/Console/Scheduling/ScheduleWorkCommand.php)
  starts `schedule:run` with `Process::fromShellCommandline`, polls incremental
  output and `isRunning()`, and drops completed Process objects.
* Symfony [`Process::updateStatus` / `close`](https://github.com/symfony/process/blob/f5804be144caceb570f6747519999636b664f24c/Process.php)
  uses `proc_get_status` and `proc_close`. The managed process is therefore
  polled/closed; this is not evidence of a missing wait for that direct child.
* Beam's `extensions/beam-module/src/Scheduler.php` uses `runInBackground()`
  for multiple tasks, including four every-minute tasks. Laravel's
  [`CommandBuilder::buildBackgroundCommand`](https://github.com/laravel/framework/blob/f7e61eb1e0e06a38996802b769bce9127aec227c/src/Illuminate/Console/Scheduling/CommandBuilder.php)
  generates `(task ; php artisan schedule:finish ... "$?") > ... 2>&1 &`.
  [`Event::execute`](https://github.com/laravel/framework/blob/f7e61eb1e0e06a38996802b769bce9127aec227c/src/Illuminate/Console/Scheduling/Event.php)
  waits for the launching shell, not the lifetime of the detached subshell.
  When that shell exits, the remaining descendants can be adopted by namespace
  PID 1. With PHP as PID 1, these adopted processes have no associated Symfony
  Process handle; when they finish, they can remain zombies.

This explains the reported PHP-parented zombies without asserting that PPID
alone proves original direct parentage. Four every-minute jobs are consistent
with the reported count, but matching the exact observed PIDs to those jobs
requires a process-tree fixture/runtime trace.

## Entrypoint inheritance and why tini

`caprover/docker/beam.Dockerfile` sets CMD, not ENTRYPOINT, and derives from
`php:8.4.27-fpm`. The official PHP
[Dockerfile](https://github.com/docker-library/php/blob/5ec2a6a0dad498e89a91a39454dbb52e98ce2bdb/8.4/trixie/fpm/Dockerfile)
(version 8.4.27) declares `ENTRYPOINT ["docker-php-entrypoint"]`.
That [script](https://github.com/docker-library/php/blob/5ec2a6a0dad498e89a91a39454dbb52e98ce2bdb/docker-php-entrypoint)
only prepends `php` for leading-option arguments, then `exec "$@"`.
For this scheduler's `sh -lc` command it is an exec-only wrapper; replacing it
loses no application setup. The separate REMP backend script is CMD in the
Beam image and was already overridden by the scheduler CMD.
The parent agent also inspected the exact pinned OCI config; preserved evidence
`base-oci-config-proof.json` confirms `docker-php-entrypoint`, backend CMD
`/usr/local/bin/remp-caprover-entrypoint`, WORKDIR `/var/www/html/Beam`, and
**StopSignal SIGQUIT** inherited from PHP-FPM. The scheduler now explicitly
sets **STOPSIGNAL SIGTERM** so a normal container stop uses the signal exercised
by the fixture instead of forwarding FPM's SIGQUIT to a CLI process. Tini forwards
the received signal; `-g` does not translate SIGQUIT into SIGTERM. This metadata
change is scheduler-only and does not claim graceful Laravel shutdown.

[Tini v0.19.0](https://github.com/krallin/tini/blob/v0.19.0/src/tini.c)
reaps with `waitpid(-1, ..., WNOHANG)` and forwards signals to the child process
group with `-g`. As namespace PID 1 it adopts orphan descendants; PHP retains
ownership of its direct managed children. No `-s` is necessary when tini is
PID 1. `-g` covers descendants remaining in the child's process group, not
arbitrary processes that create a new session/group. Tini is not a full
supervisor: it exits when its main child exits and does not promise to drain
all long-running background jobs. Do not infer graceful Laravel job completion
from signal forwarding alone.

## Offline gates and operational acceptance

```sh
python3 -B -m unittest discover -s caprover/tests -v
python3 -B caprover/scripts/validate-definitions.py
git diff --check
```

The tests require the exact scheduler-only init instructions, original CMD,
valid Beam digest reference and all previous PHP/security/backend gates.
Validator mutation tests reject the legacy no-reaper configuration, missing
installation, missing/wrong entrypoint, missing `-g`/`--`, changed WORKDIR/CMD,
unapproved extra instructions and malformed/tagged base references. Additional
mutations reject missing/wrong/duplicate STOPSIGNAL and removed/weakened build
checks, including an always-successful PHP exit and extra apt packages.
These are configuration tests, not OS/process or image-build certification.

Parent-owned `os-fixture-1792785931309063610.json` records 15 real Linux
PID-namespace cases using a synthetic C fork model and extracted Ubuntu tini
0.19.0, via unshare without sudo/Docker. Across three repetitions, old PID 1
accumulated 4/8/12 adopted zombies and tini left zero. A deliberately non-waiting
direct parent still had four zombies with tini. SIGTERM reached both main child
and same-group orphan with `-g` (exit 0); without `-g` the descendant missed it
(exit 92). All namespaces exited. This is OS-level model evidence, **not execution
of PHP, Laravel, the scheduler derivative image or real scheduled tasks**. It
supports adoption and same-group forwarding, not arbitrary process groups or
graceful application completion. The fixture was supplied by the parent, not
rerun during this v2 configuration amendment.

Before controlled deployment, the operator must separately:

1. Retain the parent OCI-config proof for the exact Beam digest, including its
   inherited SIGQUIT. Verify the built derivative overrides this with SIGTERM.
2. Build the scheduler derivative; verify `/usr/bin/tini`, its package version,
   effective ENTRYPOINT/CMD/StopSignal, PHP 8.4.27, upload-progress INI and
   FPM configuration. Preserve actual output from all same-RUN assertions.
   Do not redeploy
   the other PHP apps merely to add scheduler init.
3. Preserve the completed synthetic C namespace proof above; a PHP/Laravel
   process-tree check is still separate. In an isolated PID namespace,
   reproduce old-PHP-PID1 adoption/zombie
   accumulation with shell-background descendants; compare tini as PID 1 over
   repeated rounds. Record PID/PPID/state/group transitions and require no
   persistent zombie accumulation. Also prove that a direct-child non-wait
   fixture is not incorrectly claimed to be fixed by an ancestor reaper.
4. Exercise SIGTERM forwarding to PHP and a still-running background descendant,
   record process-group membership, exit status and bounded cleanup. Use a
   synthetic command, no DB or real scheduled job dispatch.
5. Only after these gates pass, use one protected scheduler replica with the
   existing environment. Observe several minute boundaries and a controlled
   stop, checking zombies, resource growth and normal scheduled work. Keep
   migrations disabled. Roll back/scale scheduler to zero if acceptance fails;
   do not change backend images or the database as a reaping workaround.
