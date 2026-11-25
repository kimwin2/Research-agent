# Efficient AI Daily

Hacker News · Hugging Face Daily Papers · arXiv에서 LLM / VLM / VLA 관련 글과 논문을 모으고,
Claude가 **효율(efficiency) 관점**에서 하루 5개를 골라 TL;DR로 정리해 GitHub Pages에 올리는 자동화입니다.

- 매일 07:17 KST에 GitHub Actions가 실행됩니다.
- 결과는 `data/digests/YYYY-MM-DD.json`으로 커밋되고, 그 JSON으로 정적 사이트를 만들어 Pages에 배포합니다.
- 한 번 소개한 항목은 다시 나오지 않습니다.

## 동작 방식

```
수집 (agent/sources.py)      HN Algolia API · HF daily_papers API · arXiv API  → 후보 약 100개
선별 (agent/digest.py)       Claude 호출 1회: 제목 + 짧은 요약만 보고 5개 선택
요약 (agent/digest.py)       Claude 호출 1회: 초록/본문을 읽고 헤드라인 · TL;DR · 핵심 3줄 · 효율 포인트 작성
게시 (agent/site.py)         JSON → _site/ (최신 · 날짜별 · 아카이브 · RSS) → GitHub Pages
```

Claude 호출은 하루 2회뿐이고, 도구(웹 검색 등)는 쓰지 않습니다.

## 설정 (최초 1회)

1. **Claude 인증 — 둘 중 하나를 저장소 Secret으로 등록** (Settings → Secrets and variables → Actions)
   - `ANTHROPIC_API_KEY`: Anthropic API 키. 사용한 토큰만큼 과금됩니다.
   - `CLAUDE_CODE_OAUTH_TOKEN`: Claude Pro/Max 구독으로 실행. 로컬에서 `claude setup-token`으로 발급합니다.
   - 둘 다 있으면 `ANTHROPIC_API_KEY`를 씁니다.
2. **Pages 켜기**: Settings → Pages → Build and deployment → Source를 **GitHub Actions**로 선택.
3. Actions 탭 → **Daily digest** → **Run workflow**로 한 번 실행해 확인.

사이트 주소: `https://<사용자>.github.io/<저장소>/`

> 스케줄 실행은 **기본 브랜치**의 워크플로만 동작합니다.

## 비용

실측 기준 하루 약 2.5만 입력 토큰 + 4천 출력 토큰입니다.

| 모델 (`CLAUDE_MODEL`) | 하루 | 한 달 |
| --- | --- | --- |
| `claude-opus-5-5` (기본값) | 약 $0.18 | 약 $5.5 |
| `claude-sonnet-5-5` | 약 $0.09 | 약 $2.7 |
| `claude-haiku-5-5` | 약 $0.005 | 약 $0.15 |

## 옵션 (저장소 Variables)

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `CLAUDE_MODEL` | `claude-opus-5-5` | 사용할 모델 |
| `DIGEST_ITEMS` | `5` | 하루 항목 수 |
| `DIGEST_LANGUAGE` | `Korean` | 요약 언어 |
| `SITE_TITLE`, `SITE_TAGLINE` | | 사이트 제목 / 부제 |

수집 키워드, 점수 기준, 후보 수는 `agent/config.py`에서, 선별 기준과 요약 형식은 `agent/digest.py` 상단의
프롬프트에서 바꿉니다.

## 로컬 실행

```bash
pip install -r requirements.txt
python -m agent.digest --dry-run     # 후보만 출력 (Claude 호출 없음)
ANTHROPIC_API_KEY=... python -m agent.digest          # 오늘 다이제스트 생성
python -m agent.site                 # _site/ 생성
python -m unittest discover -s tests
```
