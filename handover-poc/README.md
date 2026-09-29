# handover-poc

반도체 불량 대응 인수인계 자동화 — 핵심 로직 PoC (1단계).

세 개의 공개 데이터셋(UCI SECOM, NASA IMS 베어링 진동, WM-811K)에서 뽑은 신호를 하나의
가상 불량 이벤트로 묶고, 규칙 기반 엔진으로 원인을 판정해 주관 부서(M-ENG/P-ENG/YI)를
제안하는 시스템의 프로토타입입니다. 핵심 로직(ingest/signals/scenarios/diagnosis)은
순수 함수 위주로 짜여 있고, CLI·SQLite·FastAPI·부서 간 인수인계("핑퐁") 추적·Streamlit
대시보드가 모두 그 위에 얇게 얹혀 있습니다. PDF·LLM 요약은 다음 단계입니다.

[Quick Start](#quick-start) · [Data](#data) · [CLI](#cli-usage) · [API](#api-usage-fastapi) ·
[Handover tracking](#handover-tracking-핑퐁) · [PDF report](#pdf-report) · [LLM summary](#llm-summary-claude-api) ·
[Dashboard](#dashboard-streamlit) · [Docker](#docker-배포) · [Testing](#testing) ·
[Results](#results-배치-실험-결과) · [Scope](#scope) · [Troubleshooting](#troubleshooting) ·
[Design notes](#design-notes)

---

## Quick Start

```bash
# 1) 가상환경 (Python 3.11 권장 — 3.14도 설치돼 있었지만 scikit-learn 등 과학 패키지의
#    휠 호환성이 더 안정적인 3.11로 새로 만들었습니다)
py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

> [!IMPORTANT]
> 실행 전에 원본 데이터셋을 `data/raw/`에 직접 준비해야 합니다(저장소에는 포함되어 있지 않습니다). 배치 방법은 [Data](#data)를 참고하세요.

```bash
# 2) 프로젝트 루트(handover-poc/)에서 이벤트 1건 생성
./.venv/Scripts/python.exe -m src.cli generate --scenario SC-EQ --seed 42 --out output/events/
```

`output/events/EVT-<timestamp>-<random4>.json`과 `output/handover.db`(SQLite)가 함께 생성됩니다.

---

## Data

| 데이터셋 | 경로 | 핵심 사항 |
|---|---|---|
| UCI SECOM | `data/raw/uci-secom.csv` | 1,567행, 591개 센서 컬럼. `Pass/Fail`은 `-1=정상, 1=불량`으로 인코딩 |
| NASA IMS 진동 | `data/raw/vibration/` | 이 환경에는 Set 2 파일 1개(`2004.02.12.10.32.39`)만 존재 → 항상 `single_file` 모드, `health_index`는 항상 `None` |
| WM-811K | `data/raw/wm811k/LSWMD.pkl` | 811,457행 중 라벨 있는 172,950행만 사용. 최초 로딩 5~8분, 이후 캐시로 수 초 |

```text
data/raw/
├── uci-secom.csv
├── vibration/
│   └── 2004.02.12.10.32.39           # 파일이 1개면 single_file 모드, 여러 개면 full_baseline 모드
└── wm811k/
    ├── LSWMD.pkl                      # 최초 실행 시에만 필요 (이후엔 캐시로 대체)
    └── wm811k_labeled_cache.pkl       # 자동 생성됨, git-ignored
```

> [!NOTE]
> 세 데이터는 서로 다른 장비·연도·기관의 것을 인위적으로 묶은 것이라, 모든 이벤트에 `"is_simulated": true`와 각 신호의 `source_ref`(원본 행/파일 위치)가 남습니다. 인과관계가 아니라 시나리오 입력으로만 취급하세요.

<details>
<summary>데이터셋별 상세 (라벨 인코딩, 호환성 패치, 캐시 동작)</summary>

- **SECOM**: `Pass/Fail`은 **-1=정상, 1=불량**으로 인코딩되어 있습니다(`src/ingest/loaders.py`의 `SECOM_LABEL_PASS`/`SECOM_LABEL_FAIL` 상수 참고). 센서 591개가 무엇을 측정하는지는 공개 자료에 없어, 모든 센서는 `sensor_id`만 부여하고 `unit`/`meaning`은 항상 `"unknown"`으로 표기합니다.
- **NASA IMS 진동**: Set 2 전체(984개 파일)는 받지 않기로 하고, 파일 하나(20,480개 샘플)를 유의미한 실측 데이터로 인용하는 **의도적으로 고정된 설계**입니다. 진동 신호는 항상 `single_file` 모드로 처리되어 RMS만 계산하고 `health_index`는 항상 `None`입니다(기준선을 계산할 다른 파일이 없기 때문). `health_index`가 필요한 판정 항목(`vibration_hi`, `vibration_normal`)은 이 모드에서 기여도 0으로 빠지고, 그 사유가 이벤트 JSON의 `diagnosis.notes`에 남습니다. `src/ingest/loaders.py`의 `load_vibration_rms`는 폴더 안 파일 개수로 모드를 자동 판별하도록 구현되어 있어, 파일이 여러 개로 바뀌면 코드 변경 없이 `full_baseline` 모드로 전환은 되지만 현재는 쓰지 않습니다.
- **WM-811K**: `src/ingest/wm811k.py`가 실 데이터에서 `pattern_group` 조건에 맞는 라벨링된 웨이퍼를 시드 기반으로 결정적으로 샘플링합니다(`src/ingest/wafer_mock.py`의 목업 생성기는 이제 테스트/오프라인 개발용 픽스처로만 남아 있습니다). `LSWMD.pkl`은 매우 오래된 pandas/Python 2로 저장되어 (a) `pandas.indexes.*` 모듈 경로가 최신 pandas(3.x)에는 없고, (b) numpy 배열 원본 바이트가 Python 2 문자열(STRING opcode)로 저장돼 있어 기본 ASCII 디코딩이 실패합니다. `src/ingest/wm811k.py`가 이 두 문제를 호환 패치(`pandas.compat.pickle_compat`의 클래스 위치 맵 확장 + `encoding="latin1"`)로 직접 처리합니다. 순수 파이썬 Unpickler를 타기 때문에 최초 1회 로딩에 5~8분 정도 걸리며, 이후에는 라벨 있는 172,950행만 추려낸 캐시(`data/raw/wm811k/wm811k_labeled_cache.pkl`, 약 250MB)를 만들어 두고 다음부터는 그 캐시를 즉시 읽습니다(수 초). 캐시는 `.gitignore`에 포함되어 있으니, 삭제하면 다음 실행 때 원본에서 다시 5~8분간 재생성됩니다.

</details>

---

## CLI usage

프로젝트 루트(`handover-poc/`)에서 실행합니다.

```bash
# 이벤트 1건 생성 (output/events/EVT-<timestamp>-<random4>.json + output/handover.db)
./.venv/Scripts/python.exe -m src.cli generate --scenario SC-EQ --seed 42 --out output/events/

# 정합성 검증만 단독 실행
./.venv/Scripts/python.exe -m src.cli validate --event-file output/events/EVT-xxxx.json

# 배치 실험: 4개 시나리오 x seed 0~49 = 200개 이벤트 + 혼동행렬 (DB에도 저장)
./.venv/Scripts/python.exe -m src.cli batch --seeds 50 --out output/experiments/

# 기존 JSON 이벤트들을 DB로 일괄 이전 (이미 저장된 event_id는 덮어씀)
./.venv/Scripts/python.exe -m src.cli migrate --events-dir output/events --db output/handover.db

# DB에 저장된 이벤트 조회 (필터 가능)
./.venv/Scripts/python.exe -m src.cli list --db output/handover.db --scenario SC-EQ --dept M-ENG
```

| 시나리오 ID | 의미 |
|---|---|
| `SC-EQ` | 설비 기인 |
| `SC-PR` | 공정 기인 |
| `SC-UN` | 원인 불명확 |
| `SC-NG` | 정상 |

가중치·임계값은 `config/rules.yaml`, 시나리오 정의는 `config/scenarios.yaml`에 있습니다.

> [!NOTE]
> 같은 `--scenario`/`--seed`로 두 번 실행하면 신호(`signals`)와 판정(`diagnosis`)은 완전히 동일합니다. `event_id`/`event_time`은 생성 시각을 담는 메타데이터라 매번 새로 발급됩니다.

### 영속화 (SQLite)

`generate`/`batch`는 기본적으로 이벤트를 `output/handover.db`(SQLite, git-ignored)에도 저장합니다. `--no-db`로 끌 수 있고, `--db <path>`로 다른 경로를 쓸 수 있습니다. 스키마는 `src/storage/repository.py`의 `events` 테이블 하나 — 조회용 컬럼(scenario_id, primary_dept, rule_id 등)과 원본을 그대로 보존하는 `raw_json` 컬럼을 함께 둡니다. `event_id`가 기본키라 같은 이벤트를 다시 저장하면 덮어씁니다(upsert).

---

## API usage (FastAPI)

```bash
./.venv/Scripts/python.exe -m uvicorn src.api.main:app --reload
```

앱 시작 시 `SamplingContext`(SECOM/진동/WM-811K + 학습된 센서 모델)를 한 번만 로드해 재사용합니다(요청마다 다시 로드하지 않음).

| 메서드/경로 | 설명 |
|---|---|
| `GET /health` | 헬스체크 |
| `GET /scenarios` | `config/scenarios.yaml`의 시나리오 정의 |
| `POST /events/generate` | `{"scenario_id": "SC-EQ", "seed": 42}` → 이벤트 생성 + DB 저장 |
| `GET /events/{event_id}` | 단일 이벤트 조회 (없으면 404) |
| `GET /events?scenario_id=&primary_dept=&limit=&offset=` | 필터 조회 |
| `POST /validate` | `{"event": {...}}` → 정합성 검증 (실패 시 422) |

CLI의 `build_event`/`load_rules`와 `storage/repository.py`를 그대로 재사용하고, 이 모듈에는 진단/신호/시나리오 로직이 전혀 없습니다 — 순수 함수를 HTTP로 감싸기만 했습니다.

---

## Handover tracking (핑퐁)

이벤트가 처음 생성될 때의 `diagnosis.primary_dept`는 규칙 엔진의 판정일 뿐, 실제로는 부서 간에 여러 번 재할당("핑퐁")될 수 있습니다. 이벤트 JSON(불변)과는 성격이 달라 별도의 `handovers` 테이블(이벤트당 여러 행, append-only)로 추적합니다.

| 유효한 부서 | `YI` · `MFG` · `M-ENG` · `P-ENG` (`src/handover/tracker.py`의 `VALID_DEPTS`) |
|---|---|

순수 함수 `validate_handover`가 (1) 알 수 없는 부서, (2) 이유 없는 재할당, (3) 같은 부서로의 무의미한 재할당을 거부합니다.

```bash
# 재할당 기록 (직전 담당 부서는 자동으로 추적된 현재 상태에서 가져옴)
./.venv/Scripts/python.exe -m src.cli handover --event-id EVT-xxxx --to P-ENG --reason "설비 이상 없음 확인"

# 이력 + 핑퐁 횟수 조회
./.venv/Scripts/python.exe -m src.cli history --event-id EVT-xxxx
```

API: `POST /events/{event_id}/handovers` (`{"to_dept": "...", "reason": "..."}`), `GET /events/{event_id}/handovers` → `{"current_dept", "pingpong_count", "history"}`. 첫 재할당의 `from_dept`는 이벤트의 원래 `primary_dept`에서 자동으로 채워지고, 그 다음부터는 직전 `to_dept`에서 이어집니다.

---

## PDF report

이벤트 + 핑퐁 이력을 한 장짜리 "인수인계 보고서" PDF로 렌더링합니다(`src/report/pdf.py`, ReportLab). 판정 결과(규칙·점수·근거)와 신호 요약, 재할당 이력, "이 결과는 시뮬레이션 데이터입니다" 안내 문구까지 포함합니다.

```bash
./.venv/Scripts/python.exe -m src.cli report --event-id EVT-xxxx --out output/reports/
```

API: `GET /events/{event_id}/report.pdf` (`Content-Type: application/pdf`, 없는 이벤트는 404). 대시보드 "이벤트 상세" 페이지에는 "PDF 다운로드" 버튼으로도 붙어 있습니다 — 셋 다 같은 `generate_handover_pdf()`를 호출합니다.

> [!NOTE]
> 한글 폰트는 Windows/Linux/macOS 순서로 흔한 설치 경로(Malgun Gothic, NanumGothic 등)를 찾아 실제로 임베드하며, 못 찾으면 CID 폰트로 폴백합니다(`_register_fonts()`). 관련 경위는 [Design notes](#design-notes)를 참고하세요.

---

## LLM summary (Claude API)

이벤트의 판정 근거(rule_id·scores·contributions·notes)와 핑퐁 이력을 실무자가 바로 읽을 수 있는 한국어 요약으로 바꿔줍니다(`src/llm/summarize.py`, Claude API, 모델 `claude-opus-5`). 시스템 프롬프트에 이 프로젝트의 원칙을 그대로 강제합니다 — "판정 점수"를 "확률"/"신뢰도"라고 부르지 말 것, 시뮬레이션 데이터임을 숨기지 말 것, 주어진 근거 밖의 원인을 추측하지 말 것.

```bash
# ANTHROPIC_API_KEY 필요
./.venv/Scripts/python.exe -m src.cli summarize --event-id EVT-xxxx
```

API: `GET /events/{event_id}/summary` → `{"event_id", "summary"}` (인증 실패 시 503). 대시보드 "이벤트 상세" 페이지에는 "AI 요약" 카드로 붙어 있습니다.

> [!NOTE]
> 인증은 SDK가 알아서 처리합니다(`ANTHROPIC_API_KEY` 환경변수 또는 `ant auth login` 프로필) — 코드가 `os.environ`을 직접 검사하지는 않습니다. 인증 실패는 `anthropic.AuthenticationError`를 잡아 사람이 읽을 수 있는 `RuntimeError`로 바꿔 CLI(`ClickException`)/API(503)/대시보드(`st.warning`) 각자의 방식으로 보여줍니다.

> [!WARNING]
> 테스트(`test_summarize.py`/`test_api.py`/`test_dashboard.py`)는 전부 모킹이라 실제 Claude API를 호출하지 않습니다. 이 환경에는 `ANTHROPIC_API_KEY`가 없어 실제 API 요청 형식이 라이브 서버에 정확히 맞는지는 검증하지 못했습니다 — 키가 준비되면 `summarize` 명령을 한 번 직접 실행해 확인하는 걸 권장합니다.

---

## Dashboard (Streamlit)

```bash
./.venv/Scripts/python.exe -m streamlit run src/dashboard/app.py
```

4개 페이지(`src/dashboard/pages/`)로 구성되어 있고, FastAPI 서버를 따로 띄우지 않고 `src.storage.repository`/`src.cli.build_event`를 CLI/API와 동일하게 직접 호출합니다(이 PoC는 단일 머신이라 HTTP 홉을 추가하지 않는 쪽을 선택했습니다).

| 페이지 | 내용 |
|---|---|
| ① 이벤트 목록 | 조회/필터 + 새 이벤트 생성 |
| ② 이벤트 상세 | 신호·판정 근거(scores/contributions)·핑퐁 이력, 재할당 기록 폼 |
| ③ 부서 현황 | 부서별 현재 담당 건수, 핑퐁 랭킹(`repository.list_events_with_status`) |
| ④ 규칙 튜닝 | 가중치/임계값을 슬라이더로 바꿔보고 `experiments.compute_batch_results`로 즉시 정확도·혼동행렬 미리보기 — 파일에는 저장되지 않음(주석 있는 `rules.yaml`을 자동 덮어쓰지 않기 위한 설계) |

`dataviz` 스킬의 검증된 팔레트(`references/palette.md`)를 그대로 가져와 쓰며, 부서(YI/MFG/M-ENG/P-ENG) 배지 색은 팔레트의 카테고리 1~4번 슬롯에 고정 순서로 매핑됩니다(`src/dashboard/common.py`의 `DEPT_COLORS`) — 같은 부서는 어느 페이지에서든 같은 색으로 보입니다. 디자인 세부사항은 [Design notes](#design-notes)를 참고하세요.

---

## Docker 배포

```bash
docker compose up --build
```

`api`(포트 8000)와 `dashboard`(포트 8501) 두 서비스가 같은 이미지로 뜨고, 둘 다 `./data`와 `./output`을 컨테이너의 `/app/data`, `/app/output`에 바인드 마운트합니다. LLM 요약을 쓰려면 `ANTHROPIC_API_KEY`를 환경변수로 넘기세요(`ANTHROPIC_API_KEY=sk-... docker compose up`).

> [!IMPORTANT]
> 첫 실행 시 WM-811K 로딩(5~8분)은 컨테이너 안에서도 똑같이 발생합니다. `data/raw/`가 바인드 마운트이므로, 호스트에서 먼저 CLI를 한 번 돌려서 `wm811k_labeled_cache.pkl`을 만들어두면 컨테이너도 그 캐시를 그대로 씁니다.

`fonts-nanum`을 Dockerfile에서 설치합니다 — PDF 리포트의 한글 폰트가 `src/report/pdf.py`의 Linux 폴백 경로(`/usr/share/fonts/truetype/nanum/NanumGothic.ttf`)와 정확히 일치해서, 별도 코드 변경 없이 임베드 폰트로 정상 렌더링됩니다.

---

## Testing

```bash
./.venv/Scripts/python.exe -m pytest -q
```

| 파일 | 검증 대상 |
|---|---|
| `test_validate.py` | 정합성 검증 5종 x 정상/실패 |
| `test_signals.py` | 비전 4개 그룹, 센서 정상/이상, 진동 두 모드 + kurtosis/crest_factor |
| `test_diagnosis.py` | R0~R3 각 1회 이상, `health_index=None`/kurtosis 대체 처리 |
| `test_storage.py` | SQLite CRUD·필터·마이그레이션 |
| `test_api.py` | FastAPI 엔드포인트, 합성 데이터로 격리 |
| `test_handover.py` | 핑퐁 검증 규칙 + DB 이력 체이닝 |
| `test_dashboard.py` | `AppTest`로 Streamlit 페이지 4개 + 홈 실제 실행, PDF/AI 요약 버튼 포함 |
| `test_report.py` | PDF 생성 — 매직 바이트, 빈 이력/`primary_dept=None` 처리 |
| `test_summarize.py` | Claude API 클라이언트를 모킹 — 실제 네트워크 호출 없음 |

`tests/conftest.py`에 실데이터 없이 쓸 수 있는 합성 `SamplingContext` 픽스처가 있습니다.

---

## Results (배치 실험 결과)

| 시나리오 | 정확도 |
|---|---|
| 전체 | 99% |
| `SC-EQ`(설비 기인) | 100% |
| `SC-PR`(공정 기인) | 100% |
| `SC-UN`(원인 불명확) | 96% |
| `SC-NG`(정상) | 100% |

`config/scenarios.yaml`의 `sampling.sensor_method`와 `config/rules.yaml`의 `crest_factor_cap` 주석에 아래 근거(실측 수치, IMS 파일이 정상 구간이라는 문서화된 사실)를 그대로 남겨뒀습니다 — 나중에 숫자만 보고 "왜 이 값인지" 다시 추측하지 않도록.

<details>
<summary>여기까지 오는 과정 (99%는 목표 수치에 끼워 맞춘 게 아니라 단계별로 실데이터를 보고 고친 결과입니다)</summary>

1. **1단계 (WM-811K 실데이터 연동 직후): 50%.** `SC-EQ`/`SC-NG` 0%, `SC-PR`/`SC-UN` 100%. 진동 신호가 `single_file` 모드에서 전혀 기여하지 못했고(`health_index`가 항상 `None`), 센서 이상 점수(`topn_zscore`)가 591차원에서 상위 5개 센서의 |z| 평균을 쓰다 보니 정상 행에서도 값이 크게 나와 `R0`가 거의 발동하지 못했습니다.
2. **2단계 (진동 신호 보강): 73%.** `kurtosis`/`crest_factor` 기반 baseline-free 대체 신호를 추가해 `SC-EQ`가 0%→100%로 올라갔습니다. `SC-NG`는 여전히 0% — 진동과 무관하게 센서 이상 점수 자체가 정상 행에서도 낮게 안 나오는 문제가 그대로 남아 있었습니다.
3. **9단계 (재평가): 74.5% → 99%.** 두 가지를 실제 데이터로 확인하고 고쳤습니다:
   - **센서 이상 점수 방식 전환** (`topn_zscore` → `isolation_forest`): 실제 SECOM 데이터로 두 방식의 PASS/FAIL 점수 분포를 직접 측정했더니, `topn_zscore`는 PASS 평균 0.703 vs FAIL 평균 0.736으로 거의 구분이 안 되고 PASS 행의 0%가 `sensor_low=0.3` 미만이었습니다(`R0`가 구조적으로 발동 불가). `isolation_forest`는 PASS 평균 0.244 vs FAIL 평균 0.280으로 0~1 스케일에 훨씬 잘 맞춰져 있고 PASS 행의 73.5%가 0.3 미만이었습니다. → 74.5%로 개선됐지만 `SC-NG`는 여전히 0%.
   - **`crest_factor_cap` 재보정** (8.0 → 12.0): `SC-NG`가 여전히 0%인 이유를 다시 파고들었더니, 이번엔 센서가 아니라 진동 "calm" 판정이 막고 있었습니다. 유일한 진동 파일(`2004.02.12.10.32.39`, kurtosis=3.63, crest_factor=6.12)은 IMS Set 2 기록의 시작 파일 — 정상 구간으로 문서화되어 있는데, 기존 `crest_factor_cap=8` 기준으로는 이상 점수 0.53(거의 "완전 비정상")으로 계산되어 모든 이벤트에서 `R0`가 막혀 있었습니다. 진동 분석 문헌에서 crest factor 6대는 정상~초기경보 구간으로 보는 게 일반적이라, 이 알려진 정상 구간 파일이 실제로 "calm"으로 분류되도록 상한을 12로 올렸습니다. → `SC-NG` 0%→100%, `SC-UN`은 96%로 2/50만 소폭 하락(P-ENG로 오분류) — 진동이 실제로 점수에 반영되면서 생긴 정직한 트레이드오프로 보고 그대로 남겨뒀습니다.

**진동 신호 보강 상세**: `single_file` 모드에서는 여러 파일에 걸친 기준선(baseline)을 계산할 수 없어 `health_index`가 항상 `None`이지만, 파일 하나(20480개 샘플)만으로도 계산할 수 있는 baseline-free 통계가 있습니다 — 정상적인(건강한) 베어링 진동은 대략 가우시안 분포에 가까워 kurtosis ≈ 3, crest factor(피크/RMS) ≈ 3~4 부근이고, 마모·충격성 결함이 생기면 신호가 임펄시브해지면서 두 값 모두 올라가는 것이 진동 분석 분야에서 널리 쓰이는 결함 지표입니다(`src/ingest/loaders.py`의 `_channel_stats`, `src/diagnosis/engine.py`의 `_kurtosis_crest_abnormality`). `health_index`가 있으면 그걸 우선 쓰고, 없을 때만 이 대체 신호를 쓰며, 둘 다 없을 때만 기여도를 0으로 둡니다 — 이 판단 경로는 항상 `diagnosis.notes`에 남습니다.

</details>

---

## Scope

이 PoC 단계에서는 "로컬에서 `docker compose up` 한 번으로 전체 스택이 뜬다"까지만 다룹니다. 아래는 다음 단계 후보로 남겨둔, 이번 범위에 포함하지 않은 것입니다.

- 인증/접근 권한 (현재는 누구나 API/대시보드에 접근 가능)
- TLS/리버스 프록시
- 실제 팹 데이터 파이프라인 연동 (현재는 정적 공개 데이터셋)
- CI/CD

---

## Troubleshooting

| 증상 | 원인 | 해결 |
|---|---|---|
| `streamlit run src/dashboard/pages/*.py`를 직접 실행하면 `ModuleNotFoundError: No module named 'src'` | `-m streamlit`이 아닌 방식으로 실행하면 프로젝트 루트가 `sys.path`에 없음 | 항상 프로젝트 루트에서 `-m streamlit run src/dashboard/app.py`로 실행. 각 페이지 파일 최상단에 `sys.path.insert(...)` 보정이 이미 적용되어 있음 |
| API 테스트가 몇 분씩 걸림 | `with TestClient(app) as c:`로 쓰면 실제 `lifespan`이 실행되어 `dependency_overrides`와 무관하게 진짜 대용량 데이터를 로드함 | `TestClient(app)`을 컨텍스트 매니저 없이 인스턴스로만 사용 (이미 적용됨) |
| PDF 리포트의 한글이 빈칸으로 나오고 표 열이 겹침 | ReportLab 기본 CID 폰트(`HYSMyeongJo-Medium` 등)는 이름만 참조하고 실제 폰트 파일을 담지 않음 | OS별 경로에서 실제 폰트 파일(Malgun Gothic/NanumGothic)을 찾아 임베드하도록 이미 수정됨(`_register_fonts()`); 폰트가 없으면 CID로 폴백 |
| `LSWMD.pkl` 로딩이 매우 느리거나 실패 | 오래된 pandas/Python 2 pickle이라 모듈 경로·인코딩이 최신 pandas와 다름 | 최초 1회 5~8분은 정상(호환 패치가 처리). 이후엔 자동 생성된 `wm811k_labeled_cache.pkl`을 읽어 수 초 안에 끝남. 캐시를 지우면 다시 5~8분 걸림 |

---

## Design notes

이 프로젝트를 만들면서 실제로 겪고 판단한 세부사항입니다. 사용에는 필요하지 않지만, 코드를 고치거나 확장할 때 "왜 이렇게 했는지" 다시 추측하지 않도록 남겨둡니다.

<details>
<summary>대시보드 sys.path 버그를 두 번 겪은 경위</summary>

- **발견한 버그 1**: `streamlit run src/dashboard/app.py`를 프로젝트 루트에서 실행하면 문제없이 동작하지만(`-m streamlit`이 cwd를 `sys.path[0]`에 넣어줌), 각 페이지 파일을 다른 방식으로 직접 실행하면(예: 테스트 스크립트, 다른 cwd) 실패할 수 있다는 걸 실데이터 스모크 테스트로 찾았습니다. 처음엔 이 sys.path 보정 코드를 `common.py`에 넣었는데, 이건 아무 효과가 없습니다 — 페이지가 `from src.dashboard.common import ...`를 실행하는 순간 이미 `src`를 못 찾아 실패하고, `common.py` 안의 코드는 그 시점엔 아직 실행조차 안 됐기 때문입니다(닭과 달걀 문제). 그래서 각 페이지 파일 맨 위, 첫 `from src...` import보다 먼저 `sys.path.insert(...)`를 반복해서 넣는 방식으로 고쳤습니다.
- **발견한 버그 2**: 대시보드 디자인을 다시 손보면서 `app.py`에도 처음으로 `from src.dashboard.common import ...`를 추가했는데, 버그 1의 수정 코드를 그대로 복사하면서 `parents[3]`도 같이 복사했습니다. 문제는 `app.py`는 `src/dashboard/app.py`로 프로젝트 루트에서 2단계 아래인데(`pages/*.py`는 3단계), `parents[3]`은 프로젝트 루트를 지나 그 부모 폴더(`src`가 없는 곳)를 가리켜서 조용히 틀린 경로를 넣고 있었습니다. `streamlit run`으로 프로젝트 루트에서 실행하면 `-m streamlit`이 cwd를 이미 `sys.path[0]`에 넣어줘서 버그가 가려졌지만, 실데이터 스모크 테스트(`AppTest`를 pytest 밖에서 직접 실행)에서 다시 걸렸습니다. `parents[2]`로 고쳤고, `tests/test_dashboard.py`에 이 정확한 depth 계산을 검증하는 회귀 테스트(`test_every_dashboard_script_has_a_correct_sys_path_bootstrap`)를 추가했습니다 — 5개 스크립트 각각의 `parents[N]`이 실제로 프로젝트 루트로 resolve되는지 파일시스템으로 직접 확인합니다.
- **테스트에서 실데이터 없이 페이지를 검증하는 방법**: `tests/test_dashboard.py`는 `streamlit.testing.v1.AppTest`로 각 페이지 스크립트를 실제로 실행시켜 예외를 잡습니다(HTTP로 껍데기만 확인하는 것과 다름). `src.dashboard.common`의 캐시된 로더를 패치해서 합성 데이터로 돌리므로 실데이터 없이도 빠르게(몇 초 안에) 돌아갑니다. 위의 sys.path 버그는 이 pytest 테스트로는 못 잡았습니다 — pytest 자체가 이미 프로젝트 루트를 `sys.path`에 넣어두기 때문입니다. 실제로 이 버그를 잡은 건 `AppTest.from_file()`을 pytest 밖에서 독립 스크립트로 직접 돌려본 실데이터 스모크 테스트였습니다.

</details>

<details>
<summary>한글 폰트: CID 폰트로 시작했다가 실제로 렌더링해보고 바꾼 경위</summary>

처음엔 ReportLab이 기본 제공하는 CJK CID 폰트(`HYSMyeongJo-Medium`/`HYGothic-Medium`, 이름만 참조하고 폰트 파일은 안 담음)를 썼습니다. 코드는 문제없이 실행되고 텍스트 추출도 정상이길래 넘어갈 뻔했는데, 실제로 PDF를 렌더링해서 눈으로 봤더니 — 이 뷰어에 한글 폰트가 없어서 한글 글자가 전부 빈칸으로 나오고, 그 여파로 표 열도 서로 겹쳐서 깨졌습니다. Windows에 이미 설치되어 있는 Malgun Gothic(`C:\Windows\Fonts\malgun.ttf`)을 실제로 임베드하는 방식으로 바꿔서 해결했습니다(`src/report/pdf.py`의 `_register_fonts()`가 Windows/Linux/macOS 순서로 흔한 설치 경로를 찾고, 못 찾으면 CID 폰트로 폴백). 코드가 정상 실행된다고 결과물까지 정상이라고 가정하면 안 된다는 걸 다시 확인한 사례라 남겨둡니다 — 대시보드 sys.path 버그를 잡을 때와 같은 교훈입니다.

</details>

<details>
<summary>테스트에서 실데이터를 건드리지 않는 이유 (의존성 주입)</summary>

`src/api/main.py`는 `get_ctx`/`get_rules`/`get_db_path`를 FastAPI `Depends`로 주입받고, `tests/test_api.py`는 `app.dependency_overrides`로 가벼운 합성 데이터(`tests/conftest.py`의 `build_fake_ctx()`)를 주입합니다. 이거 없이 앱을 만들면 테스트에서도 매번 실제 2GB `LSWMD.pkl`을 로드해야 합니다. 이 설계 덕분에 API 테스트가(실수로 `with TestClient`를 써서 진짜 lifespan을 트리거하기 전까지는) 수초 안에 끝납니다.

</details>

<details>
<summary>그 외 구현 중 판단한 세부사항</summary>

- CLI 라이브러리: `click`
- 로깅: 별도 로거 없이 `diagnosis.notes` / 이벤트의 `_notes` 필드에 사유를 남기는 방식(스킵된 조건, `health_index=None` 사유 등)을 채택. 다음 단계에서 API/DB로 확장할 때 이 필드들을 그대로 로그·감사 추적에 활용할 수 있습니다.
- 센서 이상 점수 기본값: `topn_zscore`(상위 5개 |z| 평균을 `1-exp(-x/3)`로 0~1 압축). `isolation_forest`도 `src/signals/sensor.py`에 구현되어 있어 `fit_sensor_model(..., method="isolation_forest")`로 바로 전환 가능.
- 진동 파일 저장 위치: `data/raw/`에는 SECOM csv만 두고, NASA 파일은 `data/raw/vibration/` 하위 폴더로 분리(SECOM csv가 진동 로더에 잘못 걸리지 않도록).
- WM-811K 로딩: `LSWMD.pkl`을 "최신 pandas 포맷으로 재저장"하는 방식은 시도했다가 디스크 공간 부족(당시 여유 1.6GB)으로 중단했습니다. 대신 로더가 매번 호환 패치로 직접 읽고, 라벨 있는 172,950행만 추려 작은 캐시(약 250MB)를 만들어 재사용하는 방식으로 변경했습니다 — 원본 2GB를 중복 보관하지 않으면서도 이후 실행은 몇 초 안에 끝납니다.
- WM-811K 목업(`wafer_mock.py`)은 삭제하지 않고 유지했습니다 — 거대한 `LSWMD.pkl` 없이도 `tests/test_signals.py`가 빠르게 돌 수 있어야 해서, 실 데이터 경로(`wm811k.py`)와는 별도로 테스트/오프라인 개발용 픽스처로 남겨뒀습니다.
- SQLite 스키마: 완전 정규화된 여러 테이블 대신 `events` 테이블 하나에 조회용 컬럼 + `raw_json` 블롭으로 설계했습니다. 이벤트 스키마가 아직 확정 단계가 아니라(다음 단계에서 API가 필드를 더 요구할 수 있음), 정규화를 미리 하면 스키마 변경마다 마이그레이션이 필요해집니다. `raw_json`이 원본을 그대로 보존하니 컬럼은 "지금 필요한 필터"만 추가하면 됩니다. ORM 없이 표준 라이브러리 `sqlite3`만 사용(의존성 추가 없음).
- `weights.equipment.vibration_hi` → `vibration_abnormal`로 이름을 바꿨습니다 — "hi"가 `health_index`를 뜻했는데, 이제는 kurtosis/crest_factor 대체 신호로 채워지는 경우가 대부분이라 예전 이름이 오해를 줄 수 있었습니다.
- 구현 중 버그를 하나 발견해서 고쳤습니다: `signals/vibration.py`는 kurtosis/crest_factor를 계산해서 반환했지만, `cli.py`가 그 값을 `models.VibrationSignal`과 `diagnose()` 호출에 전달하지 않아서 보강 로직이 실제로는 항상 비활성 상태였습니다. `models.py`에 필드를 추가하고 `cli.py`의 두 호출을 고친 뒤 배치를 재실행해서 50%→73%로 개선된 것을 확인했습니다.
- Pydantic 모델은 요청 바디(`GenerateRequest`, `ValidateRequest`)에만 쓰고 응답은 그냥 `dict`로 반환합니다 — 이벤트 스키마가 `models.py`의 dataclass로 이미 정의돼 있어 Pydantic으로 다시 정의하면 두 곳을 계속 동기화해야 했을 것입니다.
- 핑퐁 이력은 이벤트의 `raw_json`에 필드를 추가하는 대신 별도 `handovers` 테이블(append-only)로 분리했습니다. 이벤트 JSON은 "생성 시점의 스냅샷"이라는 불변성을 유지하고 싶었고, 이력은 거꾸로 계속 늘어나는 데이터라 성격이 다릅니다. 같은 테이블에 넣으면 매 재할당마다 `raw_json` 전체를 다시 파싱·직렬화해야 했을 것입니다.
- MFG를 `depts`(rules.yaml, 판정 엔진)에는 넣지 않고 `VALID_DEPTS`(handover/tracker.py)에만 넣었습니다 — 판정 엔진은 원인을 equipment/process 두 가설로만 나누기 때문에 MFG가 주관 부서로 나올 일이 없지만, 실제 핑퐁 흐름에서는 R1의 MFG Hold 이후 MFG도 개입할 수 있어서 핑퐁 대상 부서로는 유효해야 합니다.
- 대시보드는 FastAPI를 거치지 않고 `repository`/`build_event`를 직접 호출합니다 — 이 PoC는 한 대의 머신에서 CLI/API/대시보드가 모두 돌아가는 전제라, HTTP 홉을 추가하는 것보다 같은 순수 함수를 재사용하는 쪽이 더 단순합니다. 여러 머신으로 나뉘면 `src/dashboard/common.py`의 두 함수만 `requests` 호출로 바꾸면 됩니다.
- 차트는 `st.bar_chart`만 사용하고 plotly/matplotlib은 추가하지 않았습니다 — 이 정도 집계(부서별 건수)에는 Streamlit 내장 차트로 충분해서 의존성을 늘릴 이유가 없었습니다.
- 규칙 튜닝 페이지는 슬라이더 값을 `config/rules.yaml`에 저장하는 기능을 일부러 넣지 않았습니다 — 그 파일은 각 값의 의미를 설명하는 주석이 많은데, `yaml.dump`로 덮어쓰면 주석이 전부 사라집니다. 미리보기만 제공하고 값 복사는 사람이 하도록 남겨뒀습니다.
- PDF 라이브러리로 WeasyPrint(HTML→PDF) 대신 ReportLab을 골랐습니다 — WeasyPrint는 Windows에서 Pango/Cairo 같은 시스템 라이브러리가 추가로 필요해 설치가 까다로운 경우가 많은데, ReportLab은 순수 Python 휠만으로 설치됩니다.
- `use_container_width`를 대시보드 전 페이지에서 `width="stretch"`로 바꿨습니다 — Streamlit이 "2025-12-31 이후 제거 예정" 경고를 띄우는데, 이 프로젝트 기준 "오늘"(2026-09-28)이 이미 그 날짜를 지나 있어서 다음 업그레이드에서 바로 깨질 수 있었습니다.
- 센서 스코어링 방식(`sensor_method`)을 `src/scenarios/catalog.py`에 하드코딩하지 않고 `config/scenarios.yaml`의 `sampling.sensor_method`로 뺐습니다 — 이번에 실제로 값을 바꿔가며(`topn_zscore` ↔ `isolation_forest`) 재평가했던 것처럼, 다음에 또 다른 방식을 시도할 때 코드를 건드릴 필요가 없게 하기 위해서입니다.

</details>
