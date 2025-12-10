"""
ppu-clip: 치지직 다시보기 구간 다운로드 도구

객체 지향 구조:
- LoggerConfig: 로거 설정 관리
- ChzzkURLParser: URL 파싱 및 검증
- ChzzkAPIClient: 치지직 API 통신
- FilePathManager: 파일 경로 및 이름 관리
- FFmpegDownloader: ffmpeg 기반 다운로드
- PpuClipDownloader: 전체 프로세스 오케스트레이션
"""

import sys
import json
import os
import re
import urllib.parse
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
import time
import argparse

import requests
import ffmpeg
from loguru import logger
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn


# =============================================================================
# 설정 클래스
# =============================================================================

class LoggerConfig:
    """로거 설정 관리"""
    
    def __init__(self, log_dir: str = "logs", log_filename: str = "ppu_clip.log"):
        self.log_dir = log_dir
        self.log_filename = log_filename
        
    def setup(self) -> None:
        """로거 초기화 및 설정"""
        # 로그 디렉터리 생성
        log_path = os.path.join(os.getcwd(), self.log_dir)
        os.makedirs(log_path, exist_ok=True)
        
        logger.remove()
        
        # 콘솔 출력: ERROR 이상만
        logger.add(
            sys.stderr,
            level="ERROR",
            format="<red>{time:YYYY-MM-DD HH:mm:ss}</red> | "
                   "<level>{level: <8}</level> | "
                   "<level>{message}</level>",
        )
        
        # 파일 출력: DEBUG 전부
        logger.add(
            os.path.join(log_path, self.log_filename),
            rotation="00:00",
            retention="7 days",
            encoding="utf-8",
            enqueue=True,
            level="DEBUG",
            backtrace=True,
            diagnose=False,
        )


@dataclass
class VideoInfo:
    """영상 정보"""
    video_id: str
    title: str
    url_current_time: Optional[int] = None


# =============================================================================
# URL 파싱
# =============================================================================

class ChzzkURLParser:
    """치지직 URL 파싱"""
    
    @staticmethod
    def parse(url: str) -> Tuple[str, Optional[int]]:
        """
        치지직 URL에서 video_id와 currentTime 추출
        
        Args:
            url: 치지직 다시보기 URL
            
        Returns:
            (video_id, current_time_seconds)
            
        Examples:
            https://chzzk.naver.com/video/10646413?currentTime=2293
            -> ("10646413", 2293)
        """
        parsed = urllib.parse.urlparse(url)
        video_id = parsed.path.rstrip("/").split("/")[-1]
        
        query_params = urllib.parse.parse_qs(parsed.query)
        current_time = None
        
        if "currentTime" in query_params and query_params["currentTime"]:
            try:
                current_time = int(query_params["currentTime"][0])
            except ValueError:
                raise ValueError("currentTime 파싱 실패: 정수가 아님")
        
        return video_id, current_time


# =============================================================================
# API 클라이언트
# =============================================================================

class ChzzkAPIClient:
    """치지직 API 통신"""
    
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Referer": "https://chzzk.naver.com/",
    }
    
    def __init__(self, video_id: str):
        self.video_id = video_id
        
    def get_video_meta(self) -> Dict[str, Any]:
        """영상 메타데이터 요청"""
        last_error = None
        
        for version in ("v3", "v2"):
            url = f"https://api.chzzk.naver.com/service/{version}/videos/{self.video_id}"
            
            try:
                response = requests.get(url, headers=self.HEADERS, timeout=10)
                if response.ok:
                    data = response.json()
                    return data.get("content", data)
                last_error = (response.status_code, response.text[:200])
            except Exception as e:
                last_error = str(e)
                
        raise RuntimeError(f"video meta 요청 실패: {last_error}")
    
    def get_playback_json(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        """playback JSON 획득"""
        # 1) liveRewindPlaybackJson 체크
        live_rewind = meta.get("liveRewindPlaybackJson")
        if live_rewind:
            try:
                return json.loads(live_rewind)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"liveRewindPlaybackJson 파싱 실패: {e}")
        
        # 2) 일반 VOD - inKey로 neonplayer API 호출
        in_key = self._find_in_key(meta)
        video_id = self._find_video_id(meta)
        
        url = f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{video_id}"
        params = {
            "key": in_key,
            "env": "real",
            "lc": "ko",
            "cpl": "ko",
            "sid": "2099",
        }
        
        response = requests.get(url, headers=self.HEADERS, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _find_in_key(self, meta: Dict[str, Any]) -> str:
        """inKey 찾기"""
        in_key = meta.get("inKey") or meta.get("inkey")
        if not in_key:
            in_key = self._find_first_key(meta, "inKey")
        if not in_key:
            raise RuntimeError("inKey 없음 (API 변경 또는 일반 VOD 아님)")
        return in_key
    
    def _find_video_id(self, meta: Dict[str, Any]) -> str:
        """videoId 찾기"""
        video_id = meta.get("videoId") or meta.get("id")
        if not video_id:
            video_id = self._find_first_key(meta, "videoId")
        if not video_id:
            raise RuntimeError("videoId/id 없음")
        return video_id
    
    @staticmethod
    def _find_first_key(obj: Any, key: str) -> Optional[Any]:
        """중첩된 dict/list에서 key 재귀 탐색"""
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for value in obj.values():
                result = ChzzkAPIClient._find_first_key(value, key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = ChzzkAPIClient._find_first_key(item, key)
                if result is not None:
                    return result
        return None


# =============================================================================
# M3U8 추출
# =============================================================================

class M3U8Extractor:
    """playback JSON에서 m3u8 URL 추출"""
    
    @staticmethod
    def extract(playback: Dict[str, Any]) -> str:
        """m3u8 URL 추출"""
        urls = M3U8Extractor._collect_m3u8_urls(playback)
        if not urls:
            raise RuntimeError("m3u8 URL을 찾지 못함")
        return urls[0]
    
    @staticmethod
    def _collect_m3u8_urls(obj: Any) -> List[str]:
        """재귀적으로 m3u8 URL 수집"""
        urls = []
        
        if isinstance(obj, dict):
            for value in obj.values():
                urls.extend(M3U8Extractor._collect_m3u8_urls(value))
        elif isinstance(obj, list):
            for item in obj:
                urls.extend(M3U8Extractor._collect_m3u8_urls(item))
        elif isinstance(obj, str) and ".m3u8" in obj:
            urls.append(obj)
            
        return urls


# =============================================================================
# 파일 경로 관리
# =============================================================================

class FilePathManager:
    """파일 경로 및 이름 관리"""
    
    def __init__(self, output_dir: str = "clips"):
        self.output_dir = output_dir
        
    def build_output_path(
        self,
        video_title: str,
        start_sec: int,
        duration: int,
    ) -> Optional[str]:
        """
        출력 파일 경로 생성
        
        Returns:
            파일 경로 or None (이미 존재하는 경우)
        """
        # 출력 디렉터리 생성
        clips_dir = os.path.join(os.getcwd(), self.output_dir)
        os.makedirs(clips_dir, exist_ok=True)
        
        # 파일명 생성
        safe_title = self._sanitize_filename(video_title)
        start_str = self._format_time(start_sec)
        end_str = self._format_time(start_sec + duration)
        filename = f"{safe_title}_{start_str}-{end_str}.mp4"
        
        output_path = os.path.join(clips_dir, filename)
        
        # 중복 파일 체크
        if os.path.exists(output_path):
            return None
            
        return output_path
    
    @staticmethod
    def _sanitize_filename(name: str, max_length: int = 100) -> str:
        """파일명에서 금지 문자 제거"""
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        name = name.strip().rstrip(".")
        if not name:
            name = "clip"
        if len(name) > max_length:
            name = name[:max_length]
        return name
    
    @staticmethod
    def _format_time(seconds: int) -> str:
        """초를 HHMMSS 포맷으로 변환"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}{minutes:02d}{secs:02d}"


# =============================================================================
# FFmpeg 다운로더
# =============================================================================

class FFmpegDownloader:
    """ffmpeg를 이용한 클립 다운로드"""
    
    def __init__(self, console: Console):
        self.console = console
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Referer": "https://chzzk.naver.com/",
        }
    
    def download(
        self,
        m3u8_url: str,
        output_path: str,
        start_sec: int,
        duration: int,
    ) -> None:
        """
        m3u8 URL에서 특정 구간 다운로드
        
        Args:
            m3u8_url: M3U8 스트림 URL
            output_path: 출력 파일 경로
            start_sec: 시작 시간 (초)
            duration: 다운로드 길이 (초)
        """
        logger.info(f"ffmpeg start={start_sec}, duration={duration}")
        logger.debug(f"input m3u8={m3u8_url}")
        logger.debug(f"output file={output_path}")
        
        # HTTP 헤더 포맷
        headers_str = (
            f"User-Agent: {self.headers['User-Agent']}\r\n"
            "Referer: https://chzzk.naver.com/\r\n"
        )
        
        # ffmpeg 프로세스 생성
        process = self._create_ffmpeg_process(
            m3u8_url, output_path, start_sec, duration, headers_str
        )
        
        # 진행률 표시하며 다운로드
        self._download_with_progress(process, duration)
        
        logger.success(f"저장 완료: {output_path}")
        self.console.print(f"[bold green]다운로드 완료![/] → {output_path}\n")
    
    def _create_ffmpeg_process(
        self,
        m3u8_url: str,
        output_path: str,
        start_sec: int,
        duration: int,
        headers: str,
    ):
        """ffmpeg 프로세스 생성"""
        return (
            ffmpeg
            .input(
                m3u8_url,
                ss=start_sec,
                allowed_extensions="ALL",
                extension_picky=0,
                protocol_whitelist="file,http,https,tcp,tls",
                headers=headers,
            )
            .output(
                output_path,
                t=duration,
                c="copy",
            )
            .global_args(
                "-hide_banner",
                "-loglevel", "error",
                "-progress", "pipe:1",
                "-nostats",
            )
            .overwrite_output()
            .run_async(
                pipe_stdout=True,
                pipe_stderr=True,
            )
        )
    
    def _download_with_progress(self, process, duration: int) -> None:
        """진행률 표시하며 다운로드"""
        total_us = duration * 1_000_000  # 마이크로초 변환
        current_percent = -1
        
        with Progress(
            TextColumn("[progress.description]{task.description}", justify="left"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        ) as progress:
            task = progress.add_task("[cyan]다운로드 중...", total=100)
            
            try:
                while True:
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                        continue
                    
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    line = line.strip()
                    
                    # 진행률 파싱: out_time_ms=12345678
                    if line.startswith("out_time_ms="):
                        try:
                            out_us = int(line.split("=", 1)[1])
                        except ValueError:
                            continue
                        
                        ratio = min(out_us / total_us, 1.0) if total_us > 0 else 0.0
                        percent = int(ratio * 100)
                        
                        if percent != current_percent:
                            current_percent = percent
                            progress.update(task, completed=percent)
                
                # 프로세스 종료 확인
                return_code = process.wait()
                if return_code != 0:
                    self._handle_ffmpeg_error(process, return_code)
                    
            except Exception as e:
                logger.error(f"다운로드 중 예외 발생: {e}")
                raise
    
    def _handle_ffmpeg_error(self, process, return_code: int) -> None:
        """ffmpeg 오류 처리"""
        try:
            err_output = process.stderr.read()
            if isinstance(err_output, bytes):
                err_output = err_output.decode("utf-8", errors="ignore")
        except Exception:
            err_output = ""
        
        logger.error(f"ffmpeg 종료 코드: {return_code}")
        if err_output:
            logger.error(f"ffmpeg stderr:\n{err_output}")
        
        self.console.print(
            "[bold red]\n다운로드 중 오류 발생[/]\n"
            "자세한 내용은 logs/ppu_clip.log 확인\n"
        )
        raise RuntimeError(f"ffmpeg failed with code {return_code}")


# =============================================================================
# 메인 다운로더
# =============================================================================

class PpuClipDownloader:
    """치지직 클립 다운로더 - 전체 프로세스 오케스트레이션"""
    
    def __init__(
        self,
        url: str,
        start: Optional[int],
        duration: int = 60,
        output: Optional[str] = None,
    ):
        self.url = url
        self.user_start = start
        self.duration = duration
        self.output = output
        
        self.console = Console()
        self.url_parser = ChzzkURLParser()
        self.file_manager = FilePathManager()
        self.downloader = FFmpegDownloader(self.console)
        
    def run(self) -> None:
        """다운로드 프로세스 실행"""
        # 1. URL 파싱
        video_info = self._parse_url()
        
        # 2. 시작 시간 결정
        start_sec = self._determine_start_time(video_info)
        
        # 3. 메타데이터 및 재생 정보 획득
        api_client = ChzzkAPIClient(video_info.video_id)
        meta = api_client.get_video_meta()
        video_info.title = meta.get("videoTitle") or meta.get("title") or video_info.video_id
        
        logger.info(f"video_id={video_info.video_id}, title={video_info.title}")
        logger.info(f"start_sec={start_sec}, duration={self.duration}")
        
        # 4. M3U8 URL 추출
        playback = api_client.get_playback_json(meta)
        m3u8_url = M3U8Extractor.extract(playback)
        logger.debug(f"m3u8={m3u8_url}")
        
        # 5. 출력 경로 결정
        output_path = self.file_manager.build_output_path(
            video_info.title, start_sec, self.duration
        )
        
        # 중복 파일 체크
        if output_path is None:
            self._handle_duplicate_file(video_info, start_sec)
            return
        
        logger.info(f"output={output_path}")
        
        # 6. 다운로드 정보 출력
        self._print_download_info(video_info, start_sec, output_path)
        
        # 7. 다운로드 실행
        self.downloader.download(m3u8_url, output_path, start_sec, self.duration)
    
    def _parse_url(self) -> VideoInfo:
        """URL 파싱"""
        video_id, url_current_time = self.url_parser.parse(self.url)
        return VideoInfo(
            video_id=video_id,
            title="",  # 나중에 채워짐
            url_current_time=url_current_time,
        )
    
    def _determine_start_time(self, video_info: VideoInfo) -> int:
        """시작 시간 결정"""
        # 시간 중첩 체크
        if video_info.url_current_time is not None and self.user_start is not None:
            logger.error(
                f"시간 중첩: url_current_time={video_info.url_current_time}, "
                f"user_start={self.user_start}"
            )
            raise ValueError(
                "URL에 currentTime이 있는데 --start도 지정됨 (시간 중첩)"
            )
        
        # 우선순위: user_start > url_current_time > 0
        if self.user_start is not None:
            return self.user_start
        elif video_info.url_current_time is not None:
            return video_info.url_current_time
        else:
            return 0
    
    def _handle_duplicate_file(self, video_info: VideoInfo, start_sec: int) -> None:
        """중복 파일 처리"""
        safe_title = FilePathManager._sanitize_filename(video_info.title)
        start_str = FilePathManager._format_time(start_sec)
        end_str = FilePathManager._format_time(start_sec + self.duration)
        filename = f"{safe_title}_{start_str}-{end_str}.mp4"
        
        output_path = os.path.join(os.getcwd(), "clips", filename)
        
        logger.warning(f"중복 파일 존재: {output_path}")
        self.console.print("[bold yellow]⚠ 이미 동일한 파일이 존재함[/]")
        self.console.print(f"[green]{output_path}[/]")
        self.console.print("[bold yellow]다운로드 건너뜀[/]\n")
    
    def _print_download_info(
        self,
        video_info: VideoInfo,
        start_sec: int,
        output_path: str,
    ) -> None:
        """다운로드 정보 출력"""
        start_str = self._format_time_hms(start_sec)
        end_str = self._format_time_hms(start_sec + self.duration)
        
        self.console.rule("[bold cyan]ppu-clip 다운로드")
        self.console.print(f"[bold]제목[/]: {video_info.title}")
        self.console.print(f"[bold]영상ID[/]: {video_info.video_id}")
        self.console.print(f"[bold]구간[/]: {start_str} ~ {end_str} ({self.duration}초)")
        self.console.print(f"[bold]저장[/]: {output_path}")
        self.console.print()
        self.console.print("[green]다운로드 시작...[/]\n")
    
    @staticmethod
    def _format_time_hms(seconds: int) -> str:
        """초를 HH:MM:SS 포맷으로 변환"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# =============================================================================
# CLI 엔트리포인트
# =============================================================================

def main():
    """CLI 엔트리포인트"""
    parser = argparse.ArgumentParser(
        description="ppu-clip: 치지직 다시보기 구간 다운로드 도구"
    )
    parser.add_argument(
        "url",
        help="치지직 다시보기 URL (예: https://chzzk.naver.com/video/10646413?currentTime=22935)",
    )
    parser.add_argument(
        "-s",
        "--start",
        type=int,
        default=None,
        help="시작 시각(초). URL에 currentTime이 있으면 같이 줄 수 없음.",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=int,
        default=60,
        help="다운로드 길이(초). 기본값 60",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=(
            "출력 경로. "
            "· .mp4로 끝나면 해당 파일로 저장\n"
            "· 디렉터리면 그 안에 [제목]_HHMMSS-HHMMSS.mp4 형식으로 저장\n"
            "· 지정 안 하면 ./clips/ 아래에 자동 저장"
        ),
    )
    
    args = parser.parse_args()
    
    # 로거 설정
    logger_config = LoggerConfig()
    logger_config.setup()
    
    logger.info(
        f"CLI 호출: url={args.url}, start={args.start}, "
        f"duration={args.duration}, output={args.output}"
    )
    
    # 다운로더 실행
    downloader = PpuClipDownloader(
        url=args.url,
        start=args.start,
        duration=args.duration,
        output=args.output,
    )
    downloader.run()


if __name__ == "__main__":
    main()