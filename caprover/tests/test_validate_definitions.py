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
    "RUN apt-get update && apt-get install -y --no-install-recommends tini && test -x /usr/bin/tini && tini --version && dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini && php -r 'exit(PHP_VERSION_ID === 80427 && ini_get(\"session.upload_progress.enabled\") === \"0\" ? 0 : 1);' && php-fpm --test && rm -rf /var/lib/apt/lists/* && printf 'REMP_SCHEDULER_BUILD_OK\\n'",
    "WORKDIR /var/www/html/Beam",
    'ENTRYPOINT ["/usr/bin/tini", "-g", "--"]',
    "STOPSIGNAL SIGTERM",
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

    def test_03_rejects_scheduler_without_reaper(self):
        result = self.run_validator([BASE, COMMAND[1], COMMAND[-1]])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("beam_scheduler_contract=ok", result.stdout)

    def test_04_rejects_missing_wrong_or_duplicate_stop_signal(self):
        self.assert_positive_control()
        for replacement in [[], ["STOPSIGNAL SIGQUIT"], ["STOPSIGNAL SIGTERM", "STOPSIGNAL SIGTERM"]]:
            with self.subTest(replacement=replacement):
                result = self.run_validator([BASE, *COMMAND[:3], *replacement, COMMAND[-1]])
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_05_rejects_missing_or_weakened_build_assertions(self):
        self.assert_positive_control()
        for fragment in ["test -x /usr/bin/tini && ", "tini --version && ",
                         "dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini && ",
                         "php-fpm --test && ", "PHP_VERSION_ID === 80427 && "]:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, COMMAND[0])
                result = self.run_validator([BASE, COMMAND[0].replace(fragment, ""), *COMMAND[1:]])
                self.assertNotEqual(result.returncode, 0, result.stdout)
        for old, new in [('=== "0"', '=== "1"'), ["? 0 : 1", "? 0 : 0"],
                         ["--no-install-recommends tini", "--no-install-recommends tini curl"]]:
            with self.subTest(replacement=new):
                self.assertIn(old, COMMAND[0])
                result = self.run_validator([BASE, COMMAND[0].replace(old, new), *COMMAND[1:]])
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_06_rejects_missing_or_misplaced_execution_markers(self):
        self.assert_positive_control()
        for old, new in [(" && printf 'REMP_SCHEDULER_BUILD_OK\\n'", ""),
                         ("REMP_SCHEDULER_TINI_VERSION=", ""),
                         ("php-fpm --test", "printf 'REMP_SCHEDULER_BUILD_OK\\n'"),
                         (" && printf 'REMP_SCHEDULER_BUILD_OK\\n'", "; printf 'REMP_SCHEDULER_BUILD_OK\\n'")]:
            with self.subTest(replacement=new):
                self.assertIn(old, COMMAND[0])
                result = self.run_validator([BASE, COMMAND[0].replace(old, new), *COMMAND[1:]])
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_02_rejects_invalid_contracts_after_positive_control(self):
        # Do not interpret negative results from an invalid positive fixture.
        self.assert_positive_control()
        cases = {
            "truncated_digest": [BASE[:-1], *COMMAND],
            "nonhex_digest": [BASE[:-1] + "g", *COMMAND],
            "arbitrary_repository": [BASE.replace("voltdatalab/remp-beam", "other/remp-beam"), *COMMAND],
            "branch_tag": ["FROM ghcr.io/voltdatalab/remp-beam:fix/remp-php-security-20261023", *COMMAND],
            "latest_tag": ["FROM ghcr.io/voltdatalab/remp-beam:latest", *COMMAND],
            "changed_cmd": [BASE, *COMMAND[:-1], COMMAND[-1].replace("--verbose", "--quiet")],
            "changed_workdir": [BASE, COMMAND[0], "WORKDIR /var/www/html", *COMMAND[2:]],
            "missing_install": [BASE, *COMMAND[1:]],
            "missing_entrypoint": [BASE, *COMMAND[:2], *COMMAND[3:]],
            "missing_group_forwarding": [BASE, *COMMAND[:2], 'ENTRYPOINT ["/usr/bin/tini", "--"]', *COMMAND[3:]],
            "missing_separator": [BASE, *COMMAND[:2], 'ENTRYPOINT ["/usr/bin/tini", "-g"]', *COMMAND[3:]],
            "inherited_entrypoint": [BASE, *COMMAND[:2], 'ENTRYPOINT ["docker-php-entrypoint"]', *COMMAND[3:]],
            "extra_instruction": [BASE, *COMMAND, "ENV REMP_RUN_MIGRATIONS=true"],
            "extra_from": [BASE, *COMMAND, "FROM alpine:3.22"],
        }
        for name, lines in cases.items():
            with self.subTest(case=name):
                result = self.run_validator(lines)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("beam_scheduler_contract=ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
