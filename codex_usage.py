"""Read Codex JSONL token ledgers locally, without APIs or dependencies."""
import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def usage_counts(raw):
    if not isinstance(raw, dict):
        return None
    def count(key):
        value = raw.get(key)
        return value if type(value) is int and value >= 0 else None
    inp, out, cached = count("input_tokens"), count("output_tokens"), count("cached_input_tokens")
    if inp is None or out is None or (cached is not None and cached > inp):
        return None
    return {"input": inp, "cached": cached, "output": out,
            "reasoning": count("reasoning_output_tokens"),
            "cache_write": count("cache_write_input_tokens")}


def read_log(path, warnings):
    meta, records, latest, model = None, [], None, "unknown"
    compacted = 0
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as stream:
            for index, line in enumerate(stream):
                # Conversation/tool bodies are never returned or stored.
                if not any(marker in line for marker in
                           ('"session_meta"', '"token_usage_record"', '"token_count"',
                            '"turn_context"', '"compacted"')):
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    warnings["malformed_lines"] += 1
                    continue
                if not isinstance(item, dict):
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                kind = item.get("type")
                if kind == "session_meta" and meta is None:
                    meta = payload
                elif kind == "turn_context":
                    model = payload.get("model") or model
                elif kind == "compacted":
                    compacted += 1
                elif kind == "token_usage_record":
                    counts = usage_counts(payload.get("usage"))
                    if counts is None:
                        warnings["invalid_usage"] += 1
                        continue
                    records.append({**counts, "thread": payload.get("thread_id"),
                                    "session": payload.get("session_id"),
                                    "turn": payload.get("root_turn_id") or payload.get("turn_id"),
                                    "response": payload.get("response_id"), "model": model,
                                    "time": timestamp(item.get("timestamp")), "ordinal": index})
                elif kind == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    if not isinstance(info, dict):
                        warnings["invalid_usage"] += 1
                        continue
                    counts = usage_counts(info.get("total_token_usage"))
                    if counts is not None:
                        latest = {**counts, "time": timestamp(item.get("timestamp")),
                                  "model": model, "turn": "unknown"}
    except OSError as error:
        warnings["unreadable_files"] += 1
        print(f"읽기 실패: {path.name}: {error.strerror}", file=sys.stderr)
    if not meta or not meta.get("id"):
        return None
    owner = meta["id"]
    source = meta.get("source")
    subagent = meta.get("thread_source") == "subagent" or isinstance(source, dict) and "subagent" in source
    spawn = (source.get("subagent", {}).get("thread_spawn", {})
             if isinstance(source, dict) and isinstance(source.get("subagent"), dict) else {})
    return {"id": owner, "parent": meta.get("parent_thread_id") or spawn.get("parent_thread_id"),
            "session": meta.get("session_id"), "subagent": subagent,
            "records": [r for r in records if r["thread"] == owner],
            "latest": latest, "compactions": compacted,
            "legacy_safe": not subagent and not meta.get("forked_from_id")}


def find_logs(home, extras):
    paths = set()
    for root in [home / "sessions", home / "archived_sessions", *extras]:
        if root.is_file():
            paths.add(root.resolve())
        elif root.is_dir():
            paths.update(p.resolve() for p in root.rglob("*.jsonl"))
        elif root in extras:
            raise ValueError(f"로그 경로가 없습니다: {root}")
    return sorted(paths)


def read_titles(home):
    titles = {}
    path = home / "session_index.jsonl"
    if path.exists():
        with path.open(encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get("id") and entry.get("thread_name"):
                        titles[entry["id"]] = entry["thread_name"]
                except ValueError:
                    continue
    return titles


def period_key(when, period):
    if when is None:
        return "미측정"
    day = when.date()
    if period == "day":
        return day.isoformat()
    if period == "week":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02}"
    return day.strftime("%Y-%m")


def summarize(paths, titles, since=None, thread=None, by_turn=False, period=None):
    warnings = defaultdict(int)
    logs = [result for p in paths if (result := read_log(p, warnings)) is not None]
    metadata = {log["id"]: log for log in logs}

    def root_id(log):
        current, visited = log, set()
        while current["subagent"] and current["parent"] and current["id"] not in visited:
            visited.add(current["id"])
            parent = current["parent"]
            if parent not in metadata:
                # Session ID is the root for current multi-agent logs.
                return current["session"] if current["session"] != current["id"] and current["session"] else parent
            current = metadata[parent]
        return current["id"]

    groups, selected, legacy = {}, {}, {}

    def group(root, turn="unknown", when=None):
        bucket = period_key(when, period) if period else ""
        owner = (thread or "ALL") if period else root
        key = (owner, bucket if period else turn if by_turn else "")
        if key not in groups:
            groups[key] = {"thread_id": owner, "title": "전체 채팅" if owner == "ALL" else titles.get(root, root[:13]),
                           "turn_id": turn if by_turn else "", "period": bucket, "calls": 0,
                           "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
                           "reasoning_tokens": 0, "cache_write_tokens": 0,
                           "unknown_cache_calls": 0, "unknown_reasoning_calls": 0,
                           "unknown_write_calls": 0, "unknown_sessions": set(),
                           "agents": set(), "models": set(), "sources": set(), "last": None}
        return groups[key]

    def add(row, record, owner, subagent, source):
        row["input_tokens"] += record["input"]
        row["output_tokens"] += record["output"]
        for raw, field, missing in (("cached", "cached_input_tokens", "unknown_cache_calls"),
                                    ("reasoning", "reasoning_tokens", "unknown_reasoning_calls"),
                                    ("cache_write", "cache_write_tokens", "unknown_write_calls")):
            if record[raw] is None:
                row[missing] += 1
            else:
                row[field] += record[raw]
        row["models"].add(record["model"])
        row["sources"].add(source)
        if subagent:
            row["agents"].add(owner)
        if record["time"] and (row["last"] is None or record["time"] > row["last"]):
            row["last"] = record["time"]

    for log in logs:
        root = root_id(log)
        if thread and root != thread and log["id"] != thread:
            continue
        if log["records"]:
            for record in log["records"]:
                if since and (record["time"] is None or record["time"].date() < since):
                    continue
                # Copies of forked histories and resumed files share response IDs.
                identity = (log["id"], record["response"] or
                            (str(record["time"]), record["turn"], record["input"], record["output"]))
                if identity in selected:
                    warnings["duplicate_responses"] += 1
                    previous = selected[identity][2]
                    if previous["time"] and (record["time"] is None or record["time"] < previous["time"]):
                        continue
                selected[identity] = (log, root, record)
        elif log["latest"] and log["legacy_safe"] and since is None and not by_turn and not period:
            candidate = log["latest"]
            previous = legacy.get(log["id"])
            if previous is None or (candidate["time"] and
                                     (previous[1]["time"] is None or candidate["time"] > previous[1]["time"])):
                legacy[log["id"]] = (root, candidate)
        else:
            if log["latest"] and since and log["latest"]["time"] and log["latest"]["time"].date() < since:
                continue
            group(root)["unknown_sessions"].add(log["id"])

    # Prefer individual response records to lifetime snapshots of the same owner.
    for log, root, record in selected.values():
        row = group(root, record["turn"], record["time"])
        if period and record["time"] is None:
            row["unknown_sessions"].add(log["id"])
            continue
        row["calls"] += 1
        add(row, record, log["id"], log["subagent"], "response_ledger")
    ledger_owners = {identity[0] for identity in selected}
    for owner, (root, record) in legacy.items():
        if owner not in ledger_owners:
            add(group(root), record, owner, False, "lifetime_snapshot")

    rows = []
    for row in groups.values():
        row["total_tokens"] = row["input_tokens"] + row["output_tokens"]
        row["cache_hit_percent"] = (round(row["cached_input_tokens"] * 100 / row["input_tokens"], 2)
                                    if row["input_tokens"] and not row["unknown_cache_calls"] else None)
        row["uncached_input_tokens"] = (row["input_tokens"] - row["cached_input_tokens"]
                                         if not row["unknown_cache_calls"] else None)
        row["subagents"] = len(row.pop("agents"))
        row["unmeasured_sessions"] = len(row.pop("unknown_sessions"))
        row["models"] = ",".join(sorted(row["models"]))
        row["measurement"] = ",".join(sorted(row.pop("sources"))) or "unavailable"
        row["last_recorded_at"] = row.pop("last")
        row["last_recorded_at"] = row["last_recorded_at"].isoformat() if row["last_recorded_at"] else ""
        for missing, field in (("unknown_cache_calls", "cached_input_tokens"),
                               ("unknown_reasoning_calls", "reasoning_tokens"),
                               ("unknown_write_calls", "cache_write_tokens")):
            if row[missing]:
                row[field] = None
        if row["measurement"] == "unavailable":
            for field in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens",
                          "reasoning_tokens", "cache_write_tokens", "uncached_input_tokens"):
                row[field] = None
        if "lifetime_snapshot" in row["measurement"]:
            row["calls"] = None
        rows.append(row)
    if period:
        rows.sort(key=lambda r: r["period"])
    else:
        rows.sort(key=lambda r: r["total_tokens"] if r["total_tokens"] is not None else -1, reverse=True)
    return rows, dict(warnings)


def safe_cell(value):
    # CSV formula injection: chat titles are untrusted user content.
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text


def write_csv(path, rows):
    fields = ["thread_id", "title", "turn_id", "period", "calls", "input_tokens", "cached_input_tokens",
              "cache_hit_percent", "uncached_input_tokens", "cache_write_tokens", "output_tokens",
              "reasoning_tokens", "total_tokens", "subagents", "unmeasured_sessions", "models",
              "measurement", "unknown_cache_calls", "unknown_reasoning_calls", "unknown_write_calls",
              "last_recorded_at"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else safe_cell(value) for key, value in row.items()})


def label(text, width):
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(text))
    full_width = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    if full_width <= width:
        return text + " " * (width - full_width)
    result, size = "", 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if size + char_width > width - 1:
            return result + "…" + " " * (width - size - 1)
        size += char_width
        result += char
    return result + " " * (width - size)


def print_table(rows, limit):
    heading = "기간" if any(r["period"] for r in rows) else "채팅"
    print(f"{heading:<22} {'호출':>6} {'입력':>12} {'캐시 입력':>12} {'캐시%':>7} {'출력':>10} {'합계':>12} {'하위':>4}")
    if any(r["period"] for r in rows):
        dated = [r for r in rows if r["period"] != "미측정"]
        visible = dated[-limit:] if limit else dated
    else:
        visible = rows[:limit or None]
    for row in visible:
        def number(field):
            value = row[field]
            return f"{value:,}" if value is not None else "?"
        percent = f"{row['cache_hit_percent']:.1f}%" if row["cache_hit_percent"] is not None else "?"
        name = row["period"] or (row["title"] if not row["turn_id"] else
                                 label(row["title"], 15).rstrip() + "/" + row["turn_id"][:8])
        print(f"{label(name, 26)} {number('calls'):>6} {number('input_tokens'):>12} "
              f"{number('cached_input_tokens'):>12} {percent:>7} {number('output_tokens'):>10} "
              f"{number('total_tokens'):>12} {row['subagents']:>4}")
    print(f"\n집계 행 {len(rows)}개 · 미측정 세션 {sum(r['unmeasured_sessions'] for r in rows)}개")
    print("캐시% = 캐시 입력 / 입력 × 100. 합계 = 입력 + 출력(추론 포함); 캐시는 입력에 포함됩니다.")
    print("수치는 기록된 사용량입니다. 미측정 세션은 합계에서 제외되며, 하위는 측정된 에이전트 수입니다.")
    print("구독 한도 차감률·실제 청구액은 이 토큰 기록만으로 확정할 수 없습니다. ? = 기록 없음.")


def print_chart(rows, limit):
    measured = [r for r in rows if r["total_tokens"] is not None]
    if limit:
        measured = measured[-limit:] if any(r["period"] for r in rows) else measured[:limit]
    if not measured:
        print("\n차트에 표시할 사용량 기록이 없습니다.")
        return
    largest = max(r["total_tokens"] for r in measured)
    print("\n총 토큰 차트 (# = 표시된 최댓값의 1/24)")
    for row in measured:
        name = row["period"] or row["title"]
        if row["turn_id"]:
            name = label(name, 13).rstrip() + "/" + row["turn_id"][:8]
        width = max(1, round(row["total_tokens"] * 24 / largest)) if largest and row["total_tokens"] else 0
        cached = f"{row['cache_hit_percent']:.1f}%" if row["cache_hit_percent"] is not None else "?"
        print(f"{label(name, 24)} |{'#' * width:<24}| {row['total_tokens']:>12,}  cache {cached}")


def default_since(period):
    today = date.today()
    if period == "week":
        return today - timedelta(days=today.weekday() + 77)
    if period == "month":
        year, month = divmod(today.year * 12 + today.month - 1 - 11, 12)
        return date(year, month + 1, 1)
    return today - timedelta(days=6)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--logs", type=Path, action="append", default=[], help="추가 JSONL 파일 또는 폴더 (원격에서 복사한 로그 등)")
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument("--since", type=date.fromisoformat, help="이 날짜 이후의 응답 사용량 (컴퓨터 현지 날짜)")
    dates.add_argument("--all-time", action="store_true", help="전체 기간, 구형 로그의 누적 스냅샷 포함")
    parser.add_argument("--thread", help="채팅 UUID. 루트 UUID를 지정하면 하위 에이전트 포함")
    views = parser.add_mutually_exclusive_group()
    views.add_argument("--by-turn", action="store_true", help="사용자 작업 턴별로 구분")
    views.add_argument("--period", choices=("day", "week", "month"), help="일별/주별(월요일 시작)/월별. --thread 미지정 시 전체 채팅 합산")
    parser.add_argument("--chart", action="store_true", help="CMD 호환 ASCII 막대 차트 표시")
    parser.add_argument("--csv", type=Path, help="표시 제한과 무관하게 모든 결과를 CSV로 저장")
    parser.add_argument("--limit", type=int, default=20, help="표에서 표시할 행 수 (0 = 전체)")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit은 0 이상이어야 합니다.")
    since = None if args.all_time else args.since or default_since(args.period)
    try:
        paths = find_logs(args.codex_home, args.logs)
        if since:
            paths = [p for p in paths if datetime.fromtimestamp(p.stat().st_mtime).date() >= since]
        print(f"로컬 로그 {len(paths)}개 분석 · {'전체 기간' if since is None else str(since) + ' 이후'}")
        # ponytail: scan selected files; add an incremental index if repeated scans become too slow.
        rows, warnings = summarize(paths, read_titles(args.codex_home), since, args.thread, args.by_turn, args.period)
        if not rows:
            print("해당 기록이 없습니다. 원격 채팅은 원격 JSONL을 복사한 뒤 --logs로 지정하세요.")
            return 1
        print_table(rows, args.limit)
        if args.chart:
            print_chart(rows, args.limit)
        if args.csv:
            write_csv(args.csv, rows)
            print(f"CSV: {args.csv.resolve()}")
        if warnings:
            print("기록 처리:", ", ".join(f"{key}={value}" for key, value in warnings.items()))
    except (OSError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
