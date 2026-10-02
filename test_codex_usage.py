"""Run with: python test_codex_usage.py (stdlib only)."""
import csv
import json
import io
import os
import shutil
import subprocess
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from codex_usage import print_chart, print_table, summarize, write_csv


def event(kind, payload, time="2026-10-02T00:00:00Z"):
    return {"type": kind, "payload": payload, "timestamp": time}


def record(owner, response, inp, cached, out, turn="turn-1", time="2026-10-02T00:00:00Z"):
    return event("token_usage_record", {
        "thread_id": owner, "session_id": "root", "root_turn_id": turn,
        "response_id": response, "usage": {"input_tokens": inp,
        "cached_input_tokens": cached, "output_tokens": out,
        "reasoning_output_tokens": 2}}, time)


def run():
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        def save(name, events):
            path = folder / (name + ".jsonl")
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            return path

        root_meta = event("session_meta", {"id": "root", "session_id": "root", "source": "vscode"})
        r1 = record("root", "r1", 100, 80, 10)
        r2 = record("root", "r2", 200, 100, 20, turn="turn-2")
        snapshot = event("event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 300, "cached_input_tokens": 180, "output_tokens": 30}}})
        root = save("root", [root_meta, r1, r2, snapshot, snapshot])
        child_meta = event("session_meta", {"id": "child", "session_id": "root",
            "parent_thread_id": "root", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}})
        child = save("child", [child_meta, root_meta, r1,
            record("child", "c1", 50, 20, 5)])
        duplicate = save("duplicate", [root_meta, r1, r2])
        rows, warnings = summarize([root, child, duplicate], {"root": "테스트 채팅"})
        assert len(rows) == 1
        row = rows[0]
        assert (row["input_tokens"], row["cached_input_tokens"], row["output_tokens"]) == (350, 200, 35)
        assert row["total_tokens"] == 385  # cache + reasoning are subsets, never added again
        assert row["cache_hit_percent"] == 57.14 and row["calls"] == 3 and row["subagents"] == 1
        assert warnings["duplicate_responses"] == 2
        correction = save("correction", [root_meta, record("root", "r1", 120, 90, 12,
            time="2026-10-02T00:01:00Z")])
        corrected, _ = summarize([root, correction], {})
        assert corrected[0]["total_tokens"] == 352 and corrected[0]["calls"] == 2
        turns, _ = summarize([root, child], {}, by_turn=True)
        assert len(turns) == 2 and sum(r["total_tokens"] for r in turns) == 385
        after, _ = summarize([root, child], {}, since=date(2026, 10, 3))
        assert not after
        other_meta = event("session_meta", {"id": "other", "source": "vscode"})
        other = save("other", [other_meta,
            record("other", "o1", 50, 50, 10),
            record("other", "o2", 100, 90, 10, time="2026-10-03T03:00:00Z"),
            record("other", "o3", 10, 0, 1, time="2026-09-30T03:00:00Z")])
        days, _ = summarize([root, child, other], {}, period="day")
        assert [r["period"] for r in days] == ["2026-09-30", "2026-10-02", "2026-10-03"]
        assert days[1]["thread_id"] == "ALL" and days[1]["cache_hit_percent"] == 62.5
        assert days[1]["total_tokens"] == 445
        scoped, _ = summarize([root, child, other], {}, thread="root", period="day")
        assert len(scoped) == 1 and scoped[0]["total_tokens"] == 385
        weeks, _ = summarize([root, child, other], {}, period="week")
        assert len(weeks) == 1 and weeks[0]["period"] == "2026-W40"
        months, _ = summarize([root, child, other], {}, period="month")
        assert len(months) == 2 and months[1]["total_tokens"] == 555
        with redirect_stdout(io.StringIO()) as chart:
            print_chart(days, 2)
        assert "#" in chart.getvalue() and "2026-09-30" not in chart.getvalue()
        boundary = save("boundary", [other_meta,
            record("other", "o4", 10, 0, 1, time="2027-01-01T03:00:00Z")])
        boundary_rows, _ = summarize([boundary], {}, period="week")
        assert boundary_rows[0]["period"] == "2026-W53"

        legacy_meta = event("session_meta", {"id": "legacy", "source": "vscode"})
        legacy = save("legacy", [legacy_meta, snapshot, snapshot])
        rows, _ = summarize([legacy], {})
        assert rows[0]["total_tokens"] == 330 and rows[0]["calls"] is None
        assert rows[0]["measurement"] == "lifetime_snapshot"
        rows, _ = summarize([legacy], {}, since=date(2026, 10, 1))
        assert rows[0]["total_tokens"] is None and rows[0]["unmeasured_sessions"] == 1

        empty = save("empty", [event("session_meta", {"id": "empty"})])
        rows, _ = summarize([empty], {})
        assert rows[0]["total_tokens"] is None and rows[0]["cache_hit_percent"] is None
        period_rows, _ = summarize([root, child, other, empty], {}, period="day")
        with redirect_stdout(io.StringIO()) as table:
            print_table(period_rows, 2)
        assert "2026-10-02" in table.getvalue() and "2026-10-03" in table.getvalue()
        assert "2026-09-30" not in table.getvalue()
        assert "미측정 세션 1개" in table.getvalue()
        unknown = record("root", "missing-cache", 50, None, 5)
        missing = save("missing", [root_meta, unknown])
        rows, _ = summarize([missing], {})
        assert rows[0]["cache_hit_percent"] is None and rows[0]["unknown_cache_calls"] == 1
        assert rows[0]["cached_input_tokens"] is None

        invalid = record("root", "invalid", 10, 50, 5)
        bad = save("bad", [root_meta, invalid])
        rows, warnings = summarize([bad], {})
        assert warnings["invalid_usage"] == 1 and rows[0]["total_tokens"] is None
        rows, _ = summarize([root], {"root": "=HYPERLINK(\"https://bad.example\")"})
        target = folder / "usage.csv"
        write_csv(target, rows)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            exported = next(csv.DictReader(stream))
        assert exported["title"].startswith("'=")
        assert exported["total_tokens"] == "330"
        shell = shutil.which("sh")
        if not shell and os.name == "nt":
            git_sh = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/sh.exe"
            if git_sh.exists():
                shell = str(git_sh)
        if shell:
            spaced = folder / "launcher with spaces"
            spaced.mkdir()
            for filename in ("usage.sh", "codex_usage.py"):
                shutil.copyfile(Path(__file__).with_name(filename), spaced / filename)
            launcher = (spaced / "usage.sh").as_posix()
            subprocess.run([shell, "-n", launcher], check=True, capture_output=True)
            shell_csv = spaced / "result with spaces.csv"
            result = subprocess.run([shell, launcher, "--codex-home", spaced.as_posix(),
                "--logs", root.as_posix(), "--all-time", "--csv", shell_csv.as_posix()],
                check=True, capture_output=True, encoding="utf-8", cwd=folder)
            assert "#" in result.stdout and "cache 60.0%" in result.stdout
            assert not result.stderr
            assert shell_csv.exists()
        else:
            print("SKIP: sh launcher (no sh installed)")
    print("PASS: deduplication, copied histories, subagents, turns, dates, day/week/month, chart, legacy, missing usage, invalid usage, CSV, sh launcher")


if __name__ == "__main__":
    run()
