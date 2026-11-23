import difflib
import json
import shutil
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


TEST_COMMAND = "python -m unittest discover -s tests"
REPAIRED_INSTANCE_IDS = {"type-i-04", "type-ii-02", "type-ii-03"}

CASES = [
    {
        "id": "type-i-01",
        "fault_type": "Type-I",
        "root_cause_hops": 0,
        "description": "Calculates a straight-line distance from two coordinate pairs.",
        "files": {
            "api.py": "import math\n\n\ndef distance(x, y):\n    return sqrt(x * x + y * y)\n",
            "geometry.py": "def pair_sum(left, right):\n    return left + right\n",
            "tests/test_api.py": "import unittest\nfrom api import distance\n\n\nclass DistanceTests(unittest.TestCase):\n    def test_distance(self):\n        self.assertEqual(distance(3, 4), 5)\n",
        },
        "fixes": {
            "api.py": "import math\nfrom math import sqrt\n\n\ndef distance(x, y):\n    return sqrt(x * x + y * y)\n",
        },
    },
    {
        "id": "type-i-02",
        "fault_type": "Type-I",
        "root_cause_hops": 1,
        "description": "Formats a timestamp for a service response.",
        "files": {
            "api.py": "from helper import timestamp\n\n\ndef response_time():\n    return timestamp(2025, 1, 2)\n",
            "helper.py": "from datetime import datetime, UTCZone\n\n\ndef timestamp(year, month, day):\n    return datetime(year, month, day, tzinfo=UTCZone.utc).isoformat()\n",
            "tests/test_api.py": "import unittest\nfrom api import response_time\n\n\nclass ResponseTimeTests(unittest.TestCase):\n    def test_response_time(self):\n        self.assertEqual(response_time(), \"2025-01-02T00:00:00+00:00\")\n",
        },
        "fixes": {
            "helper.py": "from datetime import datetime, timezone\n\n\ndef timestamp(year, month, day):\n    return datetime(year, month, day, tzinfo=timezone.utc).isoformat()\n",
        },
    },
    {
        "id": "type-i-03",
        "fault_type": "Type-I",
        "root_cause_hops": 2,
        "description": "Loads a JSON object through the request handling layer.",
        "files": {
            "api.py": "from routing import load_request\n\n\ndef request_value(text):\n    return load_request(text)[\"value\"]\n",
            "routing.py": "from decoder import decode\n\n\ndef load_request(text):\n    return decode(text)\n",
            "decoder.py": "from codecs import JSONDecodeError\nimport json\n\n\ndef decode(text):\n    return json.loads(text)\n",
            "tests/test_api.py": "import unittest\nfrom api import request_value\n\n\nclass RequestValueTests(unittest.TestCase):\n    def test_request_value(self):\n        self.assertEqual(request_value('{\"value\": 7}'), 7)\n",
        },
        "fixes": {
            "decoder.py": "from json import JSONDecodeError\nimport json\n\n\ndef decode(text):\n    return json.loads(text)\n",
        },
    },
    {
        "id": "type-i-04",
        "fault_type": "Type-I",
        "root_cause_hops": 2,
        "description": "Resolves a normalized file name through the application service.",
        "files": {
            "api.py": "from service import normalized_name\n\n\ndef output_name(value):\n    return normalized_name(value)\n",
            "service.py": "from paths import normalize\n\n\ndef normalized_name(value):\n    return normalize(value)\n",
            "paths.py": "from os.path import PurePath\n\n\ndef normalize(value):\n    return str(PurePath(value))\n",
            "tests/test_api.py": "import unittest\nfrom pathlib import PurePath\nfrom api import output_name\n\n\nclass OutputNameTests(unittest.TestCase):\n    def test_output_name(self):\n        self.assertEqual(output_name(\"reports/item.txt\"), str(PurePath(\"reports/item.txt\")))\n",
        },
        "fixes": {
            "paths.py": "from pathlib import PurePath\n\n\ndef normalize(value):\n    return str(PurePath(value))\n",
        },
    },
    {
        "id": "type-i-05",
        "fault_type": "Type-I",
        "root_cause_hops": 1,
        "description": "Builds an absolute cache location from a configured directory.",
        "files": {
            "api.py": "from cache_path import cache_location\n\n\ndef cache_file(root, name):\n    return cache_location(root, name)\n",
            "cache_path.py": "def cache_location(root, name):\n    return str(Path(root) / name)\n",
            "tests/test_api.py": "import unittest\nfrom pathlib import Path\nfrom api import cache_file\n\n\nclass CacheFileTests(unittest.TestCase):\n    def test_cache_file(self):\n        self.assertEqual(cache_file(\"/var/cache\", \"entry.bin\"), str(Path(\"/var/cache\") / \"entry.bin\"))\n",
        },
        "fixes": {
            "cache_path.py": "from pathlib import Path\n\n\ndef cache_location(root, name):\n    return str(Path(root) / name)\n",
        },
    },
    {
        "id": "type-i-06",
        "fault_type": "Type-I",
        "root_cause_hops": 0,
        "description": "Computes the arithmetic mean for a collection of measurements.",
        "files": {
            "api.py": "import statistics.mean as average\n\n\ndef mean_value(values):\n    return average(values)\n",
            "measurements.py": "def values_in_range(values, low, high):\n    return [value for value in values if low <= value <= high]\n",
            "tests/test_api.py": "import unittest\nfrom api import mean_value\n\n\nclass MeanValueTests(unittest.TestCase):\n    def test_mean_value(self):\n        self.assertEqual(mean_value([2, 4, 6]), 4)\n",
        },
        "fixes": {
            "api.py": "from statistics import mean as average\n\n\ndef mean_value(values):\n    return average(values)\n",
        },
    },
    {
        "id": "type-ii-01",
        "fault_type": "Type-II",
        "root_cause_hops": 0,
        "description": "Checks whether a measurement falls within a closed interval.",
        "files": {
            "api.py": "def within_range(value, lower, upper):\n    return lower <= value < upper\n",
            "ranges.py": "def span(lower, upper):\n    return upper - lower\n",
            "tests/test_api.py": "import unittest\nfrom api import within_range\n\n\nclass RangeTests(unittest.TestCase):\n    def test_upper_endpoint(self):\n        self.assertTrue(within_range(10, 2, 10))\n",
        },
        "fixes": {
            "api.py": "def within_range(value, lower, upper):\n    return lower <= value <= upper\n",
        },
    },
    {
        "id": "type-ii-02",
        "fault_type": "Type-II",
        "root_cause_hops": 1,
        "description": "Calculates a shipping charge from an order quantity.",
        "files": {
            "api.py": "from pricing import shipping_cost\n\n\ndef order_shipping(quantity, express):\n    return shipping_cost(quantity, express)\n",
            "pricing.py": "def shipping_cost(quantity, express):\n    if express:\n        return 8\n    return 15\n",
            "tests/test_api.py": "import unittest\nfrom api import order_shipping\n\n\nclass ShippingTests(unittest.TestCase):\n    def test_express_shipping(self):\n        self.assertEqual(order_shipping(1, True), 15)\n",
        },
        "fixes": {
            "pricing.py": "def shipping_cost(quantity, express):\n    if express:\n        return 15\n    return 8\n",
        },
    },
    {
        "id": "type-ii-03",
        "fault_type": "Type-II",
        "root_cause_hops": 2,
        "description": "Determines whether a user can access an administrative operation.",
        "files": {
            "api.py": "from service import may_manage\n\n\ndef manage_access(role):\n    return may_manage(role)\n",
            "service.py": "from policy import allows_management\n\n\ndef may_manage(role):\n    return allows_management(role)\n",
            "policy.py": "def allows_management(role):\n    if role == \"admin\":\n        return False\n    return True\n",
            "tests/test_api.py": "import unittest\nfrom api import manage_access\n\n\nclass ManagementAccessTests(unittest.TestCase):\n    def test_administrator_access(self):\n        self.assertTrue(manage_access(\"admin\"))\n",
        },
        "fixes": {
            "policy.py": "def allows_management(role):\n    if role == \"admin\":\n        return True\n    return False\n",
        },
    },
    {
        "id": "type-ii-04",
        "fault_type": "Type-II",
        "root_cause_hops": 2,
        "description": "Counts the calendar days covered by a booking.",
        "files": {
            "api.py": "from service import booking_days\n\n\ndef days_booked(start, end):\n    return booking_days(start, end)\n",
            "service.py": "from calendar_rules import count_days\n\n\ndef booking_days(start, end):\n    return count_days(start, end)\n",
            "calendar_rules.py": "def count_days(start, end):\n    return (end - start).days\n",
            "tests/test_api.py": "import unittest\nfrom datetime import date\nfrom api import days_booked\n\n\nclass BookingDaysTests(unittest.TestCase):\n    def test_single_day(self):\n        self.assertEqual(days_booked(date(2025, 5, 1), date(2025, 5, 1)), 1)\n",
        },
        "fixes": {
            "calendar_rules.py": "def count_days(start, end):\n    return (end - start).days + 1\n",
        },
    },
    {
        "id": "type-ii-05",
        "fault_type": "Type-II",
        "root_cause_hops": 1,
        "description": "Selects a page of records from a sequence.",
        "files": {
            "api.py": "from paging import select_page\n\n\ndef page(items, number, size):\n    return select_page(items, number, size)\n",
            "paging.py": "def select_page(items, number, size):\n    start = (number - 1) * (size - 1)\n    return items[start:start + size]\n",
            "tests/test_api.py": "import unittest\nfrom api import page\n\n\nclass PageTests(unittest.TestCase):\n    def test_second_page(self):\n        self.assertEqual(page(list(range(6)), 2, 3), [3, 4, 5])\n",
        },
        "fixes": {
            "paging.py": "def select_page(items, number, size):\n    start = (number - 1) * size\n    return items[start:start + size]\n",
        },
    },
    {
        "id": "type-ii-06",
        "fault_type": "Type-II",
        "root_cause_hops": 0,
        "description": "Validates the structure of an email address.",
        "files": {
            "api.py": "def has_email_shape(value):\n    return \"@\" in value and \".\" in value\n",
            "email_rules.py": "def normalized(value):\n    return value.strip().lower()\n",
            "tests/test_api.py": "import unittest\nfrom api import has_email_shape\n\n\nclass EmailShapeTests(unittest.TestCase):\n    def test_separator_order(self):\n        self.assertFalse(has_email_shape(\"person.example@host\"))\n",
        },
        "fixes": {
            "api.py": "def has_email_shape(value):\n    return \"@\" in value and \".\" in value.split(\"@\", 1)[1]\n",
        },
    },
    {
        "id": "type-iii-01",
        "fault_type": "Type-III",
        "root_cause_hops": 0,
        "description": "Calculates an invoice amount after applying a discount.",
        "files": {
            "api.py": "from totals import calculate_total\n\n\ndef invoice_amount(subtotal, discount):\n    return calculate_total(discount, subtotal)\n",
            "totals.py": "def calculate_total(subtotal, discount):\n    return subtotal - discount\n",
            "tests/test_api.py": "import unittest\nfrom api import invoice_amount\n\n\nclass InvoiceAmountTests(unittest.TestCase):\n    def test_discount(self):\n        self.assertEqual(invoice_amount(100, 15), 85)\n",
        },
        "fixes": {
            "api.py": "from totals import calculate_total\n\n\ndef invoice_amount(subtotal, discount):\n    return calculate_total(subtotal, discount)\n",
        },
    },
    {
        "id": "type-iii-02",
        "fault_type": "Type-III",
        "root_cause_hops": 0,
        "description": "Renders a named record using its display label.",
        "files": {
            "api.py": "from rendering import render_record\n\n\ndef record_label(title, owner):\n    return render_record(title)\n",
            "rendering.py": "def render_record(name, creator):\n    return f\"{name} ({creator})\"\n",
            "tests/test_api.py": "import unittest\nfrom api import record_label\n\n\nclass RecordLabelTests(unittest.TestCase):\n    def test_record_label(self):\n        self.assertEqual(record_label(\"Report\", \"Lee\"), \"Report (Lee)\")\n",
        },
        "fixes": {
            "api.py": "from rendering import render_record\n\n\ndef record_label(title, owner):\n    return render_record(title, owner)\n",
        },
    },
    {
        "id": "type-iii-03",
        "fault_type": "Type-III",
        "root_cause_hops": 1,
        "description": "Runs an operation using the default retry policy.",
        "files": {
            "api.py": "from retrying import run_once\n\n\ndef run(operation):\n    return run_once(operation)\n",
            "retrying.py": "def run_once(operation, attempts=0):\n    for _ in range(attempts):\n        if operation():\n            return True\n    return False\n",
            "tests/test_api.py": "import unittest\nfrom api import run\n\n\nclass RunTests(unittest.TestCase):\n    def test_default_attempt(self):\n        calls = []\n\n        def operation():\n            calls.append(True)\n            return True\n\n        self.assertTrue(run(operation))\n        self.assertEqual(len(calls), 1)\n",
        },
        "fixes": {
            "retrying.py": "def run_once(operation, attempts=1):\n    for _ in range(attempts):\n        if operation():\n            return True\n    return False\n",
        },
    },
    {
        "id": "type-iii-04",
        "fault_type": "Type-III",
        "root_cause_hops": 2,
        "description": "Creates an account through the user service adapter.",
        "files": {
            "api.py": "from adapter import register\n\n\ndef create_account(user_id, email):\n    return register(user_id, email)\n",
            "adapter.py": "from client import create_user\n\n\ndef register(user_id, email):\n    return create_user(user_id, email)\n",
            "client.py": "def create_user(*, user_id, email):\n    return {\"id\": user_id, \"email\": email}\n",
            "tests/test_api.py": "import unittest\nfrom api import create_account\n\n\nclass AccountTests(unittest.TestCase):\n    def test_account_fields(self):\n        self.assertEqual(create_account(\"u-4\", \"a@example.test\"), {\"id\": \"u-4\", \"email\": \"a@example.test\"})\n",
        },
        "fixes": {
            "adapter.py": "from client import create_user\n\n\ndef register(user_id, email):\n    return create_user(user_id=user_id, email=email)\n",
        },
    },
    {
        "id": "type-iii-05",
        "fault_type": "Type-III",
        "root_cause_hops": 0,
        "description": "Formats a date using a caller-provided pattern.",
        "files": {
            "api.py": "from dates import render_date\n\n\ndef display_date(value, pattern):\n    return render_date(value, fmt=pattern)\n",
            "dates.py": "def render_date(value, pattern):\n    return value.strftime(pattern)\n",
            "tests/test_api.py": "import unittest\nfrom datetime import date\nfrom api import display_date\n\n\nclass DisplayDateTests(unittest.TestCase):\n    def test_custom_pattern(self):\n        self.assertEqual(display_date(date(2025, 7, 9), \"%Y/%m/%d\"), \"2025/07/09\")\n",
        },
        "fixes": {
            "dates.py": "def render_date(value, fmt):\n    return value.strftime(fmt)\n",
        },
    },
    {
        "id": "type-iii-06",
        "fault_type": "Type-III",
        "root_cause_hops": 1,
        "description": "Looks up a record and exposes its value through the service.",
        "files": {
            "api.py": "from storage import lookup\n\n\ndef value_for(key, entries):\n    result = lookup(key, entries)\n    return result.upper()\n",
            "storage.py": "def lookup(key, entries):\n    return (entries[key], key)\n",
            "tests/test_api.py": "import unittest\nfrom api import value_for\n\n\nclass LookupTests(unittest.TestCase):\n    def test_value_for(self):\n        self.assertEqual(value_for(\"code\", {\"code\": \"ready\"}), \"READY\")\n",
        },
        "fixes": {
            "api.py": "from storage import lookup\n\n\ndef value_for(key, entries):\n    result, _ = lookup(key, entries)\n    return result.upper()\n",
        },
    },
    {
        "id": "type-iv-01",
        "fault_type": "Type-IV",
        "root_cause_hops": 0,
        "description": "Reads the listener port from the process environment.",
        "files": {
            "api.py": "import os\n\n\ndef listener_port():\n    return int(os.environ[\"APP_PORT\"])\n",
            "network.py": "def endpoint(host, port):\n    return f\"{host}:{port}\"\n",
            "tests/test_api.py": "import os\nimport unittest\nfrom unittest.mock import patch\nfrom api import listener_port\n\n\nclass ListenerPortTests(unittest.TestCase):\n    def test_default_port(self):\n        with patch.dict(os.environ, {}, clear=True):\n            self.assertEqual(listener_port(), 8080)\n",
        },
        "fixes": {
            "api.py": "import os\n\n\ndef listener_port():\n    return int(os.getenv(\"APP_PORT\", \"8080\"))\n",
        },
    },
    {
        "id": "type-iv-02",
        "fault_type": "Type-IV",
        "root_cause_hops": 1,
        "description": "Reads a connection timeout from the service configuration.",
        "files": {
            "api.py": "from connection import timeout_value\n\n\ndef timeout(config):\n    return timeout_value(config)\n",
            "connection.py": "def timeout_value(config):\n    return config[\"connect_timeout\"]\n",
            "tests/test_api.py": "import unittest\nfrom api import timeout\n\n\nclass TimeoutTests(unittest.TestCase):\n    def test_timeout(self):\n        self.assertEqual(timeout({\"timeout\": 12}), 12)\n",
        },
        "fixes": {
            "connection.py": "def timeout_value(config):\n    return config[\"timeout\"]\n",
        },
    },
    {
        "id": "type-iv-03",
        "fault_type": "Type-IV",
        "root_cause_hops": 0,
        "description": "Reads a small application setting from its project resources.",
        "files": {
            "api.py": "from pathlib import Path\n\n\ndef setting_value():\n    return (Path(__file__).parent / \"resources\" / \"app.ini\").read_text(encoding=\"utf-8\").strip()\n",
            "settings.py": "def normalize(value):\n    return value.strip()\n",
            "config/app.ini": "enabled=true\n",
            "tests/test_api.py": "import unittest\nfrom api import setting_value\n\n\nclass SettingValueTests(unittest.TestCase):\n    def test_setting_value(self):\n        self.assertEqual(setting_value(), \"enabled=true\")\n",
        },
        "fixes": {
            "api.py": "from pathlib import Path\n\n\ndef setting_value():\n    return (Path(__file__).parent / \"config\" / \"app.ini\").read_text(encoding=\"utf-8\").strip()\n",
            "config/app.ini": "enabled=true\n",
        },
    },
    {
        "id": "type-iv-04",
        "fault_type": "Type-IV",
        "root_cause_hops": 1,
        "description": "Resolves the configured directory for stored records.",
        "files": {
            "api.py": "from storage_config import records_directory\n\n\ndef record_root():\n    return records_directory()\n",
            "storage_config.py": "import os\n\n\ndef records_directory():\n    return os.getenv(\"DATA_ROOT\", \"/srv/records\")\n",
            "tests/test_api.py": "import os\nimport unittest\nfrom unittest.mock import patch\nfrom api import record_root\n\n\nclass RecordRootTests(unittest.TestCase):\n    def test_configured_root(self):\n        with patch.dict(os.environ, {\"APP_DATA_DIR\": \"/tmp/records\"}, clear=True):\n            self.assertEqual(record_root(), \"/tmp/records\")\n",
        },
        "fixes": {
            "storage_config.py": "import os\n\n\ndef records_directory():\n    return os.getenv(\"APP_DATA_DIR\", \"/srv/records\")\n",
        },
    },
    {
        "id": "type-iv-05",
        "fault_type": "Type-IV",
        "root_cause_hops": 1,
        "description": "Reads a message stored alongside the service resources.",
        "files": {
            "api.py": "from messages import read_message\n\n\ndef message():\n    return read_message()\n",
            "messages.py": "from pathlib import Path\n\n\ndef read_message():\n    return Path(\"resources/message.txt\").read_text(encoding=\"utf-8\").strip()\n",
            "resources/message.txt": "service ready\n",
            "tests/test_api.py": "import os\nimport tempfile\nimport unittest\nfrom api import message\n\n\nclass MessageTests(unittest.TestCase):\n    def test_message_from_other_working_directory(self):\n        previous = os.getcwd()\n        with tempfile.TemporaryDirectory() as other_directory:\n            try:\n                os.chdir(other_directory)\n                self.assertEqual(message(), \"service ready\")\n            finally:\n                os.chdir(previous)\n",
        },
        "fixes": {
            "messages.py": "from pathlib import Path\n\n\ndef read_message():\n    return (Path(__file__).parent / \"resources\" / \"message.txt\").read_text(encoding=\"utf-8\").strip()\n",
        },
    },
    {
        "id": "type-iv-06",
        "fault_type": "Type-IV",
        "root_cause_hops": 0,
        "description": "Converts a configured duration into seconds.",
        "files": {
            "api.py": "def seconds(configuration):\n    return configuration[\"duration\"][\"millisecond\"] / 1000\n",
            "duration.py": "def total_seconds(value):\n    return value * 60\n",
            "tests/test_api.py": "import unittest\nfrom api import seconds\n\n\nclass SecondsTests(unittest.TestCase):\n    def test_configured_duration(self):\n        self.assertEqual(seconds({\"duration\": {\"milliseconds\": 2500}}), 2.5)\n",
        },
        "fixes": {
            "api.py": "def seconds(configuration):\n    return configuration[\"duration\"][\"milliseconds\"] / 1000\n",
        },
    },
]


def write_instance(instance, root):
    instance_dir = root / "instances" / instance["id"]
    repo_dir = instance_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, contents in instance["files"].items():
        path = repo_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8", newline="\n")

    metadata = {
        "id": instance["id"],
        "fault_type": instance["fault_type"],
        "root_cause_hops": instance["root_cause_hops"],
        "test_cmd": TEST_COMMAND,
        "description": instance["description"],
    }
    metadata_path = instance_dir / "meta.json"
    if not metadata_path.exists():
        metadata_path.write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    patch_parts = []
    for relative_path, fixed_contents in instance["fixes"].items():
        original_contents = instance["files"][relative_path]
        if instance["id"] in REPAIRED_INSTANCE_IDS:
            with tempfile.TemporaryDirectory(prefix="benchmark-v2-diff-") as temporary:
                diff_repo = Path(temporary)
                subprocess.run(
                    ["git", "init", "--quiet"],
                    cwd=diff_repo,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                diff_path = diff_repo / relative_path
                diff_path.parent.mkdir(parents=True, exist_ok=True)
                diff_path.write_text(
                    original_contents,
                    encoding="utf-8",
                    newline="\n",
                )
                subprocess.run(
                    ["git", "add", "--", relative_path],
                    cwd=diff_repo,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                diff_path.write_text(
                    fixed_contents,
                    encoding="utf-8",
                    newline="\n",
                )
                diff_result = subprocess.run(
                    ["git", "diff", "--", relative_path],
                    cwd=diff_repo,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                patch_parts.append(diff_result.stdout)
            continue

        diff_lines = list(difflib.unified_diff(
            original_contents.splitlines(keepends=True),
            fixed_contents.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        ))
        if diff_lines:
            patch_parts.append(f"diff --git a/{relative_path} b/{relative_path}\n")
            patch_parts.extend(diff_lines)
    (instance_dir / "reference.patch").write_text(
        "".join(patch_parts),
        encoding="utf-8",
        newline="\n",
    )


def run_command(command, cwd):
    return subprocess.run(
        shlex.split(command),
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def validate_instance(instance_dir):
    metadata = json.loads((instance_dir / "meta.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="benchmark-v2-") as temporary:
        repo_copy = Path(temporary) / "repo"
        shutil.copytree(instance_dir / "repo", repo_copy)
        buggy = run_command(metadata["test_cmd"], repo_copy)
        combined_output = buggy.stdout + buggy.stderr
        if instance_dir.name in REPAIRED_INSTANCE_IDS:
            (instance_dir / "failing.log").write_text(
                combined_output,
                encoding="utf-8",
                newline="\n",
            )

        def output_tail(result):
            return " | ".join((result.stdout + result.stderr).splitlines()[-15:])

        reasons = []
        if buggy.returncode == 0:
            reasons.append(f"buggy tests: {output_tail(buggy)}")

        patch_result = subprocess.run(
            [
                "git", "apply", "--whitespace=nowarn",
                str(instance_dir / "reference.patch")
            ],
            cwd=repo_copy,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if patch_result.returncode != 0:
            patch_stderr = " | ".join(patch_result.stderr.splitlines())
            reasons.append(f"git apply: {patch_stderr or '(no stderr)'}")
            return metadata, buggy.returncode != 0, False, "; ".join(reasons)

        fixed = run_command(metadata["test_cmd"], repo_copy)
        if fixed.returncode != 0:
            reasons.append(f"fixed tests: {output_tail(fixed)}")
        return metadata, buggy.returncode != 0, fixed.returncode == 0, "; ".join(reasons)


def main():
    root = Path(__file__).resolve().parent
    valid = len(CASES) == 24
    valid = valid and all(
        sum(case["fault_type"] == fault_type for case in CASES) == 6
        for fault_type in ("Type-I", "Type-II", "Type-III", "Type-IV")
    )
    valid = valid and sum(case["root_cause_hops"] > 0 for case in CASES) >= 8
    valid = valid and sum(case["root_cause_hops"] == 2 for case in CASES) >= 4

    rows = []
    for instance in CASES:
        instance_dir = root / "instances" / instance["id"]
        if instance["id"] in REPAIRED_INSTANCE_IDS or not instance_dir.exists():
            write_instance(instance, root)
        metadata, buggy_fails, reference_passes, reason = validate_instance(
            instance_dir
        )
        rows.append((
            metadata["id"],
            metadata["fault_type"],
            metadata["root_cause_hops"],
            buggy_fails,
            reference_passes,
            reason,
        ))
        valid = valid and buggy_fails and reference_passes

    headers = ("id", "fault_type", "hops", "buggy_fails", "reference_passes", "reason")
    widths = [
        max(len(str(header)), *(len(str(row[index])) for row in rows))
        for index, header in enumerate(headers)
    ]
    print(" | ".join(str(value).ljust(widths[index]) for index, value in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))

    return 0 if valid and all(row[3] and row[4] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
