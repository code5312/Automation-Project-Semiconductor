# handover-poc

반도체 불량 대응 인수인계 자동화 — 핵심 로직 PoC (1단계).

세 개의 공개 데이터셋(UCI SECOM, NASA IMS 베어링 진동, WM-811K)에서 뽑은 신호를 하나의
가상 불량 이벤트로 묶고, 규칙 기반 엔진으로 원인을 판정해 주관 부서(M-ENG/P-ENG/YI)를
제안하는 시스템의 프로토타입입니다. 핵심 로직(ingest/signals/scenarios/diagnosis)은
순수 함수 위주로 짜여 있고, CLI·SQLite·FastAPI·부서 간 인수인계("핑퐁") 추적이 모두 그
위에 얇게 얹혀 있습니다. 대시보드·PDF·LLM 요약은 다음 단계입니다.

## 데이터 상태 (중요)

- **SECOM**: `data/raw/uci-secom.csv` (1,567행, 591개 센서 컬럼). `Pass/Fail`은
  **-1=정상, 1=불량**으로 인코딩되어 있습니다 (`src/ingest/loaders.py`의 `SECOM_LABEL_PASS`/
  `SECOM_LABEL_FAIL` 상수 참고). 센서 591개가 무엇을 측정하는지는 공개 자료에 없어, 모든
  센서는 `sensor_id`만 부여하고 `unit`/`meaning`은 항상 `"unknown"`으로 표기합니다.
- **NASA IMS 진동**: 이 환경에는 Set 2 파일이 **1개(`2004.02.12.10.32.39`)만** 있습니다.
  이건 임시가 아니라 **의도적으로 고정된 설계**입니다 — Set 2 전체(984개 파일)는 받지
  않기로 하고, 이 파일 하나(20480개 샘플)를 유의미한 실측 데이터로 인용합니다. 진동
  신호는 항상 **`single_file` 모드**로 처리됩니다: RMS만 계산하고 **`health_index`는
  항상 `None`**입니다 (기준선을 계산할 다른 파일이 없기 때문). `health_index`가 필요한
  판정 항목(`vibration_hi`, `vibration_normal`)은 이 모드에서 기여도 0으로 빠지고, 그 사유가
  이벤트 JSON의 `diagnosis.notes`에 남습니다. (참고: `src/ingest/loaders.py`의
  `load_vibration_rms`는 폴더 안 파일 개수로 모드를 자동 판별하도록 구현되어 있어, 파일이
  여러 개로 바뀌면 코드 변경 없이 `full_baseline` 모드로 전환은 되지만 현재는 쓰지 않습니다.)
- **WM-811K**: `data/raw/wm811k/LSWMD.pkl` (811,457행 중 라벨 있는 172,950행만 사용,
  8개 불량 패턴 + none). `src/ingest/wm811k.py`가 실 데이터에서 `pattern_group` 조건에
  맞는 라벨링된 웨이퍼를 시드 기반으로 결정적으로 샘플링합니다 (`src/ingest/wafer_mock.py`의
  목업 생성기는 이제 테스트/오프라인 개발용 픽스처로만 남아 있습니다).
  **LSWMD.pkl 로딩 관련 주의**: 이 파일은 매우 오래된 pandas/Python 2로 저장되어
  (a) `pandas.indexes.*` 모듈 경로가 최신 pandas(3.x)에는 없고, (b) numpy 배열 원본
  바이트가 Python 2 문자열(STRING opcode)로 저장돼 있어 기본 ASCII 디코딩이 실패합니다.
  `src/ingest/wm811k.py`가 이 두 문제를 호환 패치(`pandas.compat.pickle_compat`의
  클래스 위치 맵 확장 + `encoding="latin1"`)로 직접 처리합니다. 순수 파이썬 Unpickler를
  타기 때문에 **최초 1회 로딩에 5~8분 정도** 걸리며, 이후에는 라벨 있는 172,950행만
  추려낸 캐시(`data/raw/wm811k/wm811k_labeled_cache.pkl`, 약 250MB)를 만들어 두고
  다음부터는 그 캐시를 즉시 읽습니다(수 초). 캐시는 `.gitignore`에 포함되어 있으니,
  삭제하면 다음 실행 때 원본에서 다시 5~8분간 재생성됩니다.
- 세 데이터는 서로 다른 장비·연도·기관의 것을 인위적으로 묶은 것이라, 모든 이벤트에
  `"is_simulated": true`와 각 신호의 `source_ref`(원본 행/파일 위치)가 남습니다. 인과관계가
  아니라 시나리오 입력으로만 취급하세요.

## 환경 설정

Python 3.11 가상환경을 사용합니다 (3.14도 설치돼 있었지만, scikit-learn 등 과학 패키지의
휠 호환성이 더 안정적인 3.11로 새로 만들었습니다).

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## 데이터 배치

```
data/raw/
├── uci-secom.csv
├── vibration/
│   └── 2004.02.12.10.32.39           # 파일이 1개면 single_file 모드, 여러 개면 full_baseline 모드
└── wm811k/
    ├── LSWMD.pkl                      # 최초 실행 시에만 필요 (이후엔 캐시로 대체)
    └── wm811k_labeled_cache.pkl       # 자동 생성됨, git-ignored
```

## CLI 사용법

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

시나리오 ID: `SC-EQ`(설비 기인), `SC-PR`(공정 기인), `SC-UN`(원인 불명확), `SC-NG`(정상).
가중치·임계값은 `config/rules.yaml`, 시나리오 정의는 `config/scenarios.yaml`에 있습니다.

### 영속화 (SQLite)

`generate`/`batch`는 기본적으로 이벤트를 `output/handover.db`(SQLite, git-ignored)에도
저장합니다. `--no-db`로 끌 수 있고, `--db <path>`로 다른 경로를 쓸 수 있습니다. 스키마는
`src/storage/repository.py`의 `events` 테이블 하나 — 조회용 컬럼(scenario_id,
primary_dept, rule_id 등)과 원본을 그대로 보존하는 `raw_json` 컬럼을 함께 둡니다: 필터는
컬럼으로, 상세 조회는 `raw_json`으로 하면 되고 이벤트 JSON 스키마가 바뀌어도 컬럼만
맞춰주면 됩니다. `event_id`가 기본키라 같은 이벤트를 다시 저장하면 덮어씁니다(upsert).
## API 사용법 (FastAPI)

```bash
./.venv/Scripts/python.exe -m uvicorn src.api.main:app --reload
```

앱 시작 시 `SamplingContext`(SECOM/진동/WM-811K + 학습된 센서 모델)를 한 번만 로드해
재사용합니다 (요청마다 다시 로드하지 않음). 엔드포인트:

| 메서드/경로 | 설명 |
| --- | --- |
| `GET /health` | 헬스체크 |
| `GET /scenarios` | `config/scenarios.yaml`의 시나리오 정의 |
| `POST /events/generate` | `{"scenario_id": "SC-EQ", "seed": 42}` → 이벤트 생성 + DB 저장 |
| `GET /events/{event_id}` | 단일 이벤트 조회 (없으면 404) |
| `GET /events?scenario_id=&primary_dept=&limit=&offset=` | 필터 조회 |
| `POST /validate` | `{"event": {...}}` → 정합성 검증 (실패 시 422) |

CLI의 `build_event`/`load_rules`와 `storage/repository.py`를 그대로 재사용하고, 이
모듈에는 진단/신호/시나리오 로직이 전혀 없습니다 — 순수 함수를 HTTP로 감싸기만 했습니다.

### 테스트에서 실데이터를 건드리지 않는 이유

`src/api/main.py`는 `get_ctx`/`get_rules`/`get_db_path`를 FastAPI `Depends`로 주입받고,
`tests/test_api.py`는 `app.dependency_overrides`로 가벼운 합성 데이터(`tests/conftest.py`의
`build_fake_ctx()`)를 주입합니다. **주의**: `TestClient(app)`을 `with` 컨텍스트 매니저로
쓰면(`with TestClient(app) as c:`) 앱의 실제 `lifespan`이 실행되어 `dependency_overrides`와
무관하게 진짜 `LSWMD.pkl`/SECOM/진동 파일을 로드해버립니다 — 처음 이 실수로 테스트가
몇 분씩 걸렸습니다. 그래서 `TestClient(app)`을 컨텍스트 매니저 없이 그냥 인스턴스로만
사용합니다.

### 재현성

같은 `--scenario`/`--seed`로 두 번 실행하면 신호(`signals`)와 판정(`diagnosis`)은
완전히 동일합니다. `event_id`/`event_time`은 생성 시각을 담는 메타데이터라 매번
새로 발급되며(실제 이벤트 관리 시스템의 "생성 시각"과 같은 성격), 재현성 검사에서는
이 두 필드를 제외하고 비교합니다.

## 핑퐁(부서 재할당) 이력 추적

이벤트가 처음 생성될 때의 `diagnosis.primary_dept`는 규칙 엔진의 판정일 뿐, 실제로는
부서 간에 여러 번 재할당("핑퐁")될 수 있습니다. 이건 이벤트 JSON 자체(불변)와는 성격이
달라서 — 생성 후에 계속 쌓이는 이력이라 — 별도의 `handovers` 테이블(이벤트당 여러 행,
append-only)로 추적합니다. 유효한 부서는 `YI`/`MFG`/`M-ENG`/`P-ENG` 4개
(`src/handover/tracker.py`의 `VALID_DEPTS`)이고, 순수 함수 `validate_handover`가 (1) 알 수
없는 부서, (2) 이유 없는 재할당, (3) 같은 부서로의 무의미한 재할당을 거부합니다.

```bash
# 재할당 기록 (직전 담당 부서는 자동으로 추적된 현재 상태에서 가져옴)
./.venv/Scripts/python.exe -m src.cli handover --event-id EVT-xxxx --to P-ENG --reason "설비 이상 없음 확인"

# 이력 + 핑퐁 횟수 조회
./.venv/Scripts/python.exe -m src.cli history --event-id EVT-xxxx
```

API: `POST /events/{event_id}/handovers` (`{"to_dept": "...", "reason": "..."}`),
`GET /events/{event_id}/handovers` → `{"current_dept", "pingpong_count", "history"}`.
첫 재할당의 `from_dept`는 이벤트의 원래 `primary_dept`에서 자동으로 채워지고, 그 다음부터는
직전 `to_dept`에서 이어집니다.

## 테스트

```bash
./.venv/Scripts/python.exe -m pytest -q
```

`tests/test_validate.py`(정합성 검증 5종 x 정상/실패), `tests/test_signals.py`(비전 4개
그룹, 센서 정상/이상, 진동 두 모드 + kurtosis/crest_factor), `tests/test_diagnosis.py`
(R0~R3 각 1회 이상, `health_index=None`/kurtosis 대체 처리), `tests/test_storage.py`
(SQLite CRUD·필터·마이그레이션), `tests/test_api.py`(FastAPI 엔드포인트, 합성 데이터로
격리), `tests/test_handover.py`(핑퐁 검증 규칙 + DB 이력 체이닝)로 구성되어 있습니다.
`tests/conftest.py`에 실데이터 없이 쓸 수 있는 합성 `SamplingContext` 픽스처가 있습니다.

## 배치 실험 결과에 대한 솔직한 안내

**진동 신호 보강(kurtosis/crest factor 기반 baseline-free 이상 점수, 아래 참고) 이후
전체 정확도가 50% → 73%로 개선됐습니다**: `SC-EQ`(설비 기인) 100%, `SC-PR`(공정 기인)
100%, `SC-UN`(원인 불명확) 92%, `SC-NG`(정상) 0%. `SC-EQ`는 이전에는 진동 신호가
전혀 기여하지 못해(`health_index`가 항상 `None`) `score_min=0.6`을 못 넘기고 매번
`R3`(YI로 넘김)로 떨어졌는데, kurtosis/crest_factor 기반 대체 신호가 그 자리를 메우면서
100%로 올라갔습니다. `SC-UN`은 92%로 소폭 내려갔습니다 — 이제 진동이 실제로 점수에
영향을 주다 보니, "원인 불명확" 시나리오 중 일부(4/50)가 P-ENG로 판정되는 경우가
생겼습니다. 이는 신호가 더 정직해진 결과로 보고 그대로 남겨뒀습니다.

`SC-NG`(정상)는 여전히 0%입니다 — 이건 진동과 무관하게, 591차원에서 상위 5개 센서의
|z| 평균이 정상 행에서도 꽤 크게 나오는 경향(차원이 많을수록 극단값이 흔해지는 현상)
때문에 `R0`의 `sensor_low=0.3` 기준을 넘기지 못하는 것이 원인입니다. 이 결과는 숫자를
좋게 보이도록 조정하지 않고 그대로 `output/experiments/confusion_matrix.csv`에
남겨두었습니다. 개선하려면 `config/rules.yaml`의 `thresholds`(특히 `sensor_low`)나
`src/signals/sensor.py`의 `method`(예: `isolation_forest`로 전환)를 조정하는 것이
다음 개선 후보입니다.

### 진동 신호 보강 상세

`single_file` 모드에서는 여러 파일에 걸친 기준선(baseline)을 계산할 수 없어
`health_index`가 항상 `None`이지만, 파일 하나(20480개 샘플)만으로도 계산할 수 있는
**baseline-free 통계**가 있습니다 — 정상적인(건강한) 베어링 진동은 대략 가우시안 분포에
가까워 **kurtosis ≈ 3, crest factor(피크/RMS) ≈ 3~4** 부근이고, 마모·충격성 결함이
생기면 신호가 임펄시브해지면서 두 값 모두 올라가는 것이 진동 분석 분야에서 널리 쓰이는
결함 지표입니다 (`src/ingest/loaders.py`의 `_channel_stats`, `src/diagnosis/engine.py`의
`_kurtosis_crest_abnormality`). `health_index`가 있으면 그걸 우선 쓰고, 없을 때만 이
대체 신호를 쓰며, 둘 다 없을 때만 기여도를 0으로 둡니다 — 이 판단 경로는 항상
`diagnosis.notes`에 남습니다.

## 진행하면서 판단한 세부사항

- CLI 라이브러리: `click`
- 로깅: 별도 로거 없이 `diagnosis.notes` / 이벤트의 `_notes` 필드에 사유를 남기는 방식
  (스킵된 조건, `health_index=None` 사유 등)을 채택. 다음 단계에서 API/DB로 확장할 때
  이 필드들을 그대로 로그·감사 추적에 활용할 수 있습니다.
- 센서 이상 점수 기본값: `topn_zscore`(상위 5개 |z| 평균을 `1-exp(-x/3)`로 0~1 압축).
  `isolation_forest`도 `src/signals/sensor.py`에 구현되어 있어 `fit_sensor_model(...,
  method="isolation_forest")`로 바로 전환 가능.
- 진동 파일 저장 위치: `data/raw/`에는 SECOM csv만 두고, NASA 파일은
  `data/raw/vibration/` 하위 폴더로 분리 (SECOM csv가 진동 로더에 잘못 걸리지 않도록).
- WM-811K 로딩: `LSWMD.pkl`을 "최신 pandas 포맷으로 재저장"하는 방식은 시도했다가
  디스크 공간 부족(당시 여유 1.6GB)으로 중단했습니다. 대신 로더가 매번 호환 패치로 직접
  읽고, 라벨 있는 172,950행만 추려 작은 캐시(약 250MB)를 만들어 재사용하는 방식으로
  변경했습니다 — 원본 2GB를 중복 보관하지 않으면서도 이후 실행은 몇 초 안에 끝납니다.
- WM-811K 목업(`wafer_mock.py`)은 삭제하지 않고 유지했습니다 — 거대한 `LSWMD.pkl` 없이도
  `tests/test_signals.py`가 빠르게 돌 수 있어야 해서, 실 데이터 경로(`wm811k.py`)와는
  별도로 테스트/오프라인 개발용 픽스처로 남겨뒀습니다.
- SQLite 스키마: 완전 정규화된 여러 테이블 대신 `events` 테이블 하나에 조회용 컬럼 +
  `raw_json` 블롭으로 설계했습니다. 이벤트 스키마가 아직 확정 단계가 아니라(다음 단계에서
  API가 필드를 더 요구할 수 있음), 정규화를 미리 하면 스키마 변경마다 마이그레이션이
  필요해집니다. `raw_json`이 원본을 그대로 보존하니 컬럼은 "지금 필요한 필터"만 추가하면
  됩니다. ORM 없이 표준 라이브러리 `sqlite3`만 사용 (의존성 추가 없음).
- `weights.equipment.vibration_hi` → `vibration_abnormal`로 이름을 바꿨습니다 — "hi"가
  `health_index`를 뜻했는데, 이제는 kurtosis/crest_factor 대체 신호로 채워지는 경우가
  대부분이라 예전 이름이 오해를 줄 수 있었습니다.
- 구현 중 버그를 하나 발견해서 고쳤습니다: `signals/vibration.py`는 kurtosis/crest_factor를
  계산해서 반환했지만, `cli.py`가 그 값을 `models.VibrationSignal`과 `diagnose()` 호출에
  전달하지 않아서 보강 로직이 실제로는 항상 비활성 상태였습니다. `models.py`에 필드를
  추가하고 `cli.py`의 두 호출을 고친 뒤 배치를 재실행해서 50%→73%로 개선된 것을
  확인했습니다.
- FastAPI 의존성 주입: `get_ctx`/`get_rules`/`get_db_path`를 `Depends`로 분리한 이유가
  테스트 목적입니다 — 이거 없이 앱을 만들면 테스트에서도 매번 실제 2GB `LSWMD.pkl`을
  로드해야 합니다. `app.dependency_overrides`로 가벼운 합성 데이터를 주입할 수 있게
  했고, 실제로 이 설계 덕분에 API 테스트가 (실수로 `with TestClient`를 써서 진짜
  lifespan을 트리거하기 전까지는) 수초 안에 끝납니다.
- Pydantic 모델은 요청 바디(`GenerateRequest`, `ValidateRequest`)에만 쓰고 응답은 그냥
  `dict`로 반환합니다 — 이벤트 스키마가 `models.py`의 dataclass로 이미 정의돼 있어
  Pydantic으로 다시 정의하면 두 곳을 계속 동기화해야 했을 것입니다.
- 핑퐁 이력은 이벤트의 `raw_json`에 필드를 추가하는 대신 별도 `handovers` 테이블(append-only)로
  분리했습니다. 이벤트 JSON은 "생성 시점의 스냅샷"이라는 불변성을 유지하고 싶었고, 이력은
  거꾸로 계속 늘어나는 데이터라 성격이 다릅니다. 같은 테이블에 넣으면 매 재할당마다
  `raw_json` 전체를 다시 파싱·직렬화해야 했을 것입니다.
- MFG를 `depts`(rules.yaml, 판정 엔진)에는 넣지 않고 `VALID_DEPTS`(handover/tracker.py)에만
  넣었습니다 — 판정 엔진은 원인을 equipment/process 두 가설로만 나누기 때문에 MFG가 주관
  부서로 나올 일이 없지만, 실제 핑퐁 흐름에서는 R1의 MFG Hold 이후 MFG도 개입할 수 있어서
  핑퐁 대상 부서로는 유효해야 합니다.
