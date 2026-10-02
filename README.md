# Codex Hitting Usage

Codex 채팅별 토큰 사용량과 캐시 적중률을 로컬 로그에서 집계하는 명령줄 도구입니다.

Python 3.10 이상, 추가 패키지·API 키 없이 실행합니다. Codex 로그를 읽기만 하며, 프로그램에서 외부 서버로 데이터를 보내지 않습니다.

## 다운로드

```sh
git clone https://github.com/formskorea-cto/codex-hitting-usage.git
cd codex-hitting-usage
```

아래 경로는 예시입니다. 실제 복제한 폴더에서 실행하세요.

## CMD 차트

CMD에서 폴더로 이동한 뒤 실행합니다. `usage.cmd`는 표와 ASCII 막대 차트를 함께 표시합니다.

```cmd
cd /d C:\tools\codex-hitting-usage
usage.cmd
usage.cmd --period day
usage.cmd --period week
usage.cmd --period month
```

옵션이 없으면 채팅별 합계, `--period`를 지정하면 전체 채팅의 일별·주별·월별 합계입니다. 기본 조회 기간은 각각 최근 7일·이번 주를 포함한 12주·이번 달을 포함한 12개월입니다. 주는 월요일부터 시작하는 ISO 주 번호로 표시합니다. 응답 기록이 없는 기간을 사용량 0으로 만들지 않습니다.

특정 채팅의 월별 사용량과 CSV 저장:

```cmd
usage.cmd --thread CHAT_UUID --period month --csv monthly-chat.csv
usage.cmd --period week --all-time --csv weekly.csv
usage.cmd --period day --since 2026-09-01 --limit 0
```

`--since`는 시작일을 직접 지정하고, `--all-time`은 전체 로그 기간을 조회합니다. 막대 길이는 표시된 행의 총 토큰에 비례하며, 옆에 캐시 입력 비율을 표시합니다. 일·주·월 집계는 기록된 응답의 현지 시각에만 근거합니다. 구형 누적값은 기간에 배분할 수 없어 `미측정`으로 구분합니다. `--by-turn`과 `--period`는 동시에 지정할 수 없습니다.

## sh 차트 (Linux, macOS, WSL, Git Bash)

`usage.sh`와 `codex_usage.py`를 같은 폴더에 두고 실행합니다. 실행 권한 설정 없이 `sh`로 호출할 수 있습니다. 현재 폴더가 달라도 스크립트가 있는 위치를 기준으로 Python 프로그램을 찾습니다.

```sh
sh /path/to/codex-hitting-usage/usage.sh
sh /path/to/codex-hitting-usage/usage.sh --period day
sh /path/to/codex-hitting-usage/usage.sh --period week
sh /path/to/codex-hitting-usage/usage.sh --period month --csv monthly.csv
sh /path/to/codex-hitting-usage/usage.sh --thread CHAT_UUID --period day
```

Git Bash에서 C:\tools\codex-hitting-usage에 복제한 경우의 예시입니다.

```sh
sh /c/tools/codex-hitting-usage/usage.sh --period day
```

WSL에서 Windows 로그를 읽으려면 Windows 사용자 폴더를 명시합니다. 지정하지 않으면 실행 환경의 사용자 폴더에서 로그를 읽습니다.

```sh
sh /mnt/c/tools/codex-hitting-usage/usage.sh --codex-home /mnt/c/Users/YOUR_USER/.codex --period day
```

기존 CMD 옵션을 그대로 사용할 수 있습니다. 실행 가능한 Python 3.10 이상의 `python3` 또는 `python`을 자동으로 선택합니다.

## Python 직접 실행

최근 7일의 채팅별 입력·캐시 입력·출력·총 토큰과 캐시 적중률을 확인하고 CSV로 저장합니다.

```powershell
python "codex_usage.py" --csv "usage.csv"
```

특정 채팅을 사용자 작업 턴별로 확인합니다. 루트 채팅 UUID를 지정하면 기록이 있는 하위 에이전트도 함께 합산합니다.

```powershell
python "codex_usage.py" --thread CHAT_UUID --by-turn
```

특정 날짜 이후 또는 전체 기간을 확인합니다. 날짜는 실행 컴퓨터의 현지 시간 기준이며, 기간 필터는 응답 시각에 적용됩니다.

```powershell
python "codex_usage.py" --since 2026-10-02 --limit 0
python "codex_usage.py" --all-time
```

기본 입력 경로는 `$CODEX_HOME/sessions`, `$CODEX_HOME/archived_sessions`입니다. `CODEX_HOME`이 없으면 사용자 폴더의 `.codex`를 사용합니다. 제목은 같은 폴더의 `session_index.jsonl`에서 읽습니다. 인증 파일이나 대화 본문을 출력하지 않습니다.

## 원격 채팅

원격 컴퓨터에서 실행되는 채팅은 로컬 로그에 없습니다. 원격의 `~/.codex/sessions`에서 관련 JSONL 파일과 하위 에이전트 로그를 로컬로 복사한 뒤 추가 입력으로 지정하세요. `--logs`는 여러 번 사용할 수 있습니다.

```powershell
python "codex_usage.py" --logs "C:\tools\imported-sessions" --thread CHAT_UUID --all-time
```

복사한 폴더에 해당 파일이 있어야 합니다. 제목이 없는 원격 채팅은 UUID 일부로 표시됩니다. 원격의 `.codex` 구조와 `session_index.jsonl`까지 복사했다면 `--codex-home`으로 해당 폴더를 지정할 수 있습니다. 로그에는 대화와 코드가 포함될 수 있으므로 CSV 공유 시에도 채팅 제목을 확인하세요.

## 계산과 한계

- 캐시 적중률 = 기록된 캐시 입력 토큰 합 / 입력 토큰 합 × 100. 호출 적중률이 아니라 **토큰 기준 비율**입니다.
- 총 토큰 = 입력 + 출력. 캐시 읽기·쓰기는 입력에, 추론은 출력에 포함되므로 다시 더하지 않습니다.
- 현재 형식의 `token_usage_record.usage`를 응답별로 합산합니다. `response_id` 중복은 한 번만 반영하고, 복사된 부모 기록은 기록 소유자 `thread_id`로 제외합니다. 같은 응답의 수정 기록은 최신 시각을 우선합니다.
- 하위 에이전트는 부모/루트 채팅과 연결해 합산합니다. 자동 검토 에이전트도 토큰 기록이 있으면 포함합니다. 이것이 유료 사용량에 해당하는지는 프로그램이 판정하지 않습니다.
- 기록되지 않은 세션은 합계에서 제외하고 미측정 수를 표시합니다. 캐시 값이 없으면 0% 대신 `?`를 표시합니다. CSV의 빈 값은 알 수 없는 값입니다.
- 구형 `token_count`만 있는 로그는 `--all-time`에서 최신 누적 스냅샷을 사용합니다. 이 형식으로는 호출 수·기간별 사용량을 확정하지 않습니다. 하위/명시적 포크의 구형 누적값은 상속된 기록을 잘못 합산하지 않도록 제외합니다.
- 로그 형식은 Codex 버전에 따라 달라질 수 있습니다. 실행 중에는 아직 도착하지 않은 기록이 있을 수 있습니다. 기록된 토큰 수는 최종 청구서가 아닙니다.
- **실제 구독 한도 차감률·크레딧 차감액·API 청구액은 확정하지 않습니다.** 계정 전체 사용률의 전후 차이는 다른 채팅의 작업과 섞이므로 해당 채팅의 사용량으로 표시하지 않습니다.

CSV는 Excel에서 열 수 있도록 UTF-8 BOM으로 저장하며, 제목의 수식 실행 문자를 이스케이프합니다. `--limit`은 터미널 표에만 적용되고 CSV에는 조건에 맞는 모든 행이 저장됩니다.

공식 참고: [캐시 계산 방식](https://developers.openai.com/api/docs/guides/prompt-caching), [사용량과 과금의 구분](https://developers.openai.com/api/docs/guides/agents-api/observability), [로컬 세션 로그 위치](https://learn.chatgpt.com/docs/reference/troubleshooting).

## 검증

```powershell
python "test_codex_usage.py"
```

중복 응답·수정된 응답·복사된 부모 기록·하위 에이전트·턴별 합계·전체 및 특정 채팅의 일/주/월 집계·ISO 주 연도 경계·차트·기간 필터·구형 누적값·누락 및 잘못된 토큰값·CSV 수식 이스케이프를 검사합니다. `sh`가 있으면 셸 문법과 공백이 있는 경로·다른 작업 폴더에서의 실행·옵션 전달·CSV 생성도 확인합니다.
