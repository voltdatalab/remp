"""Offline CLI contract tests; synthetic digests are never deployment refs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
# Deliberately synthetic: only used inside disposable fixture Captain definitions.
BASE = "FROM ghcr.io/voltdatalab/remp-beam@sha256:" + "a" * 64
COMMAND = [
    "WORKDIR /var/www/html/Beam",
    'CMD ["sh", "-lc", "if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; fi; exec php artisan schedule:work --verbose --no-interaction"]',
]


class ValidateDefinitionsTests(unittest.TestCase):
    def run_validator(self, lines):
        with tempfile.TemporaryDirectory(prefix="remp-update-validator-", dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            script = root / "caprover/scripts/validate-definitions.py"
            script.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "caprover/scripts/validate-definitions.py", script)
            definition = root / "caprover/apps/st-remp-beam-scheduler/captain-definition"
            definition.parent.mkdir(parents=True)
            definition.write_text(json.dumps({"schemaVersion": 2, "dockerfileLines": lines}))
            return subprocess.run(
                [sys.executable, "-B", str(script)], cwd=root,
                capture_output=True, text=True, timeout=10,
            )

    def assert_positive_control(self):
        result = self.run_validator([BASE, *COMMAND])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "validated_captain_definitions=1", "beam_scheduler_contract=ok",
        ])

    def test_00_accepts_exact_digest_and_unchanged_command(self):
        self.assert_positive_control()

    def test_01_rejects_legacy_sha_tag(self):
        # Independent baseline regression: the old validator admits this tag.
        result = self.run_validator([
            "FROM ghcr.io/voltdatalab/remp-beam:sha-c68f52c", *COMMAND,
        ])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("beam_scheduler_contract=ok", result.stdout)

    def test_02_rejects_invalid_contracts_after_positive_control(self):
        # Do not interpret negative results from an invalid positive fixture.
        self.assert_positive_control()
        cases = {
            "truncated_digest": [BASE[:-1], *COMMAND],
            "nonhex_digest": [BASE[:-1] + "g", *COMMAND],
            "arbitrary_repository": [BASE.replace("voltdatalab/remp-beam", "other/remp-beam"), *COMMAND],
            "branch_tag": ["FROM ghcr.io/voltdatalab/remp-beam:fix/remp-php-security-20261023", *COMMAND],
            "latest_tag": ["FROM ghcr.io/voltdatalab/remp-beam:latest", *COMMAND],
            "changed_cmd": [BASE, COMMAND[0], COMMAND[1].replace("--verbose", "--quiet")],
            "changed_workdir": [BASE, "WORKDIR /var/www/html", COMMAND[1]],
            "extra_from": [BASE, *COMMAND, "FROM alpine:3.22"],
        }
        for name, lines in cases.items():
            with self.subTest(case=name):
                result = self.run_validator(lines)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("beam_scheduler_contract=ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
