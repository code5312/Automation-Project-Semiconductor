<div align="center">

<img alt="project" src="https://img.shields.io/badge/Automation--Project--Semiconductor-1f6feb?style=for-the-badge" />
<img alt="python" src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img alt="docker" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
<img alt="license" src="https://img.shields.io/badge/License-MIT-555555?style=for-the-badge" />

<h2>Automation Project Semiconductor</h2>
<p>반도체 제조·품질 도메인의 자동화 프로토타입을 모아두는 저장소</p>

<p><a href="#projects">Projects</a> | <a href="#tech-stack">Tech stack</a> | <a href="#license">License</a></p>

</div>

---

## Overview

이 저장소는 반도체 제조·품질 도메인을 대상으로 한 자동화 프로젝트를 프로젝트별 폴더로 모아둡니다. 각 프로젝트는 독립적으로 설치·실행되며, 세부 사용법은 프로젝트 폴더 안의 README에 있습니다.

---

## Projects

| 프로젝트 | 설명 |
|---|---|
| [`handover-poc`](handover-poc) | 반도체 불량 대응 인수인계 자동화 핵심 로직 PoC. 공개 데이터셋 3종(UCI SECOM, NASA IMS 베어링 진동, WM-811K)에서 뽑은 신호를 가상 불량 이벤트로 묶고, 규칙 기반 엔진으로 원인과 담당 부서(M-ENG/P-ENG/YI)를 판정합니다. CLI, SQLite, FastAPI, 부서 간 인수인계 이력 추적, Streamlit 대시보드, PDF 리포트, Claude API 기반 요약, Docker 배포, Cloudflare Tunnel을 통한 외부 접속까지 포함합니다. |

> [!NOTE]
> 설치, CLI/API 사용법, 데이터 배치, 테스트 방법은 [`handover-poc/README.md`](handover-poc/README.md)를 참고하세요.

---

## Project architecture

```text
automation-project-semiconductor/
├─ LICENSE
└─ handover-poc/          # 반도체 불량 대응 인수인계 자동화 PoC
   ├─ src/                # ingest, signals, scenarios, diagnosis, api, dashboard, report, llm
   ├─ config/              # rules.yaml, scenarios.yaml
   ├─ tests/
   └─ README.md            # 프로젝트별 상세 문서
```

---

## Tech stack

프로젝트별로 사용하는 스택은 다르며, 아래는 현재 `handover-poc`에서 실제로 쓰는 구성입니다.

| 영역 | 사용 기술 |
|---|---|
| 언어/런타임 | Python 3.11 |
| 데이터/모델 | pandas, numpy, scikit-learn |
| API | FastAPI, uvicorn |
| 대시보드 | Streamlit |
| 저장소 | SQLite |
| 리포트 | ReportLab |
| LLM 연동 | Anthropic SDK (Claude API) |
| 배포 | Docker, Docker Compose |
| 테스트 | pytest |

---

## License

이 저장소는 [MIT License](LICENSE)를 따릅니다.

---

<div align="center">
개선 제안과 이슈를 환영합니다.
</div>
