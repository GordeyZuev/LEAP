"""Exercise deployment failure boundaries without touching Docker or production."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class BlueGreenDeployTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        (self.root / "scripts").mkdir()
        (self.root / "nginx" / "active").mkdir(parents=True)
        (self.root / "bin").mkdir()
        shutil.copy(ROOT / "scripts" / "deploy-blue-green.sh", self.root / "scripts")
        shutil.copy(ROOT / "nginx" / "nginx.bootstrap.conf", self.root / "nginx")
        shutil.copy(ROOT / "nginx" / "nginx.https.conf", self.root / "nginx")
        (self.root / "nginx" / "nginx.conf").write_text("old config\n")
        (self.root / ".env.static").write_text(
            "OAUTH_FRONTEND_REDIRECT_URL=https://leap.example\n"
        )
        self._set_slot("blue")
        self._stub(
            "sudo",
            """#!/bin/sh
if [ "$1" = test ] && [ "$2" = -f ]; then
  [ "${MOCK_TLS:-}" = 1 ] && exit 0
  exit 1
fi
if [ "$1" = find ]; then exit 0; fi
exec "$@"
""",
        )
        self._stub("yc", "#!/bin/sh\nexit 0\n")
        self._stub(
            "docker",
            """#!/bin/sh
printf '%s\\n' "$*" >> "$MOCK_ROOT/docker-commands.log"
if [ "$1" = compose ]; then
  case " $* " in
    *" pull "*) [ "${FAIL_PHASE:-}" != pull ] || exit 1 ;;
    *" prometheus "*) [ "${FAIL_PHASE:-}" != monitoring ] || exit 1 ;;
    *" up "*" celery_beat "*) [ "${FAIL_PHASE:-}" != celery_beat ] || exit 1 ;;
  esac
  if [ "${FAIL_PHASE:-}" = preview_worker ]; then
    case " $* " in *" celery_preview_worker "*) exit 1 ;; esac
  fi
  if [ "${FAIL_PHASE:-}" = cpu_worker ]; then
    case " $* " in *" celery_cpu_worker "*) exit 1 ;; esac
  fi
  if [ "${FAIL_PHASE:-}" = maintenance_worker ]; then
    case " $* " in *" celery_maintenance_worker "*) exit 1 ;; esac
  fi
  exit 0
fi
if [ "$1" = exec ] && [ "$2" = leap_postgres ] && [ "${FAIL_PHASE:-}" = postgres ]; then exit 1; fi
if [ "$1" = exec ] && [ "$2" = leap_nginx ] && [ "$3" = test ]; then exit 0; fi
exit 0
""",
        )
        self._stub(
            "curl",
            """#!/bin/sh
if [ "${MOCK_TLS:-}" = 1 ]; then
  case " $* " in *" --resolve "*) ;; *) exit 2 ;; esac
fi
slot=$(sed -n 's/^set \\$leap_slot "\\([^"]*\\)";/\\1/p' "$MOCK_ROOT/nginx/active/slot.conf")
if [ "${FAIL_PHASE:-}" = smoke ]; then exit 22; fi
if [ "${FAIL_PHASE:-}" = api_unready ] && [ "$slot" = green ]; then
  case " $* " in *"/api/v1/health/ready"*) printf 'HTTP/1.1 503 Service Unavailable\\r\\nX-Leap-Slot: green\\r\\n\\r\\n'; exit 0 ;; esac
fi
if [ "${FAIL_PHASE:-}" = missing_slot ] && [ "$slot" = green ]; then
  printf 'HTTP/1.1 200 OK\\r\\n\\r\\n'; exit 0
fi
if [ "${FAIL_PHASE:-}" = login_redirect ] && [ "$slot" = green ]; then
  case " $* " in *"/login"*) printf 'HTTP/1.1 302 Found\\r\\nX-Leap-Slot: green\\r\\n\\r\\n'; exit 0 ;; esac
fi
if [ "${MOCK_TLS:-}" = 1 ]; then
  printf 'HTTP/2 200\\r\\nx-leap-slot: %s\\r\\n\\r\\n' "$slot"
  exit 0
fi
printf 'HTTP/1.1 200 OK\\r\\nX-Leap-Slot: %s\\r\\n\\r\\n' "$slot"
""",
        )

    def _stub(self, name: str, body: str) -> None:
        path = self.root / "bin" / name
        path.write_text(body)
        path.chmod(0o755)

    def _set_slot(self, slot: str) -> None:
        suffix = "_green" if slot == "green" else ""
        (self.root / "nginx" / "active" / "slot.conf").write_text(
            f'set $api_upstream "http://api{suffix}:8000";\n'
            f'set $frontend_upstream "http://frontend{suffix}:3000";\n'
            'set $previous_frontend_upstream "http://frontend:3000";\n'
            f'set $leap_slot "{slot}";\n'
        )

    def _run(
        self, mode: str = "test-sha", fail_phase: str = "", tls: bool = False
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            PATH=f"{self.root / 'bin'}:{env['PATH']}",
            MOCK_ROOT=str(self.root),
            FAIL_PHASE=fail_phase,
            LEAP_SMOKE_ATTEMPTS="1",
            MOCK_TLS="1" if tls else "0",
        )
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "deploy-blue-green.sh"), mode],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _slot(self) -> str:
        return (self.root / "nginx" / "active" / "slot.conf").read_text()

    def test_success_and_manual_rollback(self) -> None:
        deployed = self._run()
        self.assertEqual(deployed.returncode, 0, deployed.stderr)
        self.assertIn('set $leap_slot "green";', self._slot())
        self.assertEqual(
            (self.root / "nginx" / "active" / "confirmed-slot").read_text().strip(),
            "green",
        )
        self.assertEqual(
            (self.root / "nginx" / "active" / "rollback-slot").read_text().strip(),
            "blue",
        )
        rolled_back = self._run("--rollback")
        self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
        self.assertIn('set $leap_slot "blue";', self._slot())
        self.assertEqual(
            (self.root / "nginx" / "active" / "confirmed-slot").read_text().strip(),
            "blue",
        )
        self.assertEqual(
            (self.root / "nginx" / "active" / "rollback-slot").read_text().strip(),
            "green",
        )

    def test_failure_before_switch_keeps_active_slot(self) -> None:
        failed = self._run(fail_phase="pull")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_unready_database_stops_before_migration(self) -> None:
        failed = self._run(fail_phase="postgres")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())
        commands = (self.root / "docker-commands.log").read_text()
        self.assertNotIn("compose run --rm --no-deps migrate", commands)

    def test_preview_worker_failure_blocks_switch(self) -> None:
        failed = self._run(fail_phase="preview_worker")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_cpu_worker_failure_blocks_switch(self) -> None:
        failed = self._run(fail_phase="cpu_worker")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_maintenance_worker_failure_blocks_switch(self) -> None:
        failed = self._run(fail_phase="maintenance_worker")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_beat_failure_blocks_switch(self) -> None:
        failed = self._run(fail_phase="celery_beat")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_https_smoke_uses_local_dns_override(self) -> None:
        deployed = self._run(tls=True)
        self.assertEqual(deployed.returncode, 0, deployed.stderr)
        self.assertIn('set $leap_slot "green";', self._slot())

    def test_failed_smoke_restores_active_slot(self) -> None:
        failed = self._run(fail_phase="smoke")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())
        self.assertIn("restoring blue", failed.stderr)
        rollback = self._run("--rollback")
        self.assertNotEqual(rollback.returncode, 0)
        self.assertIn("No confirmed rollback slot green", rollback.stderr)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_failed_redeploy_invalidates_old_rollback_slot(self) -> None:
        self.assertEqual(self._run().returncode, 0)
        failed = self._run(fail_phase="smoke")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "green";', self._slot())
        rollback = self._run("--rollback")
        self.assertNotEqual(rollback.returncode, 0)
        self.assertIn("No confirmed rollback slot blue", rollback.stderr)

    def test_unready_api_reports_failing_path_and_restores_slot(self) -> None:
        failed = self._run(fail_phase="api_unready")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("Smoke /api/v1/health/ready: HTTP 503", failed.stderr)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_missing_slot_header_reports_failure(self) -> None:
        failed = self._run(fail_phase="missing_slot")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("X-Leap-Slot none; expected 200/green", failed.stderr)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_monitoring_does_not_recreate_application_dependencies(self) -> None:
        deployed = self._run()
        self.assertEqual(deployed.returncode, 0, deployed.stderr)
        commands = (self.root / "docker-commands.log").read_text().splitlines()
        postgres_check = commands.index("exec leap_postgres pg_isready -U postgres -d leap_platform")
        migrate = commands.index("compose run --rm --no-deps migrate")
        self.assertLess(postgres_check, migrate)
        monitoring = [command for command in commands if " prometheus " in f" {command} "]
        self.assertEqual(len(monitoring), 1)
        self.assertIn("up -d --no-deps --force-recreate", monitoring[0])
        self.assertIn("compose up -d --no-deps loki", commands)

    def test_login_redirect_is_not_considered_healthy(self) -> None:
        failed = self._run(fail_phase="login_redirect")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())

    def test_interrupted_switch_restores_confirmed_slot(self) -> None:
        (self.root / "nginx" / "active" / "confirmed-slot").write_text("blue\n")
        self._set_slot("green")
        failed = self._run()
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())
        self.assertIn("Interrupted switch", failed.stderr)

    def test_monitoring_failure_is_red_before_switch(self) -> None:
        failed = self._run(fail_phase="monitoring")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('set $leap_slot "blue";', self._slot())


if __name__ == "__main__":
    unittest.main()
