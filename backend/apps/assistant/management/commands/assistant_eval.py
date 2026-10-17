"""Run the assistant evaluation set and print a scored report.

    python manage.py assistant_eval --role tenant            # one role
    python manage.py assistant_eval --limit 10 --out report.json
    ASSISTANT_PROVIDER=anthropic python manage.py assistant_eval --yes   # real model: costs money

The run uses a throwaway test database (never your real data), with mock SMS, WhatsApp and payments.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from apps.assistant.evals import runner


class Command(BaseCommand):
    help = "Score the assistant against apps/assistant/evals/*.jsonl"

    def add_arguments(self, parser):
        parser.add_argument("--role", choices=[*runner.ROLES, "all"], default="all")
        parser.add_argument("--limit", type=int, default=None, help="items per role")
        parser.add_argument("--ids", default="", help="comma-separated item ids")
        parser.add_argument("--out", default="", help="write the full JSON report here")
        parser.add_argument("--yes", action="store_true", help="confirm spending money on a real model")
        parser.add_argument("--keep-db", action="store_true", help="reuse the test database between runs")

    def handle(self, *args, **opts):
        if settings.ASSISTANT_PROVIDER != "mock" and not opts["yes"]:
            raise CommandError(
                f"ASSISTANT_PROVIDER={settings.ASSISTANT_PROVIDER} calls a paid API "
                "(about 1-3 model calls per item). "
                "Re-run with --yes to confirm, or use --limit to try a few first."
            )
        roles = runner.ROLES if opts["role"] == "all" else (opts["role"],)
        ids = {i.strip() for i in opts["ids"].split(",") if i.strip()} or None

        def show(r):
            mark = "PASS" if r.passed else "FAIL"
            self.stdout.write(
                f"{mark} {r.id:<14} {r.behaviour:<9} {r.language:<3} tools={','.join(r.tools) or '-'}"
            )
            for reason in r.reasons:
                self.stdout.write(f"      - {reason}")

        test_runner = DiscoverRunner(verbosity=0, keepdb=opts["keep_db"], interactive=False)
        with override_settings(
            SMS_PROVIDER="mock",
            WHATSAPP_PROVIDER="mock",
            PAYMENT_GATEWAYS="mock",
            BILLS_PROVIDERS="mock",
            CELERY_TASK_ALWAYS_EAGER=True,
            ASSISTANT_USER_DAILY_CAP_USD="1000",
            ASSISTANT_PLATFORM_DAILY_CAP_USD="1000",
            ASSISTANT_ORG_MONTHLY_CAP_USD="1000",
            ASSISTANT_RATE_LIMIT="1000/60",
        ):
            from config.celery import app as celery_app

            celery_app.conf.task_always_eager = True
            old = test_runner.setup_databases()
            try:
                report = runner.run(roles, limit=opts["limit"], ids=ids, on_result=show)
            finally:
                test_runner.teardown_databases(old)
        s = report["summary"]
        self.stdout.write("")
        self.stdout.write(
            "Model: "
            + (
                settings.ANTHROPIC_MODEL
                if settings.ASSISTANT_PROVIDER == "anthropic"
                else settings.ASSISTANT_PROVIDER
            )
        )
        self.stdout.write(
            f"Passed {s['passed']}/{s['total']} ({s['pass_rate']:.1%}); "
            f"reply language matched {s['language_ok_rate']:.1%}; "
            f"estimated cost ${s['cost_usd']}"
        )
        for key, c in s["breakdown"].items():
            self.stdout.write(f"  {key:<22} {c.get('passed', 0)}/{c['total']}")
        if opts["out"]:
            with open(opts["out"], "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.stdout.write(f"Report written to {opts['out']}")
