import sys
import os
import asyncio
import logging
import datetime
import json
import configparser 
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel,
                             QMessageBox, QHBoxLayout, QFrame, QSizePolicy,
                             QDialog, QLineEdit, QTextEdit, QPushButton, QDialogButtonBox) 
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer, QUrl, QStandardPaths
from PyQt5.QtGui import (QFontDatabase, QFont, QPixmap, QPainter, QBrush, QColor, 
                         QDesktopServices, QMouseEvent, QCursor)
import genshin
from qasync import QEventLoop
import aiohttp

DEFAULT_STATIC_AUTH = """
[Auth]
ltuid_v2 = 78247471
account_mid_v2 = 1fsjqpseek_hy
uid_HSR = 800806374
"""
# -------------------------

# -------------------------
DEFAULT_DISPLAY_WINDOW = """
[Display]
Xem hướng dẫn tại đây: "https://1drv.ms/w/c/9891cdb5f4516073/EdbOwX6avOFLr7k9-8wAn0QBkERshlLP9G6BQ8xteK0_4Q?e=m6MJE5
transparency = 0.5
always_on_top = 0
show_in_taskbar = 0
font_size = 20
font_color = #FFFFFF
background_color = #FFBBEE
allow_resizing = 1
draggable = 1
word_wrap = 0
corner_radius = 10
show_background = 1
fit_window_to_text = 1
show_notes = 1
margins = 13
background_image = bg.png
show_ign_uid = 1
show_recovery_time = 1
show_echo_of_war = 1
show_assignments = 1
update_interval_minutes = 1
show_assignment_time = 1

[Window]
# === Đổi key vị trí ===
last_x_hsr = 150
last_y_hsr = 150
last_x_gi = 100
last_y_gi = 100

[Auth]
"""

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
log_level = logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(log_level)
if not logger.hasHandlers():
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False
# --- End Logging Setup ---

def get_appdata_dir():
    try:
        path = os.environ.get('APPDATA')
        if not path:
            home = os.path.expanduser("~")
            path = os.path.join(home, 'AppData','Roaming') if sys.platform=="win32" else \
                   (os.path.join(home,'Library','Application Support') if sys.platform=="darwin" else \
                    os.environ.get('XDG_CONFIG_HOME', os.path.join(home,'.config')))
        widget_dir = os.path.join(path, "Hoyoverse_Widget") 
        os.makedirs(widget_dir, exist_ok=True)
        return widget_dir
    except Exception as e:
        logger.error(f"Lỗi AppData: {e}", exc_info=True)
        return os.path.dirname(os.path.abspath(__file__))

APPDATA_WIDGET_DIR = get_appdata_dir()
CONFIG_FILE_PATH = os.path.join(APPDATA_WIDGET_DIR, 'settings.ini')
LOG_FILE_PATH = os.path.join(APPDATA_WIDGET_DIR, 'widget_Starrail.log') # Log riêng

try:
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        logger.addHandler(file_handler)
        logger.info(f"--- Logger StarRailWidgetApp được cấu hình (Log file: {LOG_FILE_PATH}) ---")
except Exception as e:
    logger.error(f"CRITICAL: Không thể tạo file log {LOG_FILE_PATH}: {e}")

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
        logger.debug(f"MEIPASS: {base_path}")
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
        logger.debug(f"Script Path: {base_path}")

    res_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resource path: {res_path}")
    return res_path

def format_timedelta_hm(delta: datetime.timedelta) -> str:
    """Định dạng timedelta thành HH:MM"""
    if not isinstance(delta, datetime.timedelta) or delta.total_seconds() <= 0:
        return "00:00"
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"

class TokenUpdateDialog(QDialog):
    def __init__(self, current_ltoken, current_cookie_token, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cập nhật Token HoYoLab")
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        self.info_label = QLabel("Cookie/Token đã hết hạn hoặc không hợp lệ.\nVui lòng lấy token mới từ trình duyệt (F12 -> Application -> Cookies -> hoyolab.com) và dán vào ô dưới:")
        self.info_label.setWordWrap(True)

        self.ltoken_label = QLabel("ltoken_v2:")
        self.ltoken_input = QTextEdit()
        self.ltoken_input.setPlaceholderText("Dán ltoken_v2 vào đây")
        self.ltoken_input.setText(current_ltoken or "")
        self.ltoken_input.setFixedHeight(60)
        self.ltoken_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.cookie_token_label = QLabel("cookie_token_v2:")
        self.cookie_token_input = QTextEdit()
        self.cookie_token_input.setPlaceholderText("Dán cookie_token_v2 vào đây")
        self.cookie_token_input.setText(current_cookie_token or "")
        self.cookie_token_input.setFixedHeight(60)
        self.cookie_token_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout.addWidget(self.info_label)
        layout.addWidget(self.ltoken_label)
        layout.addWidget(self.ltoken_input)
        layout.addWidget(self.cookie_token_label)
        layout.addWidget(self.cookie_token_input)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)

        self.new_ltoken = None
        self.new_cookie_token = None

    def accept(self):
        self.new_ltoken = self.ltoken_input.toPlainText().strip()
        self.new_cookie_token = self.cookie_token_input.toPlainText().strip()

        if not self.new_ltoken or not self.new_cookie_token:
            self.error_label.setText("Vui lòng nhập đủ 2 token.")
            return
        super().accept()

    def getTokens(self):
        if self.result() == QDialog.Accepted:
            return (self.new_ltoken, self.new_cookie_token)
        else:
            return (None, None)

def create_default_config_file():
    logger.info(f"Tạo file config mặc định: {CONFIG_FILE_PATH}")
    config_to_write = configparser.ConfigParser()
    try:
        config_to_write.read_string(DEFAULT_DISPLAY_WINDOW)
        
        
        config_to_write.set('Auth', 'ltoken_v2', 'PASTE TOKEN HERE')
        config_to_write.set('Auth', 'cookie_token_v2', 'PASTE TOKEN HERE')
        
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            config_to_write.write(f)
            
        logger.info("Đã tạo file config AppData thành công.")
        logger.warning("!!! Yêu cầu điền token vào settings.ini AppData !!!")
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi tạo default config file: {e}", exc_info=True)

def get_config():
    logger.debug("Bắt đầu get_config()")
    config = configparser.ConfigParser()
    try:
        config.read_string(DEFAULT_STATIC_AUTH)
        logger.info("Đã đọc Auth cố định.")

        default_dw_parser = configparser.ConfigParser()
        default_dw_parser.read_string(DEFAULT_DISPLAY_WINDOW)
        if default_dw_parser.has_section('Display'):
            config['Display'] = default_dw_parser['Display']
        if default_dw_parser.has_section('Window'):
            config['Window'] = default_dw_parser['Window']
        logger.debug("Đã nạp Display/Window mặc định.")

        if os.path.exists(CONFIG_FILE_PATH):
            logger.info(f"Đọc config từ AppData: {CONFIG_FILE_PATH}")
            appdata_cfg = configparser.ConfigParser()
            if appdata_cfg.read(CONFIG_FILE_PATH, encoding='utf-8'):
                for sec in ['Display', 'Window']:
                    if appdata_cfg.has_section(sec):
                        if not config.has_section(sec): config.add_section(sec)
                        for key, val in appdata_cfg[sec].items():
                            config[sec][key] = val
                        logger.info(f"Đã áp dụng [{sec}] từ AppData.")

                if appdata_cfg.has_section('Auth'):
                    ltoken = appdata_cfg.get('Auth', 'ltoken_v2', fallback=None)
                    cookie_token = appdata_cfg.get('Auth', 'cookie_token_v2', fallback=None)
                    if ltoken and not ltoken.startswith('#'):
                        config.set('Auth', 'ltoken_v2', ltoken)
                    else:
                        logger.warning("ltoken_v2 thiếu/không hợp lệ trong AppData.")
                    if cookie_token and not cookie_token.startswith('#'):
                        config.set('Auth', 'cookie_token_v2', cookie_token)
                    else:
                        logger.warning("cookie_token_v2 thiếu/không hợp lệ trong AppData.")
                    logger.info("Đã đọc token động từ AppData (nếu có).")
                else:
                    logger.warning("Không tìm thấy section [Auth] trong AppData.")
            else:
                logger.warning(f"File AppData lỗi: {CONFIG_FILE_PATH}. Tạo lại.")
                create_default_config_file()
        else:
            logger.info(f"Không tìm thấy file AppData. Tạo file mới.")
            create_default_config_file()

        if not config.has_option('Auth', 'ltoken_v2') or not config.has_option('Auth', 'cookie_token_v2'):
             logger.error("Thiếu token động (ltoken_v2 hoặc cookie_token_v2) sau khi load config!")
        elif config.get('Auth', 'ltoken_v2', fallback='').startswith('#') or config.get('Auth', 'cookie_token_v2', fallback='').startswith('#'):
             logger.warning("Token động vẫn là placeholder. Vui lòng cập nhật file settings.ini trong AppData.")

    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi load config: {e}", exc_info=True)
        config = configparser.ConfigParser()
        config.read_string(DEFAULT_STATIC_AUTH)
        logger.warning("Sử dụng Auth cố định do lỗi load config.")

    logger.debug("get_config() hoàn thành.")
    return config

def save_dynamic_tokens(ltoken: str, cookie_token: str) -> bool:
    """Lưu chỉ token động vào file config AppData."""
    logger.info("Lưu token động vào AppData...")
    config_to_save = configparser.ConfigParser()
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            config_to_save.read(CONFIG_FILE_PATH, encoding='utf-8')
        else:
            default_dw_parser = configparser.ConfigParser()
            default_dw_parser.read_string(DEFAULT_DISPLAY_WINDOW)
            config_to_save.read_dict(default_dw_parser) # Sao chép cấu trúc

        if not config_to_save.has_section('Auth'):
            config_to_save.add_section('Auth')

        config_to_save.set('Auth', 'ltoken_v2', ltoken if ltoken else '')
        config_to_save.set('Auth', 'cookie_token_v2', cookie_token if cookie_token else '')


        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            config_to_save.write(f)
        logger.info(f"Đã lưu token động vào: {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Lỗi lưu token động: {e}", exc_info=True)
        return False

def save_settings_to_appdata(config_runtime: configparser.ConfigParser, game_type: str, x: int, y: int):
    """Lưu Display và Window (vị trí) vào file AppData."""
    logger.debug(f"Lưu settings {game_type} ({x},{y}) vào AppData...")
    config_to_save = configparser.ConfigParser()
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            config_to_save.read(CONFIG_FILE_PATH, encoding='utf-8')

        if config_runtime.has_section('Display'):
            if not config_to_save.has_section('Display'): config_to_save.add_section('Display')
            config_to_save['Display'] = config_runtime['Display'] # Ghi đè hoàn toàn
        elif config_to_save.has_section('Display'):
            config_to_save.remove_section('Display')

        if not config_to_save.has_section('Window'): config_to_save.add_section('Window')
        config_to_save.set('Window', f'last_x_{game_type}', str(x))
        config_to_save.set('Window', f'last_y_{game_type}', str(y))

        os.makedirs(APPDATA_WIDGET_DIR, exist_ok=True) # Đảm bảo thư mục tồn tại
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            config_to_save.write(f)
        logger.info(f"Đã lưu Display/Window vào: {CONFIG_FILE_PATH}")
    except Exception as e:
        logger.error(f"Lỗi save_settings_to_appdata: {e}", exc_info=True)

# --- End Config Functions ---


class ClickableFrame(QFrame):
    """Một QFrame có thể click để mở URL."""
    clicked = pyqtSignal(QUrl)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url = QUrl()
        self.setCursor(Qt.PointingHandCursor) 

    def setUrl(self, url_str):
        self._url = QUrl(url_str)

    def url(self):
        return self._url

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self._url.isEmpty():
            event.accept() 
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self._url.isEmpty():
            if (event.pos() - event.buttonDownPos(Qt.LeftButton)).manhattanLength() < QApplication.startDragDistance():
                logger.info(f"Mở URL: {self._url.toString()}")
                QDesktopServices.openUrl(self._url)
                self.clicked.emit(self._url)
                event.accept()
            else:
                super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)


class BackgroundFrame(QFrame):
    """Một QFrame tùy chỉnh để vẽ ảnh nền."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background_pixmap = None

    def setBackgroundImage(self, image_path):
        """Đặt ảnh nền từ đường dẫn file."""
        if image_path and os.path.exists(image_path):
            self.background_pixmap = QPixmap(image_path)
            logger.debug(f"Đã tải ảnh nền: {image_path}")
        else:
            self.background_pixmap = None
            if image_path:
                logger.warning(f"Không tìm thấy ảnh nền: {image_path}")
        self.update() 



    def paintEvent(self, event):
        """Vẽ lại widget, bao gồm cả ảnh nền nếu có."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.background_pixmap and not self.background_pixmap.isNull():
            scaled_pixmap = self.background_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # Căn giữa ảnh đã scale
            x = (self.width() - scaled_pixmap.width()) / 2
            y = (self.height() - scaled_pixmap.height()) / 2
            painter.drawPixmap(QPoint(int(x), int(y)), scaled_pixmap)
        else:
            pass

        painter.end()


# --- Main Widget Class ---
class StarRailApp(QWidget):
    def __init__(self):
        logger.debug("StarRailApp __init__.")
        super().__init__()
        try:
            self.config = get_config()
        except Exception as e:
            logger.critical(f"Lỗi nghiêm trọng khi load config ban đầu: {e}", exc_info=True)
            QMessageBox.critical(None, "Lỗi Config", f"Không thể load config:\n{e}\nVui lòng kiểm tra file 'settings.ini' trong thư mục AppData và file log.")
            sys.exit(1)

        self.client = None
        self.custom_font = QFont()
        self.uid = None
        self.timer = None
        self.ign = "Đang tải..."
        self.level = "N/A"
        # HSR không cần region
        self.shutting_down_due_to_auth_error = False

        self.is_draggable = True 
        self.dragPos = QPoint()

        try:
            self.initUI()
            self.oldPos = self.pos()
            logger.debug("StarRailApp __init__ OK.")
        except SystemExit:
             raise
        except Exception as e:
             logger.critical(f"Lỗi không mong muốn trong __init__: {e}", exc_info=True)
             self.show_warning(f"Gặp lỗi không mong muốn khi khởi tạo:\n{e}")
             sys.exit(1)


    def initUI(self):
        logger.debug("Bắt đầu initUI (StarRail)")
        try:
            display_config = self.config['Display']
            auth_config = self.config['Auth']
            window_config = self.config['Window']

            logger.debug("Kiểm tra Auth/UID (StarRail)...")

            try:
                uid_str = auth_config.get('uid_HSR')
                if not uid_str: raise ValueError("Thiếu key 'uid_HSR' trong section [Auth]")
                self.uid = int(uid_str)
                logger.info(f"HSR UID: {self.uid}")
            except (ValueError, TypeError) as e:
                err_msg = f"Lỗi định dạng uid_HSR trong section [Auth]: {e}. Giá trị phải là một số nguyên."
                logger.critical(err_msg, exc_info=True)
                self.show_warning(err_msg)
                sys.exit(1)

            logger.debug("Đọc config Display/Window...")
            try:
                self.word_wrap = self.bool_from_str(display_config.get('word_wrap','0'))
                self.fit_window_to_text = self.bool_from_str(display_config.get('fit_window_to_text','1'))
                show_taskbar = self.bool_from_str(display_config.get('show_in_taskbar','0'))
                on_top = self.bool_from_str(display_config.get('always_on_top','0'))
                allow_resize = self.bool_from_str(display_config.get('allow_resizing','1'))
                self.is_draggable = self.bool_from_str(display_config.get('draggable','1'))
                show_title = not self.bool_from_str(display_config.get('hide_title_bar','1'))
                trans = float(display_config.get('transparency','0.8'))
                lx = window_config.getint('last_x_HSR', 150)
                ly = window_config.getint('last_y_HSR', 150)
                self.margins = display_config.getint('margins', 10)
                self.font_size = display_config.getint('font_size', 12)
                self.font_color = display_config.get('font_color', '#FFFFFF')
                self.show_bg = self.bool_from_str(display_config.get('show_background', '1'))
                self.bg_color = display_config.get('background_color', 'rgba(20, 30, 50, 0.8)')
                self.bg_img = display_config.get('background_image', '')
                self.radius = display_config.getint('corner_radius', 10)
                self.interval = max(1, display_config.getint('update_interval_minutes', 5))
                self.font_path = display_config.get("font_file", "zh-cn.ttf")
                self.icon_width = display_config.getint('icon_width', 35)
            except (ValueError, TypeError) as e:
                err_msg = f"Lỗi giá trị trong config Display/Window: {e}"
                logger.critical(err_msg, exc_info=True)
                self.show_warning(err_msg + "\nVui lòng kiểm tra file settings.ini.")
                sys.exit(1)

            if self.word_wrap and self.fit_window_to_text:
                err_msg="Cấu hình 'word_wrap=1' và 'fit_window_to_text=1' xung đột. Vui lòng chọn một."
                logger.critical(err_msg)
                self.show_warning(err_msg)
                sys.exit(1)

            logger.debug("Cài đặt cửa sổ...")
            flags = Qt.Window
            if not show_taskbar: flags |= Qt.Tool
            if not show_title: flags |= Qt.FramelessWindowHint # Chỉ ẩn title bar nếu không hiện taskbar
            if on_top: flags |= Qt.WindowStaysOnTopHint

            self.setWindowFlags(flags)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setWindowOpacity(trans if self.show_bg else 1.0)
            self.move(lx, ly)

            logger.debug("Thiết lập layout...")
            self.main_layout = QVBoxLayout(self)
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.bg_frame = BackgroundFrame()
            self.main_layout.addWidget(self.bg_frame)
            self.content_layout = QVBoxLayout(self.bg_frame)
            self.content_layout.setContentsMargins(self.margins, self.margins, self.margins, self.margins)

            logger.debug("Tải font...")
            font_abs_path = resource_path(self.font_path)
            if os.path.exists(font_abs_path):
                font_id = QFontDatabase.addApplicationFont(font_abs_path)
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        self.custom_font = QFont(families[0], self.font_size)
                        logger.info(f"Đã tải font: {families[0]} ({font_abs_path})")
                    else:
                        logger.error(f"Không tìm thấy font family trong file: {font_abs_path}")
                        self.custom_font.setPointSize(self.font_size)
                else:
                    logger.error(f"Lỗi khi thêm font ứng dụng: {font_abs_path}. Sử dụng font mặc định.")
                    self.custom_font.setPointSize(self.font_size)
            else:
                logger.warning(f"Không tìm thấy file font: {font_abs_path}. Sử dụng font mặc định.")
                self.custom_font.setPointSize(self.font_size)

            # --- Khởi tạo Client Genshin ---
            logger.debug("Khởi tạo Client Genshin...")
            try:
                self.client = genshin.Client()
                self.set_cookies(auth_config)
                logger.info("Client Genshin và Cookies OK.")
            except (ValueError, RuntimeError) as e:
                logger.error(f"Lỗi Client/Cookie ban đầu: {e}")
            except Exception as e:
                logger.critical(f"Lỗi không xác định khi khởi tạo Client: {e}", exc_info=True)
                self.show_warning(f"Lỗi không xác định khi khởi tạo Client:\n{e}")
                sys.exit(1)
            self.apply_styles()

            # --- Thiết lập kích thước cửa sổ ---
            logger.debug("Thiết lập kích thước...")
            if not allow_resize:
                 if not self.fit_window_to_text:
                    try:
                        w = self.config.getint('Display', 'window_width', fallback=250)
                        h = self.config.getint('Display', 'window_height', fallback=160)
                        self.setFixedSize(w, h)
                        logger.debug(f"Kích thước cố định: {w}x{h}")
                    except (ValueError, TypeError):
                        logger.warning("Lỗi đọc window_width/height, đặt kích thước cố định 250x160.")
                        self.setFixedSize(250, 160)
                 else:
                    logger.debug("Kích thước sẽ tự điều chỉnh theo nội dung (fit_window_to_text=1).")
                    self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
            else:
                try:
                    w = self.config.getint('Display', 'window_width', fallback=300)
                    h = self.config.getint('Display', 'window_height', fallback=190)
                    self.resize(w, h)
                    logger.debug(f"Kích thước ban đầu (cho phép resize): {w}x{h}")
                except (ValueError, TypeError):
                    logger.warning("Lỗi đọc window_width/height, đặt kích thước ban đầu 300x190.")
                    self.resize(300, 190)
                if self.fit_window_to_text:
                    logger.warning("allow_resizing=1 và fit_window_to_text=1 có thể hoạt động không như mong đợi. Ưu tiên fit_window_to_text.")


            # --- Bắt đầu cập nhật và hẹn giờ ---
            asyncio.ensure_future(self.update_info()) 
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.trigger_update_info)
            self.timer.start(self.interval * 60 * 1000) # Miligiây
            logger.info(f"Hẹn giờ cập nhật mỗi {self.interval} phút.")

            logger.debug("initUI (StarRail) hoàn thành.")

        except SystemExit:
            logger.info("initUI bị dừng bởi SystemExit.")
            raise
        except Exception as e:
            logger.critical(f"Lỗi nghiêm trọng trong initUI (StarRail): {e}", exc_info=True)
            self.show_warning(f"Lỗi nghiêm trọng khi khởi tạo giao diện:\n{e}\nVui lòng kiểm tra log.")
            try: QApplication.instance().quit()
            except: pass
            sys.exit(1)

    def apply_styles(self):
        logger.debug("Apply styles...")
        if not self.config: return
        try: 
            style=f""" * {{ color:{self.font_color};font-size:{self.font_size}px;background:transparent;}} BackgroundFrame {{ border-radius:{self.radius}px;background:{'transparent' if self.bg_img and self.show_bg else self.bg_color};}} """; self.setStyleSheet(style)
            bg_img_abs_path = resource_path(self.bg_img) if self.bg_img else ''; (self.bg_frame.setBackgroundImage(bg_img_abs_path) if self.show_bg and bg_img_abs_path and os.path.exists(bg_img_abs_path) else self.bg_frame.setBackgroundImage(None))
        except Exception as e: logger.error(f"Lỗi apply_styles: {e}", exc_info=True)
        
    def bool_from_str(self, value): return str(value).strip() == '1'
    def set_cookies(self, auth_config):
        logger.debug("Set cookies...")
        if not self.client: raise RuntimeError("Client null.")
        try:
            cookies={k:auth_config.get(k) for k in ['ltuid_v2','ltoken_v2','cookie_token_v2','account_mid_v2']}; assert None not in cookies.values(), ""
            self.client.set_cookies(cookies); logger.info(f"Cookies OK.")
        except Exception as e: logger.error(f"Lỗi set_cookies: {e}"); raise RuntimeError(f"{e}") from e
    def trigger_update_info(self): logger.debug("Timer triggered."); asyncio.ensure_future(self.update_info())
    async def update_info(self):
        logger.debug("Bắt đầu update_info (StarRail).")
        if self.uid is None: logger.error("UID null."); return
        ign_uid_level_text = f"{self.ign} UID: {self.uid} Lv: {self.level}"; stamina_text = "Sức Mạnh Khai Phá: Lỗi"; training_text = "Huấn Luyện Hằng Ngày: Lỗi"; assignment_text = "Ủy Thác: Lỗi"; echo_war_text = "Dư Âm Chiến Đấu: Lỗi"
        if self.ign == "Đang tải...":
             logger.info(f"Lần đầu, lấy IGN/Level..."); api_url = "https://api-account-os.hoyoverse.com/account/binding/api/getUserGameRolesByCookieToken"; 
             try:
                 auth_conf = self.config['Auth']; cookie_str=f"ltuid_v2={auth_conf.get('ltuid_v2')}; ltoken_v2={auth_conf.get('ltoken_v2')}; cookie_token_v2={auth_conf.get('cookie_token_v2')}; account_mid_v2={auth_conf.get('account_mid_v2')};"; headers = {'Cookie': cookie_str, 'User-Agent': 'Mozilla/5.0'}
                 async with aiohttp.ClientSession(headers=headers) as session:
                     async with session.get(api_url, timeout=10) as resp:
                         resp.raise_for_status(); data = await resp.json()
                         if data.get("retcode") == 0:
                             accs = data.get("data", {}).get("list", []); found = False
                             for acc in accs:
                                 if acc.get("game_biz") == "hkrpg_global" and str(acc.get("game_uid")) == str(self.uid):
                                     self.ign=acc.get('nickname','(Ko tên)'); self.level=acc.get('level','N/A'); logger.info(f"IGN/Level OK: {self.ign} Lv:{self.level}"); found=True; break
                             if not found: logger.warning(f"Ko tìm thấy HSR UID {self.uid}."); self.ign="(Ko thấy)"
                         else: logger.error(f"API IGN lỗi: {data.get('retcode')} {data.get('message')}"); self.ign="(Lỗi API)"
             except Exception as e: logger.error(f"Lỗi lấy IGN/Level: {e}", exc_info=True); self.ign="(Lỗi IGN)"
             ign_uid_level_text = f"{self.ign} UID: {self.uid} Lv: {self.level}"
        if not self.client: logger.error("Client null."); return
        try:
            logger.info(f"Gọi API get_starrail_notes...")
            notes = await self.client.get_starrail_notes(self.uid)
            if notes:
                logger.info(f"API Notes HSR OK"); stamina_num = f"{notes.current_stamina}/{notes.max_stamina}"; stamina_time_str = "??:?"
                if notes.current_stamina >= notes.max_stamina: stamina_time_str = "Đầy"
                elif isinstance(notes.stamina_recover_time, datetime.timedelta):
                    if notes.stamina_recover_time.total_seconds() > 1: stamina_time_str = format_timedelta_hm(notes.stamina_recover_time)
                    else: stamina_time_str = "<1m"
                else: logger.warning(f"Loại stamina_recover_time lạ: {type(notes.stamina_recover_time)}"); stamina_time_str = "Lỗi"
                stamina_text = f"Sức Mạnh Khai Phá: {stamina_num} ({stamina_time_str})"
                training_text = f"Huấn Luyện Hằng Ngày: {notes.current_train_score}/{notes.max_train_score}"
                assign_num = f"{notes.accepted_expedition_num}/{notes.total_expedition_num}"; assign_time_str = "??:??"
                if notes.expeditions:
                    try:
                        ongoing=[e.remaining_time for e in notes.expeditions if e.status=="Ongoing" and isinstance(e.remaining_time,datetime.timedelta) and e.remaining_time.total_seconds()>0]
                        if ongoing: min_t_delta = min(ongoing); assign_time_str=format_timedelta_hm(min_t_delta)
                        else: assign_time_str = "Xong"
                    except Exception as e: logger.warning(f"Lỗi tính assignment time HSR: {e}"); assign_time_str = "Lỗi"
                else: assign_time_str = "00:00"
                assignment_text = f"Ủy Thác: {assign_num} ({assign_time_str})"
                echo_war_text = f"Dư Âm Chiến Đấu: {notes.remaining_weekly_discounts}/{notes.max_weekly_discounts}"
            else: logger.warning("API get_starrail_notes trả về None.")
        except (genshin.errors.InvalidCookies, genshin.errors.AccountNotFound) as e:
            logger.error(f"Lỗi Cookie/TK: {e}")
            self.shutting_down_due_to_auth_error = True
            auth_error = True
            resin_text = "Lỗi: Cookie/TK sai"
            commission_text = " "
            realm_text = " "
            expedition_text = " "

            # Thông báo lỗi
            try:
                QMessageBox.critical(self, "Lỗi xác thực", 
                    "Thông tin tài khoản đã hết hạn.\nVui lòng cập nhật Token và khởi động lại Widget.")
            except Exception as msg_err:
                logger.error(f"Lỗi hiển thị QMessageBox: {msg_err}")
            try:
                settings_path = CONFIG_FILE_PATH.replace("/", "\\")
                os.system(f'start notepad "{settings_path}"')
                logger.info(f"Đã mở Notepad: {settings_path}")
            except Exception as open_err:
                logger.error(f"Lỗi mở Notepad: {open_err}")

            # Thoát chương trình (không tắt Notepad)
            QTimer.singleShot(500, lambda: QApplication.quit())
        except genshin.errors.AccountNotFound: logger.error(f"API Lỗi: Không tìm thấy TK HSR/Cookie sai."); stamina_text="Lỗi: Không tìm thấy TK"
        except genshin.errors.InvalidCookies: logger.error("API Lỗi: Cookie không hợp lệ."); stamina_text="Lỗi: Cookie sai"
        except genshin.errors.GenshinException as e: logger.error(f"API Lỗi (HSR): {e}", exc_info=True); stamina_text=f"Lỗi API ({getattr(e, 'retcode', '?')})"
        except asyncio.TimeoutError: logger.error("API Lỗi: Timeout."); stamina_text = "Lỗi: Timeout"
        except Exception as e: logger.error(f"Lỗi update_info (notes): {e}", exc_info=True); stamina_text = f"Lỗi..."
        finally:
            logger.debug("Scheduling update_ui...")
            try: QTimer.singleShot(0, lambda ignuidlv=ign_uid_level_text, stam=stamina_text, train=training_text, assign=assignment_text, echo=echo_war_text: self.update_ui(ignuidlv, stam, train, assign, echo))
            except Exception as e: logger.error(f"Lỗi QTimer.singleShot: {e}", exc_info=True)
        logger.debug("update_info hoàn thành.")

    def update_ui(self, ign_uid_level_info, stamina_info, training_info, assignment_info, echo_war_info):
        logger.debug(f"Bắt đầu update_ui (StarRail)...")
        try:
            logger.debug("Xóa widget cũ...")
            while self.content_layout.count(): item=self.content_layout.takeAt(0); w=item.widget(); l=item.layout(); (w.deleteLater() if w else (self.clear_layout(l) if l else None))
            def create_row_layout(icon_name, text):
                layout = QHBoxLayout(); layout.setContentsMargins(0,0,0,0); icon_label = QLabel(); icon_label.setFixedWidth(self.icon_width); icon_label.setAlignment(Qt.AlignCenter); text_label = QLabel(text)
                icon_folder = resource_path("Icon")
                icon_path = os.path.join(icon_folder, f"{icon_name}.png")
                icon_size = self.font_size + 4
                if os.path.exists(icon_path): pixmap = QPixmap(icon_path).scaledToHeight(icon_size, Qt.SmoothTransformation); (icon_label.setPixmap(pixmap) if not pixmap.isNull() else logger.warning(f"Icon null: {icon_path}"))
                else: logger.warning(f"Icon miss: {icon_path}"); icon_label.setText("?")
                text_label.setFont(self.custom_font); text_label.setWordWrap(self.word_wrap); layout.addWidget(icon_label); layout.addWidget(text_label, 1); return layout
            info_frame = ClickableFrame(); info_layout = create_row_layout("user_HSR", ign_uid_level_info);
            info_frame.setLayout(info_layout)
            bc_url = f"https://act.hoyolab.com/app/community-game-records-sea/index.html?role_id={self.uid}&server=prod_official_asia#/hsr"; info_frame.setUrl(bc_url); info_frame.setToolTip("Mở Battle Chronicle (HSR)")
            self.content_layout.addWidget(info_frame)
            stamina_layout = create_row_layout("trailblaze_power", stamina_info); self.content_layout.addLayout(stamina_layout)
            training_frame = ClickableFrame(); training_layout = create_row_layout("daily_training", training_info); training_frame.setLayout(training_layout)
            checkin_url = "https://act.hoyolab.com/bbs/event/signin/hkrpg/index.html?act_id=e202303301540311"; training_frame.setUrl(checkin_url); training_frame.setToolTip("Mở Điểm danh hàng ngày (HSR)")
            self.content_layout.addWidget(training_frame)
            assignment_layout = create_row_layout("assignment", assignment_info); self.content_layout.addLayout(assignment_layout)
            echo_war_layout = create_row_layout("echo_of_war", echo_war_info); self.content_layout.addLayout(echo_war_layout)
            self.content_layout.addStretch(1)
            if self.fit_window_to_text: logger.debug("fit_window_to_text=1."); QTimer.singleShot(50, self.adjustSize)
        except Exception as e: logger.error(f"Lỗi update_ui: {e}", exc_info=True)
        logger.debug("update_ui hoàn thành.")


    # --- Các hàm còn lại ---
    def clear_layout(self, layout):
        if layout:
            while layout.count(): item=layout.takeAt(0); w=item.widget(); l=item.layout(); (w.deleteLater() if w else (self.clear_layout(l) if l else None))
    def show_warning(self, message):
        logger.warning(f"Cảnh báo: {message}")
        try: msg=QMessageBox(); msg.setIcon(QMessageBox.Warning); msg.setText(message); msg.setWindowTitle("Cảnh Báo"); msg.exec_()
        except Exception as e: logger.error(f"Lỗi show_warning: {e}"); print(f"WARNING: {message}")
    def mousePressEvent(self, e:QMouseEvent):
        try:
            if self.is_draggable and not(self.windowFlags()&Qt.WindowTitleHint) and e.button()==Qt.LeftButton: self.dragPos=e.globalPos()-self.frameGeometry().topLeft(); e.accept()
            else: super().mousePressEvent(e)
        except Exception as err: logger.error(f"Lỗi mousePress: {err}"); super().mousePressEvent(e)
    def mouseMoveEvent(self, e:QMouseEvent):
        try:
            if self.is_draggable and not(self.windowFlags()&Qt.WindowTitleHint) and e.buttons()==Qt.LeftButton: self.move(e.globalPos()-self.dragPos); e.accept()
            else: super().mouseMoveEvent(e)
        except Exception as err: logger.error(f"Lỗi mouseMove: {err}"); super().mouseMoveEvent(e)
    def mouseReleaseEvent(self, e:QMouseEvent):
         try:
             if self.is_draggable and not(self.windowFlags()&Qt.WindowTitleHint) and e.button()==Qt.LeftButton:
                 logger.debug("Kéo xong, lưu vị trí (StarRail).")
                 save_settings_to_appdata(self.config, "HSR", self.x(), self.y())

             super().mouseReleaseEvent(e)
         except Exception as err: logger.error(f"Lỗi mouseRelease: {err}"); super().mouseReleaseEvent(e)

    def closeEvent(self, event):
        logger.info("closeEvent (StarRail)...")
        if not self.shutting_down_due_to_auth_error:
            save_settings_to_appdata(self.config, "HSR", self.x(), self.y())
        event.accept()
        logger.info("closeEvent OK (StarRail).")

if __name__ == '__main__':
    logger.info("--- Bắt đầu __main__ (StarRail) ---")
    app, loop, window = None, None, None; exit_code = 0
    try:
        try:
            if hasattr(Qt,'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True)
            if hasattr(Qt,'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
        except: pass
        app = QApplication(sys.argv)
        loop = QEventLoop(app); asyncio.set_event_loop(loop)
        with loop:
            window = StarRailApp()
            window.show()
            logger.info("Chạy event loop (StarRail)...")
            loop.run_forever()
    except KeyboardInterrupt: logger.info("Đã nhận Ctrl+C (StarRail).")
    except SystemExit as e: logger.info(f"Thoát (StarRail) với mã: {e.code}"); exit_code = e.code
    except Exception as e:
         logger.critical(f"Lỗi __main__ (StarRail): {e}", exc_info=True)
         try: QMessageBox.critical(None,"Lỗi Widget StarRail", f"Lỗi nghiêm trọng:\n{e}\nXem log.")
         except: pass
         exit_code = 1
    finally:
        logger.info(f"--- Kết thúc Widget StarRail (mã: {exit_code}) ---")
        if loop and loop.is_running(): loop.stop()
        sys.exit(exit_code)