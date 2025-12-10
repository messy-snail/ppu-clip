# 📌 **PPU-Clip — 치지직 다시보기 구간 다운로더**

**은뿌 방송 다시보기에서 원하는 순간만 빠르게 저장하기 위한 전용 도구**

PPU-Clip은 치지직(Chzzk) 다시보기 URL을 입력하면
특정 구간만 고화질로 빠르게 추출해주는 간단한 CLI/웹 도구입니다.

> “다시보고 싶은 은뿌의 순간들, 딱 그 구간만 바로 뽑아내기.”

## ✨ 주요 기능

* 🔗 **치지직 다시보기 URL 자동 분석**

  * `?currentTime=12345` 포함한 URL도 자동 처리
  * 영상 ID와 재생 시간 자동 추출

* 🎬 **원하는 구간만 고화질 다운로드**

  * 시작 시간 및 duration(초 단위) 지정 가능
  * ffmpeg 기반이라 빠르고 안정적

* 💾 **예쁜 파일 이름 자동 생성**

  * `제목_시작시간-끝시간.mp4` 형태로 저장
  * 동일 파일 존재 시 자동 경고 후 중단

* 📊 **다운로드 진행률 표시**

  * Rich 기반 프로그레스 바 제공
  * 깔끔하고 직관적인 UI

* 🗂 **로그 자동 저장**

  * `logs/` 아래에 날짜별로 관리
  * 오류 발생 시 추적 용이

* 🌐 **Streamlit 웹 버전 지원(선택)**

  * URL → 구간 입력 → 다운로드 버튼
  * 로컬 웹 앱 형태로 실행 가능


## 🧩 시스템 요구사항

- Python 3.10 이상
- ffmpeg 8.0 이상 (CLI에서 `ffmpeg -version`으로 확인)

## 🛠 설치 방법

### uv 기반 실행

```bash
uv sync
uv run main.py "<치지직 URL>" --duration 10
```

## 🚀 CLI 사용 예시

### 기본 예시

```bash
uv run main.py "https://chzzk.naver.com/video/10646413?currentTime=22935" --duration 20
```

### 시작 시간을 직접 지정

```bash
uv run main.py "https://chzzk.naver.com/video/10646413" --start 3600 --duration 30
```

### 저장 위치 지정

```bash
uv run main.py "URL" --duration 10 --output "./my_clips"
```


## 🌐 Streamlit 웹 버전 실행

```bash
uv run streamlit run app.py
```

실행 후 브라우저가 자동으로 열립니다.


## 📁 프로젝트 구조

```
ppu_clip/
├─ main.py               # CLI 핵심 로직
├─ app.py                # Streamlit 웹 UI
├─ pyproject.toml
├─ logs/                 # 로그 자동 저장
└─ clips/                # 다운로드 파일 저장
```

## 💙 Note

이 프로젝트는
*은뿌 다시보기에서 특정 구간만 저장하고 싶었던 니즈*에서 출발했습니다.
편하게 사용할 수 있도록 계속 다듬어 나갈 예정입니다.
