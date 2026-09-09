# AI-DLC State Tracking

## Project Information
- **Project Type**: Greenfield
- **Start Date**: 2026-09-09T11:37:51Z
- **Current Stage**: OPERATIONS (placeholder)

## Workspace State
- **Existing Code**: No
- **Programming Languages**: None detected
- **Build System**: None detected
- **Project Structure**: Empty
- **Reverse Engineering Needed**: No
- **Workspace Root**: /Users/junho/coding_work/es_api

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Mode | Decided At |
|---|---|---|---|
| Security Baseline | No | - | Requirements Analysis |
| Resiliency Baseline | No | - | Requirements Analysis |
| Property-Based Testing | Yes | Partial (PBT-02, PBT-03, PBT-07, PBT-08, PBT-09 blocking; others advisory) | Requirements Analysis |

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Reverse Engineering (SKIPPED - greenfield)
- [x] Requirements Analysis (APPROVED)
- [x] User Stories (SKIP - developer tooling, single user type)
- [x] Workflow Planning
- [x] Application Design - APPROVED
- [ ] Units Generation - SKIP (single package)

### 🟢 CONSTRUCTION PHASE - Unit: es-crawler
- [x] Functional Design - APPROVED
- [x] NFR Requirements - APPROVED (PBT-09 satisfied: hypothesis)
- [x] NFR Design - APPROVED
- [ ] Infrastructure Design - SKIP (no cloud resources)
- [x] Code Generation - APPROVED | 101 tests pass, ruff/mypy clean
- [x] Build and Test - APPROVED

### 🟡 OPERATIONS PHASE
- [x] Operations - PLACEHOLDER (워크플로는 Build and Test 로 완료)

## Execution Plan Summary
- **Units of Work**: 1 (es-crawler)
- **Stages to Execute**: 6 (Application Design, Functional Design, NFR Requirements, NFR Design, Code Generation, Build and Test)
- **Stages Skipped**: 4 (Reverse Engineering, User Stories, Units Generation, Infrastructure Design)
- **Risk Level**: Low

## Convention Precedence (user directive 2026-09-09)
`/Users/junho/coding_work/general_implementation` conventions OVERRIDE all other conventions,
including this project's CLAUDE.md-derived choices and previously approved AI-DLC decisions.

### Overridden decisions
| Was | Now | Source |
|---|---|---|
| App Design Q2=B: two CLI subcommands | Single entry point, one RUN SUMMARY | prohibition #12, section 3.2 |
| D-3, D-4: scheduler chains extract && convert | Single command per run | same |
| App Design Q1=A: flat 9 modules | Scaffold shared modules + project modules | section 1.5, 3.1 |
| NFR Q1=B: Python 3.12 | Python 3.14 | C7 |
| NFR Q2=A: pyproject + pip install -e . | No install; python src/run.py | C7, section 3.1 |
| NFR Q3=A: elasticsearch>=8.15,<9 | Exact pin elasticsearch==8.15.x | requirements.txt rule |
| NFR-6: secrets in .env | configs/env.yaml | CQ4=A |

### New requirements introduced by the convention
- RUN SUMMARY block (stdout; progress to stderr)
- schema.py single source + validate() for the format-recovery channel
- synth.py synthetic ES hits; file-based test fixtures prohibited
- Porting apparatus: sync.sh, .gitattributes export-ignore, TODO.md, todo/, git tags
- Package name: es_crawler

## Resolved Decisions
- **D-1**: Scheduler runs daily at 19:00 KST; fetch window = [previous day 18:00 KST, current day 18:00 KST). Chunk boundaries anchored at a configurable anchor time (default 18:00 KST), not midnight. Output files labeled by window END date.
- **D-2**: Timezone configurable, default Asia/Seoul; converted to UTC for ES range queries (KST 18:00 = UTC 09:00).
- **D-3**: `convert` takes the same date-range arguments as `extract`; missing JSONL is skip+warning, not an error.
- **D-4**: Scheduler runs `extract && convert` chained; a failed extract does not trigger convert.

## Application Design Decisions
| # | Decision |
|---|---|
| Q1=A | 9-module split kept |
| Q2=B | CLI subcommands: `extract`, `convert` (no `run`) |
| Q3=B | CSV conversion batched after all extraction |
| Q4=A | YAML config (PyYAML) |
| Q5=C | Public API: `CrawlService` class (`.extract()` / `.convert()` / `.run()`) |
| Q6=A | `elasticsearch-py` used directly; no extra abstraction layer |
| Q7=A | Checkpoint: `{output_dir}/.checkpoint.json`, atomic write |
| Q8=A | Chunk key: window end time, ISO 8601 with timezone |

## Current Status
- **Lifecycle Phase**: INCEPTION
- **Current Stage**: OPERATIONS (placeholder)
- **Next Stage**: None - AI-DLC workflow complete
- **Status**: All planned stages complete

## Workflow Complete
- **Completed**: 2026-09-09
- **Stages executed**: 8 (Workspace Detection, Requirements Analysis, Workflow Planning, Application Design, Functional Design, NFR Requirements, NFR Design, Code Generation, Build and Test)
- **Stages skipped**: 4 (Reverse Engineering, User Stories, Units Generation, Infrastructure Design)
- **Verification**: 105 tests pass (8 consecutive runs, different seeds), ruff/mypy clean, export surface 29 files
- **Defects found and fixed during Build and Test**: 3 (DST offset invariant, wall-clock chunk arithmetic, filename minute-granularity collision) - all found by property-based tests
- **Open items**: commit+tag (not requested), sync.sh preflight (needs tag), integration tests (needs cluster), INPUT_SCHEMA and batch_size (need real data)
