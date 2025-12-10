import streamlit as st
from main import PpuClipDownloader, ChzzkURLParser, FilePathManager
import os
import re
import urllib.parse


@st.dialog("⚠️ 중복 파일 발견")
def show_duplicate_dialog(filepath: str) -> bool:
    """중복 파일 처리 다이얼로그"""
    st.warning(f"동일한 파일이 이미 존재합니다:")
    st.code(filepath)
    
    file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
    st.info(f"💾 파일 크기: {file_size:.1f} MB")
    
    if st.button("확인", use_container_width=True):
        st.rerun()


def remove_current_time_from_url(url: str) -> str:
    """URL에서 currentTime 파라미터 제거"""
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)
    
    # currentTime 제거
    if 'currentTime' in query_params:
        del query_params['currentTime']
    
    # 쿼리 파라미터 재구성
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    
    # URL 재구성
    clean_url = urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))
    
    return clean_url


def parse_time_to_seconds(time_str: str) -> int:
    """HH:MM:SS 또는 MM:SS 또는 SS를 초로 변환"""
    time_str = time_str.strip()
    
    # HH:MM:SS
    if re.match(r'^\d{1,2}:\d{2}:\d{2}$', time_str):
        h, m, s = map(int, time_str.split(':'))
        return h * 3600 + m * 60 + s
    
    # MM:SS
    elif re.match(r'^\d{1,2}:\d{2}$', time_str):
        m, s = map(int, time_str.split(':'))
        return m * 60 + s
    
    # SS
    elif re.match(r'^\d+$', time_str):
        return int(time_str)
    
    else:
        raise ValueError("시간 형식이 잘못됨 (예: 01:23:45, 23:45, 145)")


def seconds_to_hms(seconds: int) -> str:
    """초를 HH:MM:SS 형식으로 변환"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# 페이지 설정
st.set_page_config(
    page_title="ppu-clip",
    page_icon="🎬",
    layout="centered"
)

st.title("🎬 뿌클립")
st.caption("은뿌 클립 다운로더")

# URL 입력
url = st.text_input(
    "치지직 URL",
    placeholder="https://chzzk.naver.com/video/10646413?currentTime=2293",
    key="url_input"
)

# URL에서 currentTime 자동 파싱 및 제거
default_start_time = "00:00:00"
clean_url = url

if url:
    try:
        _, current_time = ChzzkURLParser.parse(url)
        if current_time is not None:
            default_start_time = seconds_to_hms(current_time)
            # URL에서 currentTime 파라미터 제거
            clean_url = remove_current_time_from_url(url)
            st.info(f"🕐 URL에서 시작 시간 자동 설정: {default_start_time}")
    except:
        pass

# 시간 입력
col1, col2 = st.columns(2)

with col1:
    start_time_str = st.text_input(
        "시작 시간 (HH:MM:SS)",
        value=default_start_time,
        placeholder="00:01:30",
        help="형식: HH:MM:SS, MM:SS, 또는 초 단위 숫자"
    )

with col2:
    duration = st.number_input(
        "길이 (초)", 
        min_value=1, 
        value=60,
        help="다운로드할 클립의 길이"
    )

# 다운로드 버튼
if st.button("📥 다운로드", type="primary", use_container_width=True):
    if not url:
        st.error("❌ URL을 입력하세요")
    elif not start_time_str:
        st.error("❌ 시작 시간을 입력하세요")
    else:
        try:
            # 시작 시간을 초로 변환
            start_seconds = parse_time_to_seconds(start_time_str)
            
            # 중복 파일 사전 체크
            # video_id와 title 먼저 가져오기
            from main import ChzzkAPIClient
            
            video_id, _ = ChzzkURLParser.parse(clean_url)
            api_client = ChzzkAPIClient(video_id)
            meta = api_client.get_video_meta()
            video_title = meta.get("videoTitle") or meta.get("title") or video_id
            
            # 출력 경로 체크
            file_manager = FilePathManager()
            output_path = file_manager.build_output_path(
                video_title, start_seconds, duration
            )
            
            # 중복 파일이면 다이얼로그 표시
            if output_path is None:
                safe_title = FilePathManager._sanitize_filename(video_title)
                start_str = FilePathManager._format_time(start_seconds)
                end_str = FilePathManager._format_time(start_seconds + duration)
                filename = f"{safe_title}_{start_str}-{end_str}.mp4"
                filepath = os.path.join(os.getcwd(), "clips", filename)
                
                show_duplicate_dialog(filepath)
            else:
                # 진행률 바 생성
                progress_bar = st.progress(0)
                progress_text = st.empty()
                
                def update_progress(percent):
                    """진행률 업데이트 콜백"""
                    progress_bar.progress(percent / 100)
                    progress_text.text(f"⏳ 다운로드 중... {percent}%")
                
                # Console 출력 캡처
                import io
                import sys
                
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()
                
                try:
                    downloader = PpuClipDownloader(
                        url=clean_url,
                        start=start_seconds,
                        duration=duration,
                        progress_callback=update_progress,
                    )
                    downloader.run()
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr
                    progress_bar.empty()
                    progress_text.empty()
                
                st.success("✅ 다운로드 완료!")
                
                # 다운로드 버튼 제공
                if os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        video_bytes = f.read()
                        file_size = len(video_bytes) / (1024 * 1024)  # MB
                        
                        st.download_button(
                            label=f"💾 클립 저장하기 ({file_size:.1f} MB)",
                            data=video_bytes,
                            file_name=os.path.basename(output_path),
                            mime="video/mp4",
                            use_container_width=True
                        )
                    
        except ValueError as e:
            st.error(f"❌ 시간 형식 오류: {e}")
        except Exception as e:
            st.error(f"❌ 오류 발생: {e}")
            with st.expander("상세 오류 정보"):
                st.code(str(e))

# 사이드바
with st.sidebar:
    st.header("📖 사용법")
    st.markdown("""
    1. 치지직 다시보기 URL 입력
    2. 시작 시간 & 길이 설정
    3. 다운로드 버튼 클릭
    4. 클립 저장하기 버튼으로 다운로드
    
    💡 URL에 `currentTime` 포함 시 자동 설정
    """)