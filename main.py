import time
import urandom
import ujson
import machine
import esp32
import struct
import ubluetooth
import network
import micropython
from machine import SoftSPI, Pin, RTC
import st7789

# --- 1. Prevent Antenna Interference ---
try:
    network.WLAN(network.STA_IF).active(False)
    network.WLAN(network.AP_IF).active(False)
except Exception:
    pass

# --- Hardware Pins (LilyGO T-Display) ---
SCK_PIN  = 18
MOSI_PIN = 19
MISO_PIN = 17
DC_PIN   = 16
CS_PIN   = 5
BL_PIN   = 4

BTN1_PIN = 0    
BTN2_PIN = 35   
VIBE_PIN = 13   

WIDTH  = 135
HEIGHT = 240
XSTART = 52
YSTART = 40

# --- Color Palette (RGB565) ---
BLACK    = 0x0000
DARK_CARD = 0x18E3
CARD_EDGE = 0x2965
GRAY_TEXT = 0x9CE7
WHITE    = 0xFFFF
ORANGE   = 0xFD20
GREEN    = 0x07E0
RED      = 0xF800
CYAN     = 0x07FF
YELLOW   = 0xFFE0

# --- Initialize Hardware ---
dc = Pin(DC_PIN, Pin.OUT)
cs = Pin(CS_PIN, Pin.OUT)
bl = Pin(BL_PIN, Pin.OUT) if BL_PIN else None
if bl: bl.value(1)

btn1 = Pin(BTN1_PIN, Pin.IN, Pin.PULL_UP)
btn2 = Pin(BTN2_PIN, Pin.IN)   

spi = SoftSPI(
    baudrate=20_000_000, polarity=1, phase=1,
    sck=Pin(SCK_PIN), mosi=Pin(MOSI_PIN), miso=Pin(MISO_PIN)
)

display = st7789.ST7789(
    spi=spi, width=WIDTH, height=HEIGHT, reset=None,
    dc=dc, cs=cs, rotation=4, xstart=XSTART, ystart=YSTART, inversion=True
)

def haptic(pattern=[150]):
    vibe_pin = Pin(VIBE_PIN, Pin.OUT)
    for i, ms in enumerate(pattern):
        vibe_pin.value(1 if i % 2 == 0 else 0)
        time.sleep_ms(ms)
    vibe_pin.value(0)

# --- Drawing Utilities ---
SEGMENTS = {
    '0': (1,1,1,0,1,1,1), '1': (0,0,1,0,0,1,0), '2': (1,0,1,1,1,0,1),
    '3': (1,0,1,1,0,1,1), '4': (0,1,1,1,0,1,0), '5': (1,1,0,1,0,1,1),
    '6': (1,1,0,1,1,1,1), '7': (1,0,1,0,0,1,0), '8': (1,1,1,1,1,1,1),
    '9': (1,1,1,1,0,1,1), ':': (0,0,0,0,0,0,0)
}

def draw_smooth_digit(x, y, char, color, bg_color, w=14, h=26, t=3):
    display.fill_rect(x, y, w, h, bg_color)
    if char == ':':
        display.fill_rect(x + w//2 - 1, y + h//3 - 1, 3, 3, color)
        display.fill_rect(x + w//2 - 1, y + (2*h)//3 - 1, 3, 3, color)
        return
    segs = SEGMENTS.get(char, (0,0,0,0,0,0,0))
    half_h = h // 2
    if segs[0]: display.fill_rect(x, y, w, t, color)
    if segs[1]: display.fill_rect(x, y, t, half_h, color)
    if segs[2]: display.fill_rect(x + w - t, y, t, half_h, color)
    if segs[3]: display.fill_rect(x, y + half_h - t//2, w, t, color)
    if segs[4]: display.fill_rect(x, y + half_h, t, half_h, color)
    if segs[5]: display.fill_rect(x + w - t, y + half_h, t, half_h, color)
    if segs[6]: display.fill_rect(x, y + h - t, w, t, color)

def draw_smooth_timer_string(x, y, string, color, bg_color):
    curr_x = x
    for char in string:
        spacing = 6 if char == ':' else 18
        draw_smooth_digit(curr_x, y, char, color, bg_color)
        curr_x += spacing

MINI_GLYPHS = {
    'A': (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11), 'B': (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    'C': (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E), 'D': (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    'E': (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F), 'F': (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    'G': (0x0E, 0x11, 0x10, 0x13, 0x11, 0x11, 0x0F), 'H': (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    'I': (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E), 'J': (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    'K': (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11), 'L': (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    'M': (0x11, 0x1B, 0x15, 0x11, 0x11, 0x11, 0x11), 'N': (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    'O': (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E), 'P': (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    'Q': (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D), 'R': (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    'S': (0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E), 'T': (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    'U': (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E), 'V': (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    'W': (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11), 'X': (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    'Y': (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04), 'Z': (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    '0': (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E), '1': (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    '2': (0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F), '3': (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    '4': (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02), '5': (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    '6': (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E), '7': (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    '8': (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E), '9': (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    ':': (0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00), '%': (0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03),
    ' ': (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00), '!': (0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04),
    '-': (0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00), '.': (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C)
}

def draw_clean_char(x, y, char, color, bg_color):
    rows = MINI_GLYPHS.get(char.upper(), MINI_GLYPHS[' '])
    display.fill_rect(x, y, 6, 8, bg_color)
    for r, byte in enumerate(rows):
        for c in range(5):
            if byte & (1 << (4 - c)):
                display.fill_rect(x + c, y + r, 1, 1, color)

def draw_clean_text(x, y, text, color, bg_color):
    curr_x = x
    for ch in text:
        draw_clean_char(curr_x, y, ch, color, bg_color)
        curr_x += 7

def draw_scaled_char(x, y, char, color, bg_color, scale=2):
    rows = MINI_GLYPHS.get(char.upper(), MINI_GLYPHS[' '])
    display.fill_rect(x, y, 6 * scale, 8 * scale, bg_color)
    for r, byte in enumerate(rows):
        for c in range(5):
            if byte & (1 << (4 - c)):
                display.fill_rect(x + c * scale, y + r * scale, scale, scale, color)

def draw_scaled_text(x, y, text, color, bg_color, scale=2):
    curr_x = x
    for ch in text:
        draw_scaled_char(curr_x, y, ch, color, bg_color, scale)
        curr_x += 6 * scale + 1

def draw_card(x, y, w, h, color=DARK_CARD, border=CARD_EDGE):
    display.fill_rect(x, y, w, h, color)
    display.rect(x, y, w, h, border)

def draw_progress_bar(x, y, w, h, percent, fg_color, bg_color):
    display.fill_rect(x, y, w, h, bg_color)
    fill_w = max(0, min(w, int(w * (percent / 100.0))))
    if fill_w > 0:
        display.fill_rect(x, y, fill_w, h, fg_color)

# --- Storage & Logic ---
LOG_FILE = "logs.json"
CFG_FILE = "config.json"

DEFAULT_CFG = {
    "tasks": ["WALK 2M", "DRINK WATER", "15 SQUATS", "STRETCH", "EYE EXERCISE"],
    "first_interval": 5,
    "min_interval": 10,
    "max_interval": 30
}

class StorageManager:
    @staticmethod
    def load_cfg():
        try:
            with open(CFG_FILE, "r") as f: return ujson.load(f)
        except:
            return DEFAULT_CFG

    @staticmethod
    def save_cfg(cfg):
        with open(CFG_FILE, "w") as f: ujson.dump(cfg, f)

    @staticmethod
    def load_logs():
        try:
            with open(LOG_FILE, "r") as f: return ujson.load(f)
        except:
            return {"logs": [], "stats": {"acc": 0, "ign": 0, "focus_m": 0}}

    @staticmethod
    def log_event(event_type, details):
        data = StorageManager.load_logs()
        
        if "focus_m" not in data["stats"]:
            data["stats"]["focus_m"] = data["stats"].get("sit_m", 0)
        if "acc" not in data["stats"]: data["stats"]["acc"] = 0
        if "ign" not in data["stats"]: data["stats"]["ign"] = 0
            
        rtc = RTC().datetime() 
        ts_str = f"{rtc[0]}-{rtc[1]:02d}-{rtc[2]:02d} {rtc[4]:02d}:{rtc[5]:02d}"
        
        entry = {"ts": ts_str, "type": event_type}
        entry.update(details)
        data["logs"].append(entry)
        
        if len(data["logs"]) > 30: data["logs"] = data["logs"][-30:] 
        
        if event_type == "TASK":
            if details.get("out") == "ACC": data["stats"]["acc"] += 1
            elif details.get("out") == "IGN": data["stats"]["ign"] += 1
        elif event_type == "FOCUS":
            data["stats"]["focus_m"] += round(details.get("duration", 0) / 60)
            
        with open(LOG_FILE, "w") as f: ujson.dump(data, f)
        return data["stats"]

# --- BLE Server Setup ---
def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None):
    payload = bytearray()
    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value
    
    # Flags: LE General Discoverable Mode, BR/EDR not supported
    _append(0x01, struct.pack("B", 0x06))
    
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 16:
                # FIXED: Append standard 128-bit UUID bytes directly without reversing
                _append(0x07, b)
            elif len(b) == 2:
                _append(0x03, b)
                
    if name:
        max_len = 31 - len(payload) - 2
        if max_len > 0:
            _append(0x09, name.encode()[:max_len])
            
    return payload

class BLEServer:
    def __init__(self, app_ref):
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)
        self.app = app_ref
        
        NUS_UUID = ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        RX_UUID  = ubluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
        TX_UUID  = ubluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")
        
        nus_service = (
            NUS_UUID,
            (
                (TX_UUID, 0x0002 | 0x0010), 
                (RX_UUID, 0x0008 | 0x0004), 
            ),
        )
        
        ((self.tx, self.rx),) = self.ble.gatts_register_services((nus_service,))
        self.conn = None
        
        self.adv_data = advertising_payload(name=None, services=[NUS_UUID])
        self.start_advertising()
        self.rx_buffer = ""

    def start_advertising(self, arg=None):
        try:
            self.ble.gap_advertise(100000, adv_data=self.adv_data)
        except OSError as e:
            print("Ignored BLE advertise error:", e)

    def _irq(self, event, data):
        if event == 1:
            self.conn = data[0]
            self.app.ble_status = "BLE: ON"
            self.app.ble_status_dirty = True
        elif event == 2:
            self.conn = None
            self.app.ble_status = "BLE: WAIT"
            self.app.ble_status_dirty = True
            try:
                micropython.schedule(self.start_advertising, 0)
            except RuntimeError:
                pass
        elif event == 3:
            conn_handle, value_handle = data
            if value_handle == self.rx:
                try:
                    raw = self.ble.gatts_read(self.rx).decode('utf-8')
                    self.rx_buffer += raw
                    micropython.schedule(self._scheduled_process, 0)
                except Exception as e:
                    print("! Buffer read error:", e)

    def _scheduled_process(self, arg):
        self.process_buffer()

    def process_buffer(self):
        while True:
            start = self.rx_buffer.find('{')
            if start == -1:
                if len(self.rx_buffer) > 256:
                    self.rx_buffer = ""
                break
            
            brace_count = 0
            end = -1
            in_string = False
            escape = False
            
            for i in range(start, len(self.rx_buffer)):
                char = self.rx_buffer[i]
                if escape:
                    escape = False
                    continue
                if char == '\\':
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i
                            break
            
            if end != -1:
                json_str = self.rx_buffer[start:end+1]
                self.rx_buffer = self.rx_buffer[end+1:]
                try:
                    cmd = ujson.loads(json_str)
                    self.handle_cmd(cmd)
                except Exception as e:
                    print("! JSON parse error:", e, "on packet:", json_str)
            else:
                if start > 0:
                    self.rx_buffer = self.rx_buffer[start:]
                break

    def handle_cmd(self, cmd):
        self.app.idle_since = time.time()
        print("-> BLE Received:", cmd)
        try:
            action = cmd.get("cmd") or cmd.get("c")
            
            if action in ("GET_LOGS", "LOG", "LOGS"):
                print("<- BLE Sending LOGS...")
                self.send({"type": "LOGS", "data": StorageManager.load_logs()})
                print("   Done!")
            elif action in ("GET_CFG", "CFG"):
                print("<- BLE Sending CFG...")
                self.send({"type": "CFG", "data": self.app.cfg})
                print("   Done!")
            elif action in ("SET_CFG", "SCFG"):
                self.app.cfg = cmd.get("data", {}) or cmd.get("d", self.app.cfg)
                StorageManager.save_cfg(self.app.cfg)
                print("<- BLE Sending ACK (Cfg Saved)")
                self.send({"type": "ACK"})
            elif action in ("SYNC_TIME", "SYNC"):
                t = cmd.get("time") or cmd.get("t")
                if t and isinstance(t, list) and len(t) >= 6:
                    RTC().datetime((t[0], t[1], t[2], 0, t[3], t[4], t[5], 0))
                    print("<- BLE Sending ACK (Time Synced)")
                    self.send({"type": "ACK"})
                else:
                    print("! SYNC missing valid time array")
        except Exception as e: 
            print("! Error handling command:", e)

    def send(self, obj):
        if self.conn is not None:
            msg = (ujson.dumps(obj) + "\n").encode('utf-8')
            chunk_size = 20
                
            for i in range(0, len(msg), chunk_size):
                chunk = msg[i:i+chunk_size]
                sent = False
                attempts = 0
                while not sent and attempts < 15:
                    try:
                        self.ble.gatts_notify(self.conn, self.tx, chunk)
                        sent = True
                    except OSError as e:
                        attempts += 1
                        time.sleep_ms(50)
                if not sent:
                    print("! Failed to send: Browser notifications not enabled for this session yet.")
                time.sleep_ms(25)

MODES = [15, 30, 45, 60, 0] 

class SmartTracker:
    def __init__(self):
        self.ble_status = "BLE: WAIT"
        self.ble_status_dirty = False
        self.ble = BLEServer(self)
        self.cfg = StorageManager.load_cfg()
        
        log_data = StorageManager.load_logs()
        if "focus_m" not in log_data["stats"]:
            log_data["stats"]["focus_m"] = log_data["stats"].get("sit_m", 0)
        self.stats = log_data["stats"]
        
        self.mode_idx = 0
        self.state = "IDLE" 
        self.task_in_progress = False
        
        self.start_t = 0
        self.elapsed = 0
        self.last_tick = 0
        
        self.next_prompt = 0
        self.current_task = ""
        
        self.last_timer_str = ""
        self.screen_off = False
        self.idle_since = time.time()
        
        self.btn1_prev = 1
        self.btn2_prev = 1

        if machine.reset_cause() == machine.DEEPSLEEP_RESET:
            self.draw_ui_framework()

    def calc_compliance(self):
        total = self.stats["acc"] + self.stats["ign"]
        return int((self.stats["acc"] / total) * 100) if total > 0 else 0

    def draw_ui_framework(self):
        display.fill(BLACK)
        self.update_header(self.ble_status)
        draw_card(6, 22, 123, 70)
        draw_clean_text(12, 28, "TARGET SESSION", GRAY_TEXT, DARK_CARD)
        draw_card(6, 100, 123, 62)
        draw_clean_text(12, 106, "COMPLIANCE", GRAY_TEXT, DARK_CARD)
        self.update_stats()
        draw_card(6, 170, 123, 38)
        draw_clean_text(12, 175, "STATUS", GRAY_TEXT, DARK_CARD)

    def update_header(self, ble_txt):
        self.ble_status = ble_txt
        if self.screen_off: return
        display.fill_rect(6, 6, 75, 12, BLACK)
        draw_clean_text(6, 6, ble_txt, CYAN, BLACK)
        comp_str = f"{self.calc_compliance()}%"
        display.fill_rect(90, 6, 40, 12, BLACK)
        draw_clean_text(90, 6, comp_str, GREEN, BLACK)

    def update_timer_display(self, time_str, color=WHITE):
        if time_str == self.last_timer_str or self.screen_off: return
        self.last_timer_str = time_str
        draw_smooth_timer_string(22, 48, time_str, color, DARK_CARD)

    def update_stats(self):
        if self.screen_off: return
        comp = self.calc_compliance()
        draw_progress_bar(12, 122, 111, 6, comp, GREEN, BLACK)
        display.fill_rect(12, 138, 111, 14, DARK_CARD)
        draw_clean_text(12, 138, f"ACC: {self.stats['acc']}  IGN: {self.stats['ign']}", WHITE, DARK_CARD)

    def update_status_box(self, text, color, bg=DARK_CARD, border=CARD_EDGE, subtext=""):
        if self.screen_off: return
        draw_card(6, 170, 123, 38, bg, border)
        draw_clean_text(12, 175, "STATUS", GRAY_TEXT if bg==DARK_CARD else WHITE, bg)
        draw_clean_text(12, 188, text, color, bg)
        if subtext: draw_clean_text(12, 198, subtext, WHITE, bg)

    def update_footer(self, btn1_txt, btn2_txt):
        if self.screen_off: return
        display.fill_rect(0, 215, WIDTH, 25, BLACK)
        if btn1_txt: draw_clean_text(4, 218, btn1_txt, CYAN, BLACK)
        if btn2_txt:
            x2 = WIDTH - (len(btn2_txt) * 7) - 4
            draw_clean_text(x2, 218, btn2_txt, GREEN, BLACK)

    def set_screen_power(self, turn_on):
        if turn_on and self.screen_off:
            if bl: bl.value(1)
            self.screen_off = False
            self.draw_ui_framework()
            self.last_timer_str = ""
            self.refresh_ui_state()
        elif not turn_on and not self.screen_off:
            display.fill(BLACK)
            if bl: bl.value(0)
            self.screen_off = True

    def refresh_ui_state(self):
        if self.screen_off: return
        if self.state == "IDLE":
            self.update_status_box("IDLE", YELLOW)
            self.update_footer("SWITCH", "START")
        elif self.state == "RUNNING":
            if self.task_in_progress:
                self.update_status_box("IN PROGRESS", ORANGE)
            else:
                self.update_status_box("TRACKING...", GREEN)
            self.update_footer("PAUSE", "STOP")
        elif self.state == "PAUSED":
            self.update_status_box("PAUSED", YELLOW)
            self.update_footer("RESUME", "STOP")
        elif self.state == "PROMPT":
            draw_card(6, 170, 123, 38, RED, RED)
            draw_scaled_text(12, 181, self.current_task, WHITE, RED, scale=2)
            self.update_footer("DO IT", "SKIP")

    def get_btn_press(self):
        b1, b2 = btn1.value(), btn2.value()
        p1 = (b1 == 0 and self.btn1_prev == 1)
        p2 = (b2 == 0 and self.btn2_prev == 1)
        self.btn1_prev, self.btn2_prev = b1, b2
        return p1, p2

    def change_state(self, new_state):
        self.state = new_state
        self.refresh_ui_state()
        self.idle_since = time.time()

    def generate_next_prompt(self, is_first=False):
        mins = self.cfg['first_interval'] if is_first else urandom.randint(self.cfg['min_interval'], self.cfg['max_interval'])
        self.next_prompt = self.elapsed + (mins * 60)

    def main(self):
        self.draw_ui_framework()
        self.refresh_ui_state()
        
        while True:
            now = time.time()
            
            if self.ble_status_dirty:
                self.ble_status_dirty = False
                self.update_header(self.ble_status)

            p1, p2 = self.get_btn_press()
            
            if p1 or p2:
                self.idle_since = now
                if self.screen_off:
                    self.set_screen_power(True)
                    continue

            if self.state == "IDLE" and self.ble.conn is None and (now - self.idle_since > 60):
                display.fill(BLACK)
                if bl: bl.value(0)
                esp32.wake_on_ext0(pin=btn2, level=esp32.WAKEUP_ALL_LOW)
                machine.deepsleep()
                
            if self.state == "RUNNING" and not self.screen_off and (now - self.idle_since > 60):
                self.set_screen_power(False)

            if self.state == "RUNNING":
                dt = now - self.last_tick
                if dt >= 1:
                    self.elapsed += dt
                    self.last_tick = now
                    
                    target = MODES[self.mode_idx] * 60
                    if target > 0 and self.elapsed >= target:
                        self.set_screen_power(True)
                        haptic([400, 150, 400, 150, 800]) 
                        StorageManager.log_event("FOCUS", {"duration": self.elapsed})
                        self.elapsed = 0
                        self.task_in_progress = False
                        self.change_state("IDLE")
                        self.update_status_box("COMPLETED!", GREEN)
                    else:
                        disp_sec = self.elapsed if target == 0 else target - self.elapsed
                        mm, ss = divmod(int(disp_sec), 60)
                        self.update_timer_display(f"{mm:02d}:{ss:02d}", ORANGE if target > 0 else CYAN)
                        
                        if self.elapsed >= self.next_prompt:
                            self.set_screen_power(True)
                            self.current_task = urandom.choice(self.cfg['tasks'])
                            self.change_state("PROMPT")

            if self.state == "IDLE":
                target = MODES[self.mode_idx] * 60
                mm, ss = divmod(target, 60)
                self.update_timer_display(f"{mm:02d}:{ss:02d}", WHITE)

            if self.state == "IDLE":
                if p1:
                    haptic([100])
                    self.mode_idx = (self.mode_idx + 1) % len(MODES)
                    self.last_timer_str = "" 
                elif p2:
                    haptic([300]) 
                    self.elapsed = 0
                    self.task_in_progress = False
                    self.last_tick = now
                    self.generate_next_prompt(is_first=True)
                    self.change_state("RUNNING")

            elif self.state == "RUNNING":
                if p1:
                    haptic([200, 100, 200]) 
                    self.change_state("PAUSED")
                elif p2:
                    haptic([300, 150, 300]) 
                    StorageManager.log_event("FOCUS", {"duration": self.elapsed})
                    self.elapsed = 0
                    self.task_in_progress = False
                    self.change_state("IDLE")
                    self.update_status_box("STOPPED", RED)

            elif self.state == "PAUSED":
                if p1:
                    haptic([200])
                    self.last_tick = now
                    self.change_state("RUNNING")
                elif p2:
                    haptic([300, 150, 300])
                    StorageManager.log_event("FOCUS", {"duration": self.elapsed})
                    self.elapsed = 0
                    self.task_in_progress = False
                    self.change_state("IDLE")
                    self.update_status_box("STOPPED", RED)

            elif self.state == "PROMPT":
                if time.ticks_ms() % 1500 < 300:
                    Pin(VIBE_PIN, Pin.OUT).value(1)
                else:
                    Pin(VIBE_PIN, Pin.OUT).value(0)
                
                if p1:
                    Pin(VIBE_PIN, Pin.OUT).value(0)
                    haptic([150])
                    self.stats = StorageManager.log_event("TASK", {"task": self.current_task, "out": "ACC"})
                    self.update_stats()
                    self.task_in_progress = True
                    self.generate_next_prompt()
                    self.last_tick = now
                    self.change_state("RUNNING")
                elif p2:
                    Pin(VIBE_PIN, Pin.OUT).value(0)
                    haptic([150])
                    self.stats = StorageManager.log_event("TASK", {"task": self.current_task, "out": "IGN"})
                    self.update_stats()
                    self.task_in_progress = False
                    self.generate_next_prompt()
                    self.last_tick = now
                    self.change_state("RUNNING")

            time.sleep_ms(50)

if __name__ == "__main__":
    SmartTracker().main()
