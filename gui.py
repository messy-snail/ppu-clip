# gui.py
import os
import re
import sys
import urllib.parse

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QProgressBar,
    QMessageBox,
    QFrame,
)
from PySide6.QtGui import QFont, QPixmap

from main import (
    LoggerConfig,
    PpuClipDownloader,
    ChzzkURLParser,
    ChzzkAPIClient,
    FilePathManager,
)


STYLE_SHEET = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    font-size: 12pt;
}

QLabel {
    color: #cdd6f4;
    font-weight: 500;
}

QLabel#title {
    font-size: 18pt;
    font-weight: bold;
    color: #89dceb;
    padding: 10px;
}

QLineEdit {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 8px;
    padding: 8px 12px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}

QLineEdit:focus {
    border: 2px solid #89b4fa;
}

QSpinBox {
    background-color: #313244;
    border: 2px solid #45475a;
    border-radius: 8px;
    padding: 8px 12px;
    color: #cdd6f4;
}

QSpinBox:focus {
    border: 2px solid #89b4fa;
}

QSpinBox::up-button, QSpinBox::down-button {
    background-color: #45475a;
    border-radius: 4px;
    width: 20px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #585b70;
}

QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 10pt;
}

QPushButton:hover {
    background-color: #74c7ec;
}

QPushButton:pressed {
    background-color: #89dceb;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QPushButton#checkBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
}

QPushButton#checkBtn:hover {
    background-color: #94e2d5;
}

QPushButton#downloadBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-size: 11pt;
}

QPushButton#downloadBtn:hover {
    background-color: #eba0ac;
}

QProgressBar {
    border: 2px solid #45475a;
    border-radius: 8px;
    text-align: center;
    background-color: #313244;
    color: #cdd6f4;
    font-weight: bold;
}

QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa,
        stop:1 #74c7ec
    );
    border-radius: 6px;
}

QFrame#separator {
    background-color: #45475a;
    max-height: 2px;
}

QLabel#statusLabel {
    color: #a6e3a1;
    font-weight: bold;
    padding: 5px;
}

QMessageBox {
    background-color: #1e1e2e;
}

QMessageBox QLabel {
    color: #cdd6f4;
}

QMessageBox QPushButton {
    min-width: 80px;
}
"""


def remove_current_time_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)

    if "currentTime" in query_params:
        del query_params["currentTime"]

    new_query = urllib.parse.urlencode(query_params, doseq=True)
    clean_url = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
    return clean_url


def parse_time_to_seconds(time_str: str) -> int:
    time_str = time_str.strip()

    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", time_str):
        h, m, s = map(int, time_str.split(":"))
        return h * 3600 + m * 60 + s
    elif re.match(r"^\d{1,2}:\d{2}$", time_str):
        m, s = map(int, time_str.split(":"))
        return m * 60 + s
    elif re.match(r"^\d+$", time_str):
        return int(time_str)
    else:
        raise ValueError("시간 형식이 잘못됨 (예: 01:23:45, 23:45, 145)")


def seconds_to_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def configure_ffmpeg_path():
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        ffmpeg_dir = os.path.join(base_dir, "ffmpeg")
        if os.path.exists(os.path.join(ffmpeg_dir, "ffmpeg.exe")):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    else:
        choco_ffmpeg_dir = r"C:\ProgramData\chocolatey\bin"
        if os.path.exists(os.path.join(choco_ffmpeg_dir, "ffmpeg.exe")):
            os.environ["PATH"] = choco_ffmpeg_dir + os.pathsep + os.environ.get(
                "PATH", ""
            )


class DownloadWorker(QThread):
    progress_changed = Signal(int)
    finished_ok = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, url: str, start_sec: int, duration: int, output_path: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.start_sec = start_sec
        self.duration = duration
        self.output_path = output_path

    def run(self):
        try:
            def cb(percent: int):
                self.progress_changed.emit(percent)

            downloader = PpuClipDownloader(
                url=self.url,
                start=self.start_sec,
                duration=self.duration,
                output=None,
                progress_callback=cb,
            )
            downloader.run()
            self.finished_ok.emit(self.output_path)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker: DownloadWorker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("🎬 뿌클립 (ppu-clip GUI)")
        self.setFixedSize(1300, 550) 

        # 메인 레이아웃: 좌우 분할
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 왼쪽: 기존 컨트롤들
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)

        # 타이틀
        title_label = QLabel("🎬 뿌클립 다운로더")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title_label)

        # 구분선
        separator1 = QFrame()
        separator1.setObjectName("separator")
        separator1.setFrameShape(QFrame.HLine)
        left_layout.addWidget(separator1)

        # URL + 확인 버튼
        url_layout = QHBoxLayout()
        url_layout.setSpacing(10)
        url_label = QLabel("📺 치지직 URL")
        url_label.setMinimumWidth(100)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://chzzk.naver.com/video/10566904?currentTime=15220"
        )

        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)

        # 시작 시간 + 길이
        time_layout = QHBoxLayout()
        time_layout.setSpacing(10)

        start_label = QLabel("⏱️ 시작 시간")
        start_label.setMinimumWidth(100)
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("00:00:00 / 23:45 / 145")
        self.start_edit.setText("")
        
        self.fetch_time_btn = QPushButton("수동")
        self.fetch_time_btn.setObjectName("checkBtn")
        self.fetch_time_btn.setMaximumWidth(120)

        duration_label = QLabel("⏳ 길이(초)")
        duration_label.setMinimumWidth(100)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 60 * 60 * 24)
        self.duration_spin.setValue(60)
        self.duration_spin.setMinimumWidth(100)

        time_layout.addWidget(start_label)
        time_layout.addWidget(self.start_edit)
        time_layout.addWidget(self.fetch_time_btn)
        time_layout.addWidget(duration_label)
        time_layout.addWidget(self.duration_spin)

        # 진행률
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(5)
        progress_label = QLabel("📊 다운로드 진행률")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(30)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)

        # 버튼 / 상태
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
        self.download_btn = QPushButton("📥 다운로드 시작")
        self.download_btn.setObjectName("downloadBtn")
        self.download_btn.setMinimumHeight(45)
        
        status_container = QHBoxLayout()
        status_label_title = QLabel("💬 상태")
        self.status_label = QLabel("대기 중")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_container.addWidget(status_label_title)
        status_container.addWidget(self.status_label)
        
        btn_layout.addWidget(self.download_btn, 2)
        btn_layout.addLayout(status_container, 1)

        left_layout.addLayout(url_layout)
        left_layout.addLayout(time_layout)
        left_layout.addLayout(progress_layout)
        
        # 구분선
        separator2 = QFrame()
        separator2.setObjectName("separator")
        separator2.setFrameShape(QFrame.HLine)
        left_layout.addWidget(separator2)
        
        left_layout.addLayout(btn_layout)
        
        # 시작 시간 자동 설정 정보 라벨
        self.time_info_label = QLabel("")
        self.time_info_label.setStyleSheet("""
            QLabel {
                color: #a6e3a1;
                font-size: 10pt;
                padding: 5px;
            }
        """)
        self.time_info_label.setAlignment(Qt.AlignCenter)
        self.time_info_label.setWordWrap(True)
        left_layout.addWidget(self.time_info_label)
        
        # 오른쪽: 사용 방법 가이드
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)
        
        guide_title = QLabel("📖 사용 방법")
        guide_title.setObjectName("title")
        guide_title.setAlignment(Qt.AlignCenter)
        
        # 이미지 섹션
        image_label = QLabel()
        image_path = os.path.join(os.path.dirname(__file__), "docs", "figure.png")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            # 이미지 크기 조정 (너비 기준)
            scaled_pixmap = pixmap.scaledToWidth(350, Qt.SmoothTransformation)
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignCenter)
            image_label.setStyleSheet("""
                QLabel {
                    background-color: #313244;
                    border: 2px solid #45475a;
                    border-radius: 8px;
                    padding: 10px;
                }
            """)
        
        guide_text = QLabel(
            "💡 <b>클립에서 '풀버전 보러가기'</b> 눌러서<br>"
            "나오는 링크를 입력하면<br>"
            "시작 시간이 자동으로 설정됨<br><br>"
            "1. 치지직 다시보기 URL 입력<br>"
            "2. 시작 시간 & 길이 설정 (선택)<br>"
            "   <b>수동</b>: URL에서 시작 시간 추출<br>"
            "3. 다운로드 시작 클릭"
        )
        guide_text.setStyleSheet("""
            QLabel {
                background-color: #313244;
                border: 2px solid #45475a;
                border-radius: 8px;
                padding: 15px;
                line-height: 1.6;
                color: #cdd6f4;
            }
        """)
        guide_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        guide_text.setWordWrap(True)
        
        right_layout.addWidget(guide_title)
        if os.path.exists(image_path):
            right_layout.addWidget(image_label)
        right_layout.addWidget(guide_text, 1)
        right_layout.addStretch()
        
        # 메인 레이아웃에 좌우 추가
        main_layout.addLayout(left_layout, 2)
        main_layout.addLayout(right_layout, 1)

        # 시그널 연결
        self.download_btn.clicked.connect(self.on_download_clicked)
        self.fetch_time_btn.clicked.connect(self.on_fetch_time_clicked)

    def _show_error(self, msg: str):
        QMessageBox.critical(self, "❌ 오류", msg)

    def _show_info(self, msg: str):
        QMessageBox.information(self, "ℹ️ 알림", msg)

    def on_fetch_time_clicked(self):
        url = self.url_edit.text().strip()
        if not url:
            self.time_info_label.setText("⚠️ URL을 먼저 입력해주세요")
            self.time_info_label.setStyleSheet("color: #f38ba8; font-size: 10pt; padding: 5px;")
            return

        try:
            _, current_time = ChzzkURLParser.parse(url)
        except Exception as e:
            self.time_info_label.setText(f"⚠️ URL 파싱 실패: {e}")
            self.time_info_label.setStyleSheet("color: #f38ba8; font-size: 10pt; padding: 5px;")
            return

        if current_time is not None:
            self.start_edit.setText(seconds_to_hms(current_time))
            self.time_info_label.setText(f"💡 URL의 currentTime을 가져왔습니다: {seconds_to_hms(current_time)}")
            self.time_info_label.setStyleSheet("color: #a6e3a1; font-size: 10pt; padding: 5px;")
        else:
            self.time_info_label.setText("⚠️ URL에 currentTime 파라미터가 없습니다")
            self.time_info_label.setStyleSheet("color: #f9e2af; font-size: 10pt; padding: 5px;")

    def on_download_clicked(self):
        url = self.url_edit.text().strip()
        if not url:
            self._show_error("URL을 입력해줘.")
            return

        clean_url = remove_current_time_from_url(url)

        try:
            video_id, url_current_time = ChzzkURLParser.parse(url)
        except Exception as e:
            self._show_error(f"URL 파싱 실패: {e}")
            return

        start_str = self.start_edit.text().strip()
        try:
            if start_str:
                # 유저가 수동으로 입력한 경우 우선
                start_sec = parse_time_to_seconds(start_str)
                self.time_info_label.setText(f"💡 사용자 입력 시작 시간 사용: {seconds_to_hms(start_sec)}")
                self.time_info_label.setStyleSheet("color: #89dceb; font-size: 10pt; padding: 5px;")
            elif url_current_time is not None:
                # currentTime 쿼리가 있는 경우 자동 설정
                start_sec = url_current_time
                self.start_edit.setText(seconds_to_hms(start_sec))
                self.time_info_label.setText(f"💡 자동으로 시작 시간을 {seconds_to_hms(start_sec)}로 설정합니다")
                self.time_info_label.setStyleSheet("color: #a6e3a1; font-size: 10pt; padding: 5px;")
            else:
                # currentTime 쿼리가 없는 경우 00:00:00 설정
                start_sec = 0
                self.start_edit.setText("00:00:00")
                self.time_info_label.setText("💡 자동으로 시작 시간을 00:00:00으로 설정합니다")
                self.time_info_label.setStyleSheet("color: #a6e3a1; font-size: 10pt; padding: 5px;")
        except ValueError as e:
            self._show_error(str(e))
            return

        duration = int(self.duration_spin.value())

        try:
            api_client = ChzzkAPIClient(video_id)
            meta = api_client.get_video_meta()
            video_title = meta.get("videoTitle") or meta.get("title") or video_id

            file_manager = FilePathManager()
            output_path = file_manager.build_output_path(
                video_title, start_sec, duration
            )

            if output_path is None:
                safe_title = FilePathManager._sanitize_filename(video_title)
                start_str2 = FilePathManager._format_time(start_sec)
                end_str2 = FilePathManager._format_time(start_sec + duration)
                filename = f"{safe_title}_{start_str2}-{end_str2}.mp4"
                filepath = os.path.join(os.getcwd(), "clips", filename)

                size_mb = 0.0
                if os.path.exists(filepath):
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)

                msg = f"동일한 파일이 이미 있어.\n\n{filepath}"
                if size_mb > 0:
                    msg += f"\n\n파일 크기: {size_mb:.1f} MB"
                self._show_info(msg)
                return

        except Exception as e:
            self._show_error(f"메타데이터 조회 실패: {e}")
            return

        self.progress_bar.setValue(0)
        self.status_label.setText("다운로드 중...")
        self.status_label.setStyleSheet("color: #f9e2af;")
        self.download_btn.setEnabled(False)

        self.worker = DownloadWorker(
            url=clean_url,
            start_sec=start_sec,
            duration=duration,
            output_path=output_path,
            parent=self,
        )
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.finished_ok.connect(self.on_download_finished)
        self.worker.error_occurred.connect(self.on_download_error)
        self.worker.finished.connect(self.on_worker_finished)

        self.worker.start()

    def on_progress_changed(self, percent: int):
        self.progress_bar.setValue(percent)

    def on_download_finished(self, output_path: str):
        self.progress_bar.setValue(0)
        self.status_label.setText("대기 중")
        self.status_label.setStyleSheet("")
        self.time_info_label.setText("")
        
        # URL과 시작 시간 필드 초기화 (길이는 유지)
        self.url_edit.clear()
        self.start_edit.clear()
        
        self._show_info(f"다운로드 완료!\n\n{output_path}")

    def on_download_error(self, err: str):
        self.progress_bar.setValue(0)
        self.status_label.setText("대기 중")
        self.status_label.setStyleSheet("")
        self.time_info_label.setText("")
        self._show_error(f"다운로드 중 오류 발생:\n{err}")

    def on_worker_finished(self):
        self.download_btn.setEnabled(True)


def main():
    logger_cfg = LoggerConfig()
    logger_cfg.setup()
    configure_ffmpeg_path()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()