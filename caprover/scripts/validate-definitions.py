#!/usr/bin/env python3
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
definitions = sorted((ROOT / "caprover" / "apps").glob("*/captain-definition"))
assert definitions, "no captain definitions found"

allowed_sources = {"imageName", "dockerfilePath", "dockerfileLines"}
for path in definitions:
    data = json.loads(path.read_text())
    assert data.get("schemaVersion") == 2, f"{path}: schemaVersion must be 2"
    sources = allowed_sources.intersection(data)
    assert len(sources) == 1, f"{path}: expected exactly one build source, got {sorted(sources)}"
    source = next(iter(sources))
    value = data[source]
    if source == "dockerfileLines":
        assert isinstance(value, list) and value, f"{path}: dockerfileLines must be a non-empty list"
        assert all(isinstance(line, str) and line.strip() for line in value), f"{path}: invalid dockerfile line"
    else:
        assert isinstance(value, str) and value.strip(), f"{path}: {source} must be a non-empty string"

scheduler = ROOT / "caprover" / "apps" / "st-remp-beam-scheduler" / "captain-definition"
data = json.loads(scheduler.read_text())
lines = data["dockerfileLines"]
assert re.fullmatch(r"FROM ghcr\.io/voltdatalab/remp-beam@sha256:[0-9a-f]{64}", lines[0]), "scheduler must pin the exact Beam repository by SHA-256 digest"
assert lines[1:] == [
    "RUN apt-get update && apt-get install -y --no-install-recommends tini && test -x /usr/bin/tini && tini --version && dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini && php -r 'exit(PHP_VERSION_ID === 80427 && ini_get(\"session.upload_progress.enabled\") === \"0\" ? 0 : 1);' && php-fpm --test && rm -rf /var/lib/apt/lists/* && printf 'REMP_SCHEDULER_BUILD_OK\\n'",
    "WORKDIR /var/www/html/Beam",
    'ENTRYPOINT ["/usr/bin/tini", "-g", "--"]',
    "STOPSIGNAL SIGTERM",
    'CMD ["sh", "-lc", "if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; fi; exec php artisan schedule:work --verbose --no-interaction"]',
], "scheduler requires only tini installation with build assertions, group-forwarding ENTRYPOINT, SIGTERM stop signal, and the original WORKDIR/CMD"
print(f"validated_captain_definitions={len(definitions)}")
print("beam_scheduler_contract=ok")
