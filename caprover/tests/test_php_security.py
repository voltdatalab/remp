"""Offline PHP patch gate; run with python3 -m unittest discover -s caprover/tests -v.

Keep the 8.4 minor and backend entrypoints unchanged. This validates
configuration only, not registry availability, image builds or running PHP.
"""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PHP_IMAGES = {
    "caprover/docker/beam.Dockerfile": "php:8.4.27-fpm",
    "caprover/docker/campaign.Dockerfile": "php:8.4.27-fpm",
    "caprover/docker/mailer.Dockerfile": "php:8.4.27-fpm",
    "caprover/docker/sso.Dockerfile": "php:8.4.27-fpm",
    "caprover/docker/nginx.Dockerfile": "php:8.4.27-cli",
    "Docker/php/Dockerfile": "php:8.4.27-fpm",
}


class PhpSecurityTests(unittest.TestCase):
    def test_upload_progress_disabled_globally(self):
        path = ROOT / "Docker/php/security.ini"
        self.assertTrue(path.is_file(), "pre-request global mitigation INI is required")
        settings = [line.strip() for line in path.read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith(";")]
        self.assertEqual(settings, ["session.upload_progress.enabled=0"])

    def test_fpm_images_load_and_verify_security_ini(self):
        for path, image in PHP_IMAGES.items():
            if not image.endswith("-fpm"):
                continue
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                source = "security.ini" if path == "Docker/php/Dockerfile" else "Docker/php/security.ini"
                self.assertIn(f"COPY {source} /usr/local/etc/php/conf.d/zz-remp-security.ini", text)
                self.assertIn("PHP_VERSION_ID === 80427", text)
                self.assertIn("ini_get(\"session.upload_progress.enabled\") === \"0\"", text)
                self.assertIn("php-fpm --test", text)

    def test_scheduler_command_unchanged(self):
        data = json.loads((ROOT / "caprover/apps/st-remp-beam-scheduler/captain-definition").read_text())
        # Scheduler-only init: preserve the original CMD byte-for-byte and PHP gates.
        self.assertEqual(data["dockerfileLines"][1:], [
            "RUN apt-get update && apt-get install -y --no-install-recommends tini && test -x /usr/bin/tini && tini --version && dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini && php -r 'exit(PHP_VERSION_ID === 80427 && ini_get(\"session.upload_progress.enabled\") === \"0\" ? 0 : 1);' && php-fpm --test && rm -rf /var/lib/apt/lists/* && printf 'REMP_SCHEDULER_BUILD_OK\\n'",
            "WORKDIR /var/www/html/Beam",
            'ENTRYPOINT ["/usr/bin/tini", "-g", "--"]',
            "STOPSIGNAL SIGTERM",
            'CMD ["sh", "-lc", "if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; fi; exec php artisan schedule:work --verbose --no-interaction"]',
        ])

    def test_scheduler_stop_signal_overrides_fpm_sigquit(self):
        lines = json.loads((ROOT / "caprover/apps/st-remp-beam-scheduler/captain-definition").read_text())["dockerfileLines"]
        self.assertEqual([line for line in lines if line.startswith("STOPSIGNAL ")], ["STOPSIGNAL SIGTERM"])

    def test_scheduler_build_assertions_in_install_run(self):
        lines = json.loads((ROOT / "caprover/apps/st-remp-beam-scheduler/captain-definition").read_text())["dockerfileLines"]
        runs = [line for line in lines if line.startswith("RUN ")]
        self.assertEqual(len(runs), 1)
        for command in ["test -x /usr/bin/tini", "tini --version",
                        "dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini",
                        'php -r \'exit(PHP_VERSION_ID === 80427 && ini_get("session.upload_progress.enabled") === "0" ? 0 : 1);\'',
                        "php-fpm --test"]:
            with self.subTest(command=command):
                self.assertIn(" && " + command + " && ", runs[0])

    def test_scheduler_build_success_marker_is_last(self):
        lines = json.loads((ROOT / "caprover/apps/st-remp-beam-scheduler/captain-definition").read_text())["dockerfileLines"]
        self.assertTrue(lines[1].endswith(" && printf 'REMP_SCHEDULER_BUILD_OK\\n'"))
        self.assertEqual(lines[1].count("REMP_SCHEDULER_BUILD_OK"), 1)
        self.assertIn("dpkg-query -W -f='REMP_SCHEDULER_TINI_VERSION=${Package} ${Version}\\n' tini", lines[1])

    def test_entrypoints_unchanged(self):
        expected = {
            "caprover/scripts/php-entrypoint.sh": "bbf3bdb694fc7e77ff20f3e00ef3dfd1a4f6a254caf2ed2c4cd94ee9df597e96",
            "Docker/php/remp.sh": "6aef3a19bb0cc72f8b139fd43e372c6296327786fe89c1ed74b5a3ecb621bc84",
        }
        for path, digest in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_no_init_or_backend_command_change(self):
        for path in PHP_IMAGES:
            with self.subTest(path=path):
                text = (ROOT / path).read_text()
                self.assertNotRegex(text.lower(), r"\b(?:tini|dumb-init)\b")
                if path == "caprover/docker/nginx.Dockerfile":
                    continue
                commands = re.findall(r"^(?:CMD|ENTRYPOINT)\s+.*$", text, re.MULTILINE)
                expected = ("CMD /usr/local/bin/remp.sh" if path == "Docker/php/Dockerfile"
                            else 'CMD ["/usr/local/bin/remp-caprover-entrypoint"]')
                self.assertEqual(commands, [expected])


def version_test(path, expected):
    def test(self):
        images = re.findall(r"^FROM\s+(php:\S+)", (ROOT / path).read_text(), re.MULTILINE)
        self.assertEqual(images, [expected], f"{path}: require exact PHP 8.4.27 tag (same minor)")
    return test


for index, (path, image) in enumerate(PHP_IMAGES.items()):
    setattr(PhpSecurityTests, f"test_php_image_{index}_{Path(path).parent.name}_{Path(path).stem}", version_test(path, image))


if __name__ == "__main__":
    unittest.main()
