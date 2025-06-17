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
from PyQt5.QtGui import (QFontDatabase, QFont, QPixmap, QPainter, QBrush,
                         QDesktopServices, QMouseEvent, QCursor)
import genshin
from qasync import QEventLoop
import aiohttp


DEFAULT_STATIC_AUTH = """
[Auth]
ltuid_v2 = 78247471
account_mid_v2 = 1fsjqpseek_hy
uid_GI = 813137911
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
last_x_GI = 100
last_y_GI = 100
last_x_hsr = 150
last_y_hsr = 150

[Auth]
"""
# ----------------------------------

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
log_level = logging.INFO
logger = logging.getLogger(__name__)
logger.setLevel(log_level)
if not logger.hasHandlers():
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)
    logger.propagate = False

def get_appdata_dir():
    try:
        path = os.environ.get('APPDATA');
        if not path: home = os.path.expanduser("~"); path = os.path.join(home, 'AppData','Roaming') if sys.platform=="win32" else (os.path.join(home,'Library','Application Support') if sys.platform=="darwin" else os.environ.get('XDG_CONFIG_HOME', os.path.join(home,'.config')))
        widget_dir = os.path.join(path, "Hoyoverse_Widget");
        os.makedirs(widget_dir, exist_ok=True); return widget_dir
    except Exception as e: logger.error(f"Lỗi AppData: {e}", exc_info=True); return os.path.dirname(os.path.abspath(__file__))

APPDATA_WIDGET_DIR = get_appdata_dir()
CONFIG_FILE_PATH = os.path.join(APPDATA_WIDGET_DIR, 'settings.ini')
LOG_FILE_PATH = os.path.join(APPDATA_WIDGET_DIR, 'widget_Genshin.log')

try:
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        logger.addHandler(file_handler)
        logger.info(f"--- Logger GenshinWidgetApp được cấu hình (Log file: {LOG_FILE_PATH}) ---")
except Exception as e: logger.error(f"CRITICAL: Không thể tạo file log {LOG_FILE_PATH}: {e}")

def resource_path(relative_path):
    try: base_path = sys._MEIPASS; logger.debug(f"MEIPASS: {base_path}")
    except Exception: base_path = os.path.abspath(os.path.dirname(__file__)); logger.debug(f"Script Path: {base_path}")
    res_path = os.path.join(base_path, relative_path); logger.debug(f"Resource path: {res_path}")
    return res_path

def format_timedelta_hm(delta: datetime.timedelta) -> str:
    if not isinstance(delta, datetime.timedelta) or delta.total_seconds() <= 0: return "00:00"
    total_seconds = max(0, int(delta.total_seconds())); hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60); return f"{hours:02d}:{minutes:02d}"

class TokenUpdateDialog(QDialog):
    def __init__(self, current_ltoken, current_cookie_token, parent=None):
        super().__init__(parent); self.setWindowTitle("Cập nhật Token HoYoLab"); self.setModal(True); self.setMinimumWidth(450)
        layout=QVBoxLayout(self)
        self.info_label=QLabel("Cookie/Token đã hết hạn hoặc không hợp lệ.\nVui lòng lấy token mới từ trình duyệt (F12 -> Application -> Cookies -> hoyolab.com) và dán vào ô dưới:"); self.info_label.setWordWrap(True)
        self.ltoken_label=QLabel("ltoken_v2:"); self.ltoken_input=QTextEdit(); self.ltoken_input.setPlaceholderText("Dán ltoken_v2 vào đây"); self.ltoken_input.setText(current_ltoken or ""); self.ltoken_input.setFixedHeight(60); self.ltoken_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.cookie_token_label=QLabel("cookie_token_v2:"); self.cookie_token_input=QTextEdit(); self.cookie_token_input.setPlaceholderText("Dán cookie_token_v2 vào đây"); self.cookie_token_input.setText(current_cookie_token or ""); self.cookie_token_input.setFixedHeight(60); self.cookie_token_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.error_label=QLabel(""); self.error_label.setStyleSheet("color: red;"); self.error_label.setWordWrap(True)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.info_label); layout.addWidget(self.ltoken_label); layout.addWidget(self.ltoken_input); layout.addWidget(self.cookie_token_label); layout.addWidget(self.cookie_token_input); layout.addWidget(self.error_label); layout.addWidget(self.buttons)
        self.new_ltoken = None; self.new_cookie_token = None
    def accept(self):
        self.new_ltoken = self.ltoken_input.toPlainText().strip(); self.new_cookie_token = self.cookie_token_input.toPlainText().strip()
        if not self.new_ltoken or not self.new_cookie_token: self.error_label.setText("Vui lòng nhập đủ 2 token."); return
        if not self.new_ltoken.startswith("v2_") or not self.new_cookie_token.startswith("v2_"): self.error_label.setText("Định dạng token không đúng (thường bắt đầu 'v2_')."); return
        super().accept()
    def getTokens(self): return (self.new_ltoken, self.new_cookie_token) if self.result() == QDialog.Accepted else (None, None)

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
        logger.warning("!!! Yêu cầu người dùng điền token vào settings.ini trong AppData !!!")
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng khi tạo default config file: {e}", exc_info=True)

def get_config():
    logger.debug("Bắt đầu get_config()")
    config = configparser.ConfigParser()
    try:
        config.read_string(DEFAULT_STATIC_AUTH); logger.info("Đã đọc Auth cố định.")
        default_dw_parser = configparser.ConfigParser(); default_dw_parser.read_string(DEFAULT_DISPLAY_WINDOW)
        if default_dw_parser.has_section('Display'): config['Display'] = default_dw_parser['Display']
        if default_dw_parser.has_section('Window'): config['Window'] = default_dw_parser['Window']
        logger.debug("Đã nạp Display/Window mặc định.")
        if os.path.exists(CONFIG_FILE_PATH):
            logger.info(f"Đọc config từ AppData: {CONFIG_FILE_PATH}")
            appdata_cfg = configparser.ConfigParser()
            if appdata_cfg.read(CONFIG_FILE_PATH, encoding='utf-8'):
                for sec in ['Display', 'Window']:
                    if appdata_cfg.has_section(sec):
                        if not config.has_section(sec): config.add_section(sec)
                        for key, val in appdata_cfg[sec].items(): config[sec][key] = val
                        logger.info(f"Đã áp dụng [{sec}] từ AppData.")
                if appdata_cfg.has_section('Auth'):
                    ltoken = appdata_cfg.get('Auth', 'ltoken_v2', fallback=None)
                    cookie_token = appdata_cfg.get('Auth', 'cookie_token_v2', fallback=None)
                    if ltoken and not ltoken.startswith('#'): config.set('Auth', 'ltoken_v2', ltoken)
                    else: logger.warning("ltoken_v2 thiếu/không hợp lệ trong AppData.")
                    if cookie_token and not cookie_token.startswith('#'): config.set('Auth', 'cookie_token_v2', cookie_token)
                    else: logger.warning("cookie_token_v2 thiếu/không hợp lệ trong AppData.")
                    logger.info("Đã đọc token động từ AppData (nếu có).")
                else: logger.warning("Không tìm thấy section [Auth] trong AppData.")
            else: logger.warning(f"File AppData lỗi: {CONFIG_FILE_PATH}."); create_default_config_file()
        else: logger.info(f"Không tìm thấy file AppData. Tạo file mới."); create_default_config_file()
        if not config.has_option('Auth', 'ltoken_v2') or not config.has_option('Auth', 'cookie_token_v2'): logger.error("Thiếu token động sau khi load!")
    except Exception as e: logger.critical(f"Lỗi load config: {e}", exc_info=True); config = configparser.ConfigParser(); config.read_string(DEFAULT_STATIC_AUTH); logger.warning("Sử dụng Auth cố định do lỗi.")
    logger.debug("get_config() hoàn thành.")
    return config

def save_dynamic_tokens(ltoken: str, cookie_token: str) -> bool:
    logger.info("Lưu token động vào AppData...")
    config_to_save = configparser.ConfigParser()
    try:
        if os.path.exists(CONFIG_FILE_PATH): config_to_save.read(CONFIG_FILE_PATH, encoding='utf-8')
        else:
             default_dw_parser = configparser.ConfigParser(); default_dw_parser.read_string(DEFAULT_DISPLAY_WINDOW)
             if default_dw_parser.has_section('Display'): config_to_save['Display'] = default_dw_parser['Display']
             if default_dw_parser.has_section('Window'): config_to_save['Window'] = default_dw_parser['Window']
        if not config_to_save.has_section('Auth'): config_to_save.add_section('Auth')
        config_to_save.set('Auth', 'ltoken_v2', ltoken if ltoken else '')
        config_to_save.set('Auth', 'cookie_token_v2', cookie_token if cookie_token else '')
        for key in ['ltuid_v2', 'account_mid_v2', 'uid_gi', 'uid_hsr']:
             if config_to_save.has_option('Auth', key): config_to_save.remove_option('Auth', key)
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f: config_to_save.write(f)
        logger.info(f"Đã lưu token động vào: {CONFIG_FILE_PATH}")
        return True
    except Exception as e: logger.error(f"Lỗi lưu token động: {e}", exc_info=True); return False

def save_display_and_window_settings(config_runtime: configparser.ConfigParser, game_type: str, x: int, y: int):
    logger.debug(f"Lưu Display/Window cho {game_type} ({x},{y}) vào AppData...")
    config_to_save = configparser.ConfigParser()
    try:
        if os.path.exists(CONFIG_FILE_PATH): config_to_save.read(CONFIG_FILE_PATH, encoding='utf-8')
        else: logger.warning("File AppData không tồn tại khi lưu Display/Window?")
        if config_runtime.has_section('Display'):
            if not config_to_save.has_section('Display'): config_to_save.add_section('Display')
            config_to_save['Display'] = config_runtime['Display']
        elif config_to_save.has_section('Display'): config_to_save.remove_section('Display')

        if not config_to_save.has_section('Window'): config_to_save.add_section('Window')
        config_to_save.set('Window', f'last_x_{game_type}', str(x))
        config_to_save.set('Window', f'last_y_{game_type}', str(y))

        if config_to_save.has_section('Auth'):
             ltoken = config_to_save.get('Auth', 'ltoken_v2', fallback='')
             cookie_token = config_to_save.get('Auth', 'cookie_token_v2', fallback='')
             config_to_save.remove_section('Auth'); config_to_save.add_section('Auth')
             config_to_save.set('Auth', 'ltoken_v2', ltoken); config_to_save.set('Auth', 'cookie_token_v2', cookie_token)
        else:
             pass

        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f: config_to_save.write(f)
        logger.info(f"Đã lưu Display/Window vào: {CONFIG_FILE_PATH}")
    except Exception as e: logger.error(f"Lỗi save_display_and_window_settings: {e}", exc_info=True)

# --- End Config Functions ---

class ClickableFrame(QFrame):
    def __init__(self, parent=None): super().__init__(parent); self.url = None; self.setCursor(QCursor(Qt.PointingHandCursor)); self.setContentsMargins(0, 0, 0, 0)
    def setUrl(self, url_string): self.url = QUrl(url_string)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.url and self.url.isValid(): logger.info(f"Mở URL: {self.url.toString()}"); QDesktopServices.openUrl(self.url)

class BackgroundFrame(QFrame):
    def __init__(self, parent=None): super().__init__(parent); self.background_image = None
    def setBackgroundImage(self, image_path):
        abs_image_path = resource_path(image_path) if image_path else '' # Use resource_path
        if abs_image_path and os.path.exists(abs_image_path):
            try: img = QPixmap(abs_image_path); (self.setBackgroundImageFromPixmap(img) if not img.isNull() else logger.error(f"Lỗi QPixmap: {abs_image_path}"))
            except Exception as e: logger.error(f"Lỗi tải QPixmap: {abs_image_path} - {e}"); self.background_image = None
        else: self.background_image = None; logger.warning(f"Không tìm thấy ảnh nền: {abs_image_path}") if abs_image_path else None; self.update()
    def setBackgroundImageFromPixmap(self, pixmap): self.background_image = pixmap; logger.debug(f"Ảnh nền OK."); self.update()
    def paintEvent(self, event):
        try:
            painter = QPainter(self);
            if self.background_image and not self.background_image.isNull(): painter.drawPixmap(self.rect(), self.background_image.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            else: painter.fillRect(self.rect(), QBrush(self.palette().color(self.backgroundRole())))
        except Exception as e: logger.error(f"Lỗi BackgroundFrame.paintEvent: {e}", exc_info=True)
# --- End GUI Classes ---


class GenshinWidgetApp(QWidget):
    def __init__(self):
        logger.debug("GenshinWidgetApp __init__.")
        super().__init__()
        try: self.config = get_config()
        except Exception as e: logger.critical(f"...Lỗi load config: {e}", exc_info=True); QMessageBox.critical(None, "Lỗi Config", f"Không thể load config:\n{e}"); sys.exit(1)
        self.client=None; self.custom_font=QFont(); self.uid=None; self.timer=None
        self.ign="Đang tải..."; self.level="N/A"; self.region=None
        self.shutting_down_due_to_auth_error = False
        self.initUI(); self.oldPos = self.pos()
        logger.debug("GenshinWidgetApp __init__ OK.")

    def initUI(self):
        logger.debug("Bắt đầu initUI (Genshin)")
        try:
            display_config=self.config['Display']; auth_config=self.config['Auth']; window_config=self.config['Window']
            logger.debug("Kiểm tra Auth/UID (Genshin)...")
            req_keys=['ltuid_v2', 'ltoken_v2', 'cookie_token_v2', 'account_mid_v2', 'uid_GI']
            missing_keys = [k for k in req_keys if not auth_config.get(k) or auth_config.get(k,'').startswith('#')]
            try: uid_str=auth_config.get('uid_GI'); assert uid_str is not None, "Thiếu uid_GI"; self.uid=int(uid_str); logger.info(f"Genshin UID: {self.uid}")
            except Exception as e: err=f"Lỗi uid_GI [Auth]: {e}."; self.show_warning(err); logger.critical(err, exc_info=True); sys.exit(1)

            logger.debug("Đọc config Display/Window...")
            try:
                self.word_wrap=self.bool_from_str(display_config.get('word_wrap','0')); self.fit_window_to_text=self.bool_from_str(display_config.get('fit_window_to_text','0'))
                show_taskbar=self.bool_from_str(display_config.get('show_in_taskbar','1')); on_top=self.bool_from_str(display_config.get('always_on_top','0'))
                allow_resize=self.bool_from_str(display_config.get('allow_resizing','1')); self.is_draggable=self.bool_from_str(display_config.get('draggable','1'))
                show_title=self.bool_from_str(display_config.get('show_title_bar','1')); trans=float(display_config.get('transparency','1.0'))
                lx=window_config.getint('last_x_GI',100); ly=window_config.getint('last_y_GI',100); self.margins=display_config.getint('margins',10)
                self.font_size=display_config.getint('font_size',12); self.font_color=display_config.get('font_color','#FFFFFF')
                self.show_bg=self.bool_from_str(display_config.get('show_background','1')); self.bg_color=display_config.get('background_color','rgba(30,35,55,0.85)')
                self.bg_img=display_config.get('background_image',''); self.radius=display_config.getint('corner_radius',10)
                self.interval=max(1, display_config.getint('update_interval_minutes',5)); self.font_path=display_config.get("font_file","zh-cn.ttf")
                self.icon_width = display_config.getint('icon_width', 35)
            except Exception as e: err=f"Lỗi giá trị config: {e}"; self.show_warning(err); logger.critical(err, exc_info=True); sys.exit(1)
            if self.word_wrap and self.fit_window_to_text: err="word_wrap/fit_window xung đột."; self.show_warning(err); logger.critical(err); sys.exit(1)

            logger.debug("Cài đặt cửa sổ..."); flags=Qt.Window;
            if not show_taskbar: flags|=Qt.Tool|Qt.FramelessWindowHint
            elif not show_title: flags|=Qt.FramelessWindowHint
            if on_top: flags|=Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags); self.setAttribute(Qt.WA_TranslucentBackground); self.setWindowOpacity(trans); self.move(lx, ly)
            logger.debug("Thiết lập layout...")
            self.main_layout=QVBoxLayout(self); self.main_layout.setContentsMargins(0,0,0,0); self.bg_frame=BackgroundFrame(); self.main_layout.addWidget(self.bg_frame)
            self.content_layout=QVBoxLayout(self.bg_frame); self.content_layout.setContentsMargins(self.margins, self.margins, self.margins, self.margins)
            logger.debug("Tải font...")
            font_abs = resource_path(self.font_path)
            self.custom_font = QFont()
            if os.path.exists(font_abs):
                fid=QFontDatabase.addApplicationFont(font_abs)
                if fid!=-1:
                    try: families=QFontDatabase.applicationFontFamilies(fid); self.custom_font=QFont(families[0]) if families else QFont(); logger.info(f"Font OK: {self.custom_font.family()}")
                    except Exception as fe: logger.error(f"Lỗi lấy font family: {fe}"); self.custom_font=QFont()
                else: logger.error(f"Lỗi tải font (add failed): {font_abs}.")
            else: logger.warning(f"Không thấy file font: {font_abs}.")

            logger.debug("Client/Cookies...")
            try: self.client = genshin.Client(); self.set_cookies(auth_config)
            except Exception as e: logger.critical(f"Lỗi Client/Cookie ban đầu: {e}", exc_info=True)
            self.apply_styles()
            logger.debug("Thiết lập kích thước...")
            if not allow_resize:
                 if not self.fit_window_to_text:
                    try: w=self.config.getint('Display','window_width',fallback=250); h=self.config.getint('Display','window_height',fallback=160); self.setFixedSize(w,h); logger.debug(f"Fixed size: {w}x{h}")
                    except: self.setFixedSize(250,160)
                 else: logger.debug("fit_window_to_text=1")
            else: w=self.config.getint('Display','window_width',fallback=300); h=self.config.getint('Display','window_height',fallback=190); self.resize(w,h); logger.debug(f"Initial size: {w}x{h}")

            asyncio.ensure_future(self.update_info())
            self.timer=QTimer(self); self.timer.timeout.connect(self.trigger_update_info)
            self.timer.start(self.interval * 60 * 1000); logger.info(f"Timer update: {self.interval} phút.")
            logger.debug("initUI (Genshin) hoàn thành.")
        except Exception as e: logger.critical(f"Lỗi initUI (Genshin): {e}", exc_info=True); self.show_warning(f"Lỗi khởi tạo UI: {e}"); sys.exit(1)

    def apply_styles(self):
        logger.debug("Apply styles...")
        if not hasattr(self, 'config') or not self.config: return
        try: 
            style=f""" * {{ color:{self.font_color};font-size:{self.font_size}px;background:transparent;}} BackgroundFrame {{ border-radius:{self.radius}px;background:{'transparent' if self.bg_img and self.show_bg else self.bg_color};}} """; self.setStyleSheet(style)
            bg_img_abs_path = resource_path(self.bg_img) if self.bg_img else ''; (self.bg_frame.setBackgroundImage(bg_img_abs_path) if self.show_bg and bg_img_abs_path and os.path.exists(bg_img_abs_path) else self.bg_frame.setBackgroundImage(None))
        except Exception as e: logger.error(f"Lỗi apply_styles: {e}", exc_info=True)

    def bool_from_str(self, value): return str(value).strip() == '1'
    def set_cookies(self, auth_config):
        logger.debug("Set cookies...")
        if not self.client: raise RuntimeError("Client null.")
        try:
            ltuid=auth_config.get('ltuid_v2')
            ltoken=auth_config.get('ltoken_v2')
            cookie_token=auth_config.get('cookie_token_v2')
            account_mid=auth_config.get('account_mid_v2')
            if not all([ltuid, ltoken, cookie_token, account_mid]) or ltoken.startswith('#') or cookie_token.startswith('#'):
                raise ValueError("Thiếu hoặc sai định dạng Auth keys/tokens.")
            cookies={'ltuid_v2':ltuid, 'ltoken_v2':ltoken, 'cookie_token_v2':cookie_token, 'account_mid_v2':account_mid}
            self.client.set_cookies(cookies); logger.info(f"Cookies OK.")
        except Exception as e: logger.error(f"Lỗi set_cookies: {e}"); raise RuntimeError(f"Không thể set cookies: {e}") from e

    def trigger_update_info(self): logger.debug("Timer triggered."); asyncio.ensure_future(self.update_info())


    async def update_info(self):
        logger.debug("Bắt đầu update_info (Genshin).")
        if self.uid is None: logger.error("UID null."); return
        ign_uid_level_text = f"{self.ign} UID: {self.uid} Lv: {self.level}"; resin_text="Nhựa: Lỗi"; commission_text="Ủy Thác: Lỗi"; realm_text="Đ.Tiên: Lỗi"; expedition_text="T.Hiểm: Lỗi"; auth_error=False
        if self.ign == "Đang tải...":
             logger.info(f"Lần đầu, lấy IGN/Level/Region..."); api_url = "https://api-account-os.hoyoverse.com/account/binding/api/getUserGameRolesByCookieToken"; 
             try:
                 auth_conf = self.config['Auth']; cookie_str=f"ltuid_v2={auth_conf.get('ltuid_v2')}; ltoken_v2={auth_conf.get('ltoken_v2')}; cookie_token_v2={auth_conf.get('cookie_token_v2')}; account_mid_v2={auth_conf.get('account_mid_v2')};"; headers = {'Cookie': cookie_str, 'User-Agent': 'Mozilla/5.0'}
                 async with aiohttp.ClientSession(headers=headers) as session:
                     async with session.get(api_url, timeout=10) as resp:
                         resp.raise_for_status(); data = await resp.json()
                         if data.get("retcode") == 0:
                             accs = data.get("data", {}).get("list", []); found = False
                             for acc in accs:
                                 if acc.get("game_biz") == "hk4e_global" and str(acc.get("game_uid")) == str(self.uid): self.ign=acc.get('nickname','(Ko tên)'); self.level=acc.get('level','N/A'); self.region=acc.get('region', None); logger.info(f"IGN/Level/Region OK: {self.ign} Lv:{self.level} R:{self.region}"); found=True; break
                             if not found: logger.warning(f"Ko tìm thấy Genshin UID {self.uid}."); self.ign="(Ko thấy)"
                         else: logger.error(f"API IGN lỗi: {data.get('retcode')} {data.get('message')}"); self.ign="(Lỗi API)"
             except Exception as e: logger.error(f"Lỗi lấy IGN/Level/Region: {e}", exc_info=True); self.ign="(Lỗi IGN)"
             ign_uid_level_text = f"{self.ign} UID: {self.uid} Lv: {self.level}"
        if not self.client: logger.error("Client null."); return
        try:
            logger.info(f"Gọi API get_genshin_notes...")
            notes = await self.client.get_genshin_notes(self.uid)
            if notes:
                logger.info(f"API Notes OK"); now_utc = datetime.datetime.now(datetime.timezone.utc)
                resin_num = f"{notes.current_resin}/{notes.max_resin}"; resin_countdown_str = "??:?";
                if notes.current_resin >= notes.max_resin: resin_countdown_str = "Đầy"
                else:
                    recovery_time = notes.resin_recovery_time
                    if isinstance(recovery_time, datetime.timedelta):
                        if recovery_time.total_seconds() > 1: resin_countdown_str = format_timedelta_hm(recovery_time)
                        else: resin_countdown_str = "<1m"
                    elif isinstance(recovery_time, int):
                        if recovery_time > 1: delta = datetime.timedelta(seconds=recovery_time); resin_countdown_str = format_timedelta_hm(delta)
                        else: resin_countdown_str = "<1m"
                    elif isinstance(recovery_time, datetime.datetime):
                        try:
                            if recovery_time.tzinfo is None: recovery_time_utc = recovery_time.replace(tzinfo=datetime.timezone.utc)
                            else: recovery_time_utc = recovery_time.astimezone(datetime.timezone.utc)
                            if recovery_time_utc > now_utc: delta = recovery_time_utc - now_utc; resin_countdown_str = format_timedelta_hm(delta)
                            else: resin_countdown_str = "<1m"
                        except Exception as dt_err: logger.error(f"Lỗi xử lý resin datetime: {dt_err}"); resin_countdown_str = "Lỗi DT"
                    else: logger.warning(f"Loại resin time lạ: {type(recovery_time)}."); resin_countdown_str = "??:??"
                resin_text = f"Nhựa Nguyên Chất: {resin_num} ({resin_countdown_str})"

                claimed_str = "✓" if notes.claimed_commission_reward else ""; commission_text = f"Ủy Thác Hằng Ngày: {notes.completed_commissions}/{notes.max_commissions} {claimed_str}".strip()

                realm_num = f"{notes.current_realm_currency}/{notes.max_realm_currency}"
                realm_countdown_str = "??:??"
                if hasattr(notes, 'current_realm_currency') and hasattr(notes, 'max_realm_currency') and notes.current_realm_currency >= notes.max_realm_currency:
                    realm_countdown_str = "Đầy"
                elif hasattr(notes, 'realm_currency_recovery_time') and isinstance(notes.realm_currency_recovery_time, datetime.datetime):
                    try:
                        realm_full_dt_utc = notes.realm_currency_recovery_time.replace(tzinfo=datetime.timezone.utc)
                        realm_remaining_delta = realm_full_dt_utc - now_utc
                        realm_countdown_str = format_timedelta_hm(realm_remaining_delta)
                    except Exception as dt_err: logger.error(f"Lỗi xử lý realm datetime: {dt_err}"); realm_countdown_str = "Lỗi DT"
                else:
                    logger.warning(f"Realm chưa đầy nhưng thiếu/sai recovery time: {getattr(notes, 'realm_currency_recovery_time', 'N/A')}")
                    realm_countdown_str = "??:??"
                realm_text = f"Tiền Động Tiên: {realm_num} ({realm_countdown_str})"
                exp_num = "Lỗi"; exp_countdown_str = "??:??"
                if hasattr(notes, 'expeditions') and hasattr(notes, 'max_expeditions') and isinstance(notes.expeditions, list):
                     exp_num = f"{len(notes.expeditions)}/{notes.max_expeditions}"
                     try:
                         ongoing=[e.completion_time for e in notes.expeditions if e.status=="Ongoing" and isinstance(e.completion_time, datetime.datetime)]
                         if ongoing: min_t_utc=min(ongoing); exp_delta=min_t_utc.replace(tzinfo=datetime.timezone.utc)-now_utc; exp_countdown_str=format_timedelta_hm(exp_delta)
                         else: exp_countdown_str = "Xong"
                     except Exception as e: logger.warning(f"Lỗi tính expedition time: {e}"); exp_countdown_str = "Lỗi"
                else: logger.warning("Thiếu thuộc tính expeditions."); exp_num="Lỗi TT"; exp_countdown_str="Lỗi TT"
                expedition_text = f"Phái đi Thám Hiểm: {exp_num} ({exp_countdown_str})"

            else: logger.warning("API get_genshin_notes trả về None."); resin_text="Nhựa: K/data"; commission_text="Ủy Thác: K/data"; realm_text="Đ.Tiên: K/data"; expedition_text="T.Hiểm: K/data"; auth_error = True
        except (genshin.errors.InvalidCookies, genshin.errors.AccountNotFound) as e:
            logger.error(f"Lỗi Cookie/TK: {e}")
            self.shutting_down_due_to_auth_error = True
            auth_error = True
            resin_text = "Lỗi: Cookie/TK sai"
            commission_text = " "
            realm_text = " "
            expedition_text = " "

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

            QTimer.singleShot(500, lambda: QApplication.quit())
        except genshin.errors.DataNotPublic: logger.error("API Lỗi: Dữ liệu ẩn!"); resin_text="Lỗi: Dữ liệu ẩn"; auth_error = True
        except genshin.errors.GenshinException as e: logger.error(f"API Lỗi: {e}", exc_info=True); resin_text=f"Lỗi API ({getattr(e, 'retcode', '?')})"; auth_error = True
        except asyncio.TimeoutError: logger.error("API Lỗi: Timeout."); resin_text = "Lỗi: Timeout"; auth_error = True
        except Exception as e: logger.error(f"Lỗi update_info: {e}", exc_info=True); resin_text = f"Lỗi..."; auth_error = True
        finally:
            if not auth_error: logger.debug("Scheduling update_ui..."); 
            try: QTimer.singleShot(0, lambda ignuidlv=ign_uid_level_text, res=resin_text, comm=commission_text, realm=realm_text, exped=expedition_text: self.update_ui(ignuidlv, res, comm, realm, exped)) 
            except Exception as e: logger.error(f"Lỗi QTimer: {e}", exc_info=True)
            else: logger.debug("Auth error, deferring UI update."); QTimer.singleShot(0, lambda ignuidlv=ign_uid_level_text, res=resin_text, comm=commission_text, realm=realm_text, exped=expedition_text: self.update_ui(ignuidlv, res, comm, realm, exped))
        logger.debug("update_info hoàn thành.")

    def update_ui(self, ign_uid_level_info, resin_info, commission_info, realm_info, expedition_info):
        logger.debug(f"Bắt đầu update_ui (Genshin)...")
        try:
            logger.debug("Xóa widget cũ...")
            while self.content_layout.count(): item=self.content_layout.takeAt(0); w=item.widget(); l=item.layout(); (w.deleteLater() if w else (self.clear_layout(l) if l else None))

            def create_row_layout(icon_name, text):
                layout = QHBoxLayout(); layout.setContentsMargins(0,0,0,0)
                icon_label = QLabel(); icon_label.setFixedWidth(self.icon_width); icon_label.setAlignment(Qt.AlignCenter)
                text_label = QLabel(text)
                icon_folder = resource_path("Icon")
                icon_path = os.path.join(icon_folder, f"{icon_name}.png")
                icon_size = self.font_size + 4
                if os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path).scaledToHeight(icon_size, Qt.SmoothTransformation)
                    if not pixmap.isNull(): icon_label.setPixmap(pixmap)
                    else: logger.warning(f"Icon null: {icon_path}"); icon_label.setText("?")
                else: logger.warning(f"Icon miss: {icon_path}"); icon_label.setText("?") # Log đường dẫn đầy đủ hơn
                text_label.setFont(self.custom_font); text_label.setWordWrap(self.word_wrap); layout.addWidget(icon_label); layout.addWidget(text_label, 1); return layout

            info_frame = ClickableFrame(); info_layout = create_row_layout("user_GI", ign_uid_level_info); # Sử dụng user_GI.png
            info_frame.setLayout(info_layout)
            if self.region: bc_url = f"https://act.hoyolab.com/app/community-game-records-sea/index.html?role_id={self.uid}&server={self.region}#/ys"; info_frame.setUrl(bc_url); info_frame.setToolTip("Mở Battle Chronicle (Genshin)")
            self.content_layout.addWidget(info_frame)
            resin_layout = create_row_layout("resin", resin_info); self.content_layout.addLayout(resin_layout)
            commission_frame = ClickableFrame(); commission_layout = create_row_layout("commission", commission_info); commission_frame.setLayout(commission_layout)
            checkin_url = "https://act.hoyolab.com/ys/event/signin-sea-v3/index.html?act_id=e202102251931481"; commission_frame.setUrl(checkin_url); commission_frame.setToolTip("Mở Điểm danh hàng ngày (Genshin)")
            self.content_layout.addWidget(commission_frame)
            realm_layout = create_row_layout("realm_currency", realm_info); self.content_layout.addLayout(realm_layout)
            expedition_layout = create_row_layout("expedition", expedition_info); self.content_layout.addLayout(expedition_layout)
            self.content_layout.addStretch(1)
            if self.fit_window_to_text: logger.debug("fit_window_to_text=1."); QTimer.singleShot(50, self.adjustSize)
        except Exception as e: logger.error(f"Lỗi update_ui: {e}", exc_info=True)
        logger.debug("update_ui hoàn thành.")


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
                 logger.debug("Kéo xong, lưu vị trí (Genshin).")
                 save_display_and_window_settings(self.config, "GI", self.x(), self.y())
             super().mouseReleaseEvent(e)
         except Exception as err: logger.error(f"Lỗi mouseRelease: {err}"); super().mouseReleaseEvent(e)


    def closeEvent(self, event):
        logger.info("closeEvent (Genshin)...")
        if not self.shutting_down_due_to_auth_error:
            save_display_and_window_settings(self.config, "GI", self.x(), self.y())
        event.accept(); logger.info("closeEvent OK (Genshin).")
        
if __name__ == '__main__':
    logger.info("--- Bắt đầu __main__ (Genshin) ---")
    app, loop, window = None, None, None; exit_code = 0
    try:
        try:
            if hasattr(Qt,'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True)
            if hasattr(Qt,'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
        except: pass
        app = QApplication(sys.argv)
        loop = QEventLoop(app); asyncio.set_event_loop(loop)
        with loop:
            window = GenshinWidgetApp()
            window.show()
            logger.info("Chạy event loop (Genshin)...")
            loop.run_forever()
    except KeyboardInterrupt: logger.info("Đã nhận Ctrl+C (Genshin).")
    except SystemExit as e: logger.info(f"Thoát (Genshin) với mã: {e.code}"); exit_code = e.code
    except Exception as e:
         logger.critical(f"Lỗi __main__ (Genshin): {e}", exc_info=True)
         try: QMessageBox.critical(None,"Lỗi Widget Genshin", f"Lỗi nghiêm trọng:\n{e}\nXem log.")
         except: pass
         exit_code = 1
    finally:
        logger.info(f"--- Kết thúc Widget Genshin (mã: {exit_code}) ---")
        if loop and loop.is_running(): loop.stop()
        sys.exit(exit_code)