# handover-poc

반도체 불량 대응 인수인계 자동화 — 핵심 로직 PoC (1단계).

세 개의 공개 데이터셋(UCI SECOM, NASA IMS 베어링 진동, WM-811K)에서 뽑은 신호를 하나의
가상 불량 이벤트로 묶고, 규칙 기반 엔진으로 원인을 판정해 주관 부서(M-ENG/P-ENG/YI)를
제안하는 시스템의 프로토타입입니다. API·DB·대시보드·PDF·LLM 요약은 다음 단계이며, 이번
단계는 순수 함수 위주의 핵심 로직 + CLI + 테스트 + 배치 실험까지만 다룹니다.

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
# 이벤트 1건 생성 (output/events/EVT-<timestamp>-<random4>.json)
./.venv/Scripts/python.exe -m src.cli generate --scenario SC-EQ --seed 42 --out output/events/

# 정합성 검증만 단독 실행
./.venv/Scripts/python.exe -m src.cli validate --event-file output/events/EVT-xxxx.json

# 배치 실험: 4개 시나리오 x seed 0~49 = 200개 이벤트 + 혼동행렬
./.venv/Scripts/python.exe -m src.cli batch --seeds 50 --out output/experiments/
```

시나리오 ID: `SC-EQ`(설비 기인), `SC-PR`(공정 기인), `SC-UN`(원인 불명확), `SC-NG`(정상).
가중치·임계값은 `config/rules.yaml`, 시나리오 정의는 `config/scenarios.yaml`에 있습니다.

### 재현성

같은 `--scenario`/`--seed`로 두 번 실행하면 신호(`signals`)와 판정(`diagnosis`)은
완전히 동일합니다. `event_id`/`event_time`은 생성 시각을 담는 메타데이터라 매번
새로 발급되며(실제 이벤트 관리 시스템의 "생성 시각"과 같은 성격), 재현성 검사에서는
이 두 필드를 제외하고 비교합니다.

## 테스트

```bash
./.venv/Scripts/python.exe -m pytest -q
```

`tests/test_validate.py`(정합성 검증 5종 x 정상/실패), `tests/test_signals.py`(비전 4개
그룹, 센서 정상/이상, 진동 두 모드), `tests/test_diagnosis.py`(R0~R3 각 1회 이상,
`health_index=None` 처리)로 구성되어 있습니다.

## 배치 실험 결과에 대한 솔직한 안내

WM-811K를 실 데이터로 교체한 뒤에도 전체 정확도는 여전히 50%로 동일합니다 (`SC-PR`/`SC-UN`
100%, `SC-EQ`/`SC-NG` 0%) — 예상된 결과입니다. 원인이 비전 데이터 품질이 아니라
`single_file` 모드에서는 진동 신호가 판정에 전혀 기여하지 못하는 것(가중치 0.4가 항상
빠짐)과, 591차원에서 상위 5개 센서의 |z| 평균이 정상 행에서도 꽤 크게 나오는 경향(차원이
많을수록 극단값이 흔해지는 현상) 때문에 `R0`의 `sensor_low=0.3` 기준을 잘 넘기지 못하는
것에 있기 때문입니다. `SC-EQ`(설비 기인)는 `score_min=0.6` 기준을 넘기기 어려워 대부분
`R3`(YI로 넘김)로 떨어집니다. 이 결과는 숫자를 좋게 보이도록 조정하지 않고 그대로
`output/experiments/confusion_matrix.csv`에 남겨두었습니다. 개선하려면
`config/rules.yaml`의 `thresholds`(특히 `sensor_low`, `score_min`)나
`src/signals/sensor.py`의 `method`(예: `isolation_forest`로 전환)를 조정하는 것이
근본적인 해결책입니다 (진동은 단일 파일 모드가 영구 설계이므로 더 이상 옵션이 아닙니다).

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
