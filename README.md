# Codex Hitting Usage

A local command-line tool for measuring Codex token usage and token-based cache hit rates. View results by chat, task turn, day, week, or month, with terminal charts and CSV exports.

Requires **Python 3.10 or newer**. No additional packages or API keys are needed. The tool reads local logs without modifying them or sending data to external servers.

## Download

```sh
git clone https://github.com/formskorea-cto/codex-hitting-usage.git
cd codex-hitting-usage
```

Run the following commands from the cloned directory. Absolute paths below are examples; replace them with your installation path.

## Windows CMD

`usage.cmd` displays a table and an ASCII bar chart.

```cmd
usage.cmd
usage.cmd --period day
usage.cmd --period week
usage.cmd --period month
```

Without `--period`, results are grouped by chat. With `--period`, results are grouped across all selected chats by day, week, or month.

| View | Default reporting window |
| --- | --- |
| Chat, task turn, or day | Last 7 calendar days, including today |
| Week | Last 12 ISO weeks, including the current week |
| Month | Last 12 calendar months, including the current month |

Weeks start on Monday and use ISO week numbers. Dates follow the computer's local time zone. Periods without usable records are not filled with zero usage.

Filter a chat, export CSV, or choose a reporting window:

```cmd
usage.cmd --thread CHAT_UUID --period month --csv monthly-chat.csv
usage.cmd --period week --all-time --csv weekly.csv
usage.cmd --period day --since 2026-09-01 --limit 0
```

Replace `CHAT_UUID` with the chat's full UUID. Selecting a root chat includes its recorded subagent usage.

## POSIX sh: Linux, macOS, WSL, and Git Bash

Keep `usage.sh` and `codex_usage.py` in the same directory. Calling the launcher with `sh` does not require setting executable permissions. It resolves the Python script relative to its own location, so it can be launched from another working directory.

```sh
sh usage.sh
sh usage.sh --period day
sh usage.sh --period week
sh usage.sh --period month --csv monthly.csv
sh usage.sh --thread CHAT_UUID --period day
```

The launcher selects an available `python3` or `python` interpreter running Python 3.10 or newer. It accepts the same options as the CMD launcher.

Git Bash example for a clone at `C:\tools\codex-hitting-usage`:

```sh
sh /c/tools/codex-hitting-usage/usage.sh --period day
```

To read Windows logs from WSL, specify the Windows Codex home directory:

```sh
sh /mnt/c/tools/codex-hitting-usage/usage.sh --codex-home /mnt/c/Users/YOUR_USER/.codex --period day
```

Otherwise, logs are read from the home directory of the environment running Python.

## Direct Python execution

```sh
python codex_usage.py --csv usage.csv
python codex_usage.py --thread CHAT_UUID --by-turn
python codex_usage.py --since 2026-10-02 --limit 0
python codex_usage.py --all-time
python codex_usage.py --help
```

### Options

| Option | Description |
| --- | --- |
| `--codex-home PATH` | Codex home directory; defaults to `CODEX_HOME` or `~/.codex` |
| `--logs PATH` | Additional JSONL file or directory; may be repeated |
| `--thread UUID` | Filter a chat; a root UUID includes recorded subagent usage |
| `--by-turn` | Group by user task turn |
| `--period day`, `--period week`, `--period month` | Group selected chats by calendar period |
| `--since YYYY-MM-DD` | Include responses on or after this local date |
| `--all-time` | Include all available dates |
| `--chart` | Display an ASCII chart; enabled automatically by both launchers |
| `--csv PATH` | Export every matching row, regardless of the table limit |
| `--limit N` | Number of displayed rows; default 20, or 0 for all rows |

`--by-turn` and `--period` are mutually exclusive. So are `--since` and `--all-time`. Period views show the latest periods; chat and turn views show the largest token totals first.

## Log locations and remote chats

The default log directories are `$CODEX_HOME/sessions` and `$CODEX_HOME/archived_sessions`. When `CODEX_HOME` is unset, the tool uses `.codex` in the current user's home directory. Chat titles are read from `session_index.jsonl`. Authentication files and conversation bodies are not included in the output.

Chats running on a remote computer need that computer's logs. Copy the relevant JSONL files, including subagent logs, to your computer and supply the copied file or directory:

```sh
python codex_usage.py --logs /path/to/imported-sessions --thread CHAT_UUID --all-time
```

If you copied the original `.codex` directory structure and its `session_index.jsonl`, use `--codex-home` to point to that directory. Chats without a local title are identified by a shortened UUID.

Raw logs can contain conversations and source code. CSV exports can contain chat titles; review them before sharing.

## Reading the results

Every numeric token column is a token count, not a price or an allowance percentage.

The terminal table uses five token columns, with a separate labeled line for each chat or period. Full chat titles and IDs identify each row; turn IDs appear with `--by-turn`. Request and subagent counts appear below the token values. `Showing X of Y` reports the display limit, while the unmeasured-session footer covers all matching rows. The token header fits within 80 columns for ordinary counts.

```text
Token usage | Showing 1 of 1 periods
All token counts are exact. Cache hit is a token percentage.
 Input tokens |  Cached input | Cache hit % | Output tokens |  Total tokens
---------------------------------------------------------------------------
[1] Period: 2026-10-02 | All chats
        1,000 |           800 |       80.0% |           100 |         1,100
Model requests: 2 | Subagents: 1
---------------------------------------------------------------------------
```

| Metric | Meaning |
| --- | --- |
| Input tokens | All input processed by the model, including cached input |
| Cached input | Input tokens reused from the prompt cache |
| Cache hit % | Cached input divided by input, shown as a percentage |
| Output tokens | Generated output, including reasoning and tool-call arguments |
| Total tokens | Input tokens plus output tokens; cached input is not added again |
| Model requests | Recorded model responses, including subagent responses; not user messages |
| Subagents | Distinct subagents with recorded usage; excludes the root agent |
| Unmeasured sessions | Sessions without usable usage records; excluded from token totals |

A chat row combines that chat's recorded work and its subagents. A period row combines all selected chats for that day, ISO week, or month. Use `--thread` to limit period rows to one chat, or `--by-turn` to separate user task turns.

CSV exports retain exact integer counts and full chat/turn IDs. A blank value means unknown, not zero.

## Calculations and limitations

- **Token cache hit rate** = recorded cached input tokens / recorded input tokens x 100. This is a token-weighted ratio, not the percentage of requests that hit the cache.
- **Total tokens** = input + output. Cached reads and writes are subsets of input; reasoning is a subset of output. They are not added again.
- Current `token_usage_record.usage` entries are summed per response. Duplicate `response_id` entries are counted once, preferring the latest timestamp. Copied parent history is excluded using the owning `thread_id`.
- Subagents are linked to their parent or root chat. Automatic review agents are included when they have token records. The tool does not determine whether those tokens consume paid allowance.
- Sessions without usable usage records are excluded from totals and reported as unmeasured. Missing values display `unknown` in tables and `?` in charts, not zero. Blank CSV fields mean unknown values.
- Legacy logs containing only `token_count` are supported as latest lifetime snapshots with `--all-time`. They cannot establish request counts or period-specific usage. Legacy subagent and explicit fork snapshots are excluded to avoid counting inherited usage.
- Period totals include only responses with usable timestamps and usage records. Legacy or undated records cannot be allocated to calendar periods and remain unmeasured.
- Log formats may change between Codex versions. Active sessions can have records that have not arrived yet. Recorded token counts are not a final bill.
- **Exact subscription allowance deductions, credit charges, and API bills cannot be established from these token logs alone.** Account-wide usage changes can include other chats and are not attributed to one chat.

Chart bars scale to the largest displayed total, with the token cache hit rate shown alongside each bar. CSV files use UTF-8 with a BOM for Excel compatibility, and formula-triggering title prefixes are escaped. Terminal labels and help messages are in English. Chat titles are displayed as recorded.

Official references: [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching), [Observability and usage](https://developers.openai.com/api/docs/guides/agents-api/observability), [Session log locations](https://learn.chatgpt.com/docs/reference/troubleshooting).

## Verification

```sh
python -B test_codex_usage.py
```

The checks cover duplicate and revised responses, copied history, subagent and turn totals, global and chat-specific calendar aggregation, ISO week-year boundaries, charts, date filters, legacy snapshots, missing or invalid counts, and CSV formula escaping.

When `sh` is available, they also check shell syntax, paths containing spaces, execution from another working directory, option forwarding, and CSV creation. Shell-launcher checks are skipped when no supported `sh` installation is found.

## Public domain

This project is released into the public domain under [The Unlicense](LICENSE). You may copy, modify, use, sell, and redistribute it for commercial or non-commercial purposes without attribution. See [LICENSE](LICENSE) for the complete dedication and warranty disclaimer.
