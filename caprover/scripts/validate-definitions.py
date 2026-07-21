#!/usr/bin/env python3
import json
from pathlib import Path

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
lines = "\n".join(data["dockerfileLines"])
assert "ghcr.io/voltdatalab/remp-beam:sha-" in lines, "scheduler must pin an immutable Beam image"
assert "schedule:work" in lines, "scheduler must execute Laravel schedule:work"
assert ".env.example" in lines and "cp .env.example .env" in lines, "scheduler must initialize the same fallback env as the Beam web entrypoint"
assert "latest" not in lines, "scheduler must not use a mutable image tag"
print(f"validated_captain_definitions={len(definitions)}")
print("beam_scheduler_contract=ok")
