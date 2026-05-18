#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk
import threading
import time
import sys
import math
import platform


try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print(" pip install psutil")

try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False


class INA219:
    """Waveshare UPS HAT üzerindeki INA219 güç ölçüm IC'si."""
    ADDR = 0x42
    REG_CONFIG   = 0x00
    REG_SHUNT    = 0x01
    REG_BUS      = 0x02
    REG_POWER    = 0x03
    REG_CURRENT  = 0x04
    REG_CALIB    = 0x05

    def __init__(self, bus_num: int = 1):
        if not HAS_SMBUS:
            raise ImportError("smbus2 yüklü değil")
        self.bus = smbus2.SMBus(bus_num)
        self._calibrate()

    def _calibrate(self):
        # 32V, 2A arasi
        self.bus.write_word_data(self.ADDR, self.REG_CALIB, 0x2000)
        self.bus.write_word_data(self.ADDR, self.REG_CONFIG, 0x399F)

    def _read(self, reg: int) -> int:
        raw = self.bus.read_word_data(self.ADDR, reg)
        return ((raw & 0xFF) << 8) | (raw >> 8)

    @property
    def bus_voltage(self) -> float:
        raw = self._read(self.REG_BUS)
        return (raw >> 3) * 0.004  # V

    @property
    def shunt_voltage(self) -> float:
        raw = self._read(self.REG_SHUNT)
        if raw > 32767:
            raw -= 65536
        return raw * 0.00001  # V

    @property
    def current_mA(self) -> float:
        raw = self._read(self.REG_CURRENT)
        if raw > 32767:
            raw -= 65536
        return raw * 0.1  # mA

    @property
    def power_mW(self) -> float:
        raw = self._read(self.REG_POWER)
        return raw * 2.0  # mW

    def get_info(self) -> dict:
        v = self.bus_voltage + self.shunt_voltage
        pct = max(0.0, min(100.0, (v - 3.0) / (4.2 - 3.0) * 100.0))
        current = self.current_mA
        return {
            "percent":   round(pct, 1),
            "voltage":   round(v, 3),
            "current":   round(current, 1),
            "power":     round(self.power_mW, 1),
            "charging":  current < 0,
            "source":    "Waveshare UPS HAT (INA219)",
        }

#bu satır sonrasında ne olacak bilmem,insallah calısır ve odryi geceriz
_ina: INA219 | None = None

def _try_ina() -> bool:
    global _ina
    if not HAS_SMBUS:
        return False
    try:
        _ina = INA219()
        return True
    except Exception:
        _ina = None
        return False

def get_battery_info() -> dict:
    """Mevcut donanıma göre batarya bilgisini döndür."""
    # 1) INA219 / Waveshare UPS HAT
    if _ina is not None:
        try:
            return _ina.get_info()
        except Exception:
            pass

    # 2) psutil (PC / dizüstü / RPi resmi UPS)
    if HAS_PSUTIL:
        batt = psutil.sensors_battery()
        if batt is not None:
            return {
                "percent":   round(batt.percent, 1),
                "voltage":   None,
                "current":   None,
                "power":     None,
                "charging":  batt.power_plugged,
                "source":    "PC/Laptop (psutil)",
            }

    # 3) Simülasyon (demo)
    t = time.time()
    pct = 50 + 45 * math.sin(t / 30)
    return {
        "percent":   round(pct, 1),
        "voltage":   round(3.7 + 0.5 * math.sin(t / 30), 3),
        "current":   round(500 + 200 * math.cos(t / 20), 1),
        "power":     None,
        "charging":  math.sin(t / 60) > 0,
        "source":    "Simülasyon (demo)",
    }

#renk ayrdısılaı
def pct_color(pct: float) -> str:
    if pct >= 60:  return "#00e676"   
    if pct >= 30:  return "#ffab00"   
    if pct >= 15:  return "#ff6d00"   
    return "#f44336"                  

def lerp_color(c1: str, c2: str, t: float) -> str:
    r1,g1,b1 = int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
    r2,g2,b2 = int(c2[1:3],16),int(c2[3:5],16),int(c2[5:7],16)
    r = int(r1 + (r2-r1)*t)
    g = int(g1 + (g2-g1)*t)
    b = int(b1 + (b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

class BatteryMonitorApp(tk.Tk):
    BG    = "#111111"
    SURF  = "#1a1a1a"
    CARD  = "#1a1a1a"
    BORD  = "#2a2a2a"

    TEXT  = "#ffffff"
    MUTED = "#9a9a9a"

    ACC   = "#00ff99"

    REFRESH_MS = 2000
    
    def __init__(self):
        super().__init__()
        self.title("⚡ CTbatarya")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self._data: dict = {}
        self._anim_angle = 0.0
        self._pulse = 0.0
        self._build_ui()
        self._update_loop()
        self.after(100, self._animate)

    def _build_ui(self):
        PAD = 20

        # baslık
        hdr = tk.Frame(self, bg=self.BG)
        hdr.pack(fill="x", padx=PAD, pady=(PAD, 0))

        tk.Label(hdr, text="⚡", font=("Segoe UI Emoji", 22),
                 bg=self.BG, fg=self.ACC).pack(side="left")
        tk.Label(hdr, text="CTBatarya ",
                 font=("Courier New", 15, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(side="left", padx=8)

        self.lbl_source = tk.Label(hdr, text="",
                                   font=("Courier New", 8),
                                   bg=self.BG, fg=self.MUTED)
        self.lbl_source.pack(side="right")

        tk.Frame(self, bg=self.BORD, height=1).pack(fill="x", padx=PAD, pady=8)

      
        ring_frame = tk.Frame(self, bg=self.BG)
        ring_frame.pack(pady=(4, 0))

        self.ring_canvas = tk.Canvas(ring_frame, width=220, height=220,
                                     bg=self.BG, highlightthickness=0)
        self.ring_canvas.pack()

 
        mid = tk.Frame(self, bg=self.BG)
        mid.pack(pady=(0, 6))

        self.lbl_pct = tk.Label(mid, text="-- %",
                                font=("Courier New", 38, "bold"),
                                bg=self.BG, fg=self.TEXT)
        self.lbl_pct.pack()

        self.lbl_status = tk.Label(mid, text="",
                                   font=("Courier New", 11),
                                   bg=self.BG, fg=self.MUTED)
        self.lbl_status.pack()

        tk.Frame(self, bg=self.BORD, height=1).pack(fill="x", padx=PAD, pady=8)

        bar_outer = tk.Frame(self, bg=self.BORD, height=18,
                             highlightthickness=1, highlightbackground=self.BORD)
        bar_outer.pack(fill="x", padx=PAD, pady=(0, 12))
        bar_outer.pack_propagate(False)

        self.bar_inner = tk.Frame(bar_outer, bg=self.ACC, height=18)
        self.bar_inner.place(x=0, y=0, relheight=1.0, width=0)

        self._bar_width = 0
        bar_outer.bind("<Configure>",
                       lambda e: setattr(self, "_bar_width", e.width))

 
        cards_frame = tk.Frame(self, bg=self.BG)
        cards_frame.pack(fill="x", padx=PAD, pady=(0, PAD))
        cards_frame.columnconfigure((0,1,2,3), weight=1)

        self.cards: dict[str, tuple] = {}
        defs = [
            ("voltage", "Voltaj", "V"),
            ("current", "Akım",   "mA"),
            ("power",   "Güç",    "mW"),
            ("temp",    "Sıcaklık","°C"),
        ]
        for col, (key, label, unit) in enumerate(defs):
            f = tk.Frame(cards_frame, bg=self.CARD,
                         highlightthickness=1,
                         highlightbackground=self.BORD)
            f.grid(row=0, column=col, padx=4, sticky="nsew", ipady=8)
            tk.Label(f, text=label, font=("Courier New", 7, "bold"),
                     bg=self.CARD, fg=self.MUTED).pack()
            val_lbl = tk.Label(f, text="—", font=("Courier New", 12, "bold"),
                               bg=self.CARD, fg=self.TEXT)
            val_lbl.pack()
            tk.Label(f, text=unit, font=("Courier New", 7),
                     bg=self.CARD, fg=self.MUTED).pack()
            self.cards[key] = (val_lbl,)

        
        self.lbl_time = tk.Label(self, text="",
                                 font=("Courier New", 8),
                                 bg=self.BG, fg=self.MUTED)
        self.lbl_time.pack(pady=(0, PAD//2))

    #rinfg
    def _draw_ring(self, pct: float, charging: bool):
        c = self.ring_canvas
        c.delete("all")

        cx, cy, r = 110, 110, 85
        track_w = 14

        # Arka iz
        c.create_arc(cx-r, cy-r, cx+r, cy+r,
                     start=135, extent=270,
                     outline=self.BORD, width=track_w,
                     style="arc")

        #  yay
        col = pct_color(pct)
        extent = 270 * (pct / 100.0)
        if extent > 0:
            c.create_arc(cx-r, cy-r, cx+r, cy+r,
                         start=135, extent=extent,
                         outline=col, width=track_w,
                         style="arc")

        # Animasyonlu şarj halkası
        if charging:
            a = self._anim_angle
            span = 30
            c.create_arc(cx-r-8, cy-r-8, cx+r+8, cy+r+8,
                         start=a, extent=span,
                         outline=self.ACC, width=2,
                         style="arc")
            c.create_arc(cx-r-8, cy-r-8, cx+r+8, cy+r+8,
                         start=a+180, extent=span,
                         outline=self.ACC, width=2,
                         style="arc")

        angle_rad = math.radians(135 + extent)
        tip_x = cx + (r) * math.cos(angle_rad)
        tip_y = cy - (r) * math.sin(angle_rad)
        c.create_oval(tip_x-5, tip_y-5, tip_x+5, tip_y+5,
                      fill=col, outline="")

        icon = "🔌" if charging else ("🪫" if pct < 20 else "🔋")
        c.create_text(cx, cy+10, text=icon,
                      font=("Segoe UI Emoji", 30),
                      fill=self.TEXT)


    def _update_loop(self):
        def worker():
            while True:
                info = get_battery_info()
                self.after(0, self._apply_data, info)
                time.sleep(self.REFRESH_MS / 1000)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _apply_data(self, info: dict):
        self._data = info
        pct      = info["percent"]
        charging = info["charging"]
        col      = pct_color(pct)

        # Yüzde & renk
        self.lbl_pct.config(text=f"{pct:.1f}%", fg=col)
        status = "⚡ Şarj oluyor…" if charging else (
            "⚠ Kritik" if pct < 15 else
            "🔋 Deşarj oluyor" if pct < 40 else
            "✅ İyi durumda"
        )
        self.lbl_status.config(text=status,
                               fg=self.ACC if charging else col)
        self.lbl_source.config(text=info["source"])

        if self._bar_width:
            w = int(self._bar_width * pct / 100)
            self.bar_inner.place(width=w)
            self.bar_inner.config(bg=col)

        # Ring
        self._draw_ring(pct, charging)

        # Detay kartları
        self.cards["voltage"][0].config(
            text=f"{info['voltage']:.3f}" if info["voltage"] else "—")
        self.cards["current"][0].config(
            text=f"{info['current']:.0f}" if info["current"] else "—")
        self.cards["power"][0].config(
            text=f"{info['power']:.0f}" if info["power"] else "—")

        # Sıcaklık (varsa yada yoksda)
        temp = None
        if HAS_PSUTIL:
            try:
                temps = psutil.sensors_temperatures()
                for key in ("coretemp", "cpu_thermal", "soc_thermal",
                            "acpitz", "cpu-thermal"):
                    if key in temps:
                        temp = temps[key][0].current
                        break
            except Exception:
                pass
        self.cards["temp"][0].config(
            text=f"{temp:.1f}" if temp else "—")

        # Saat
        ts = time.strftime("%H:%M:%S")
        self.lbl_time.config(text=f"Son güncelleme: {ts}")

    
    def _animate(self):
        self._anim_angle = (self._anim_angle + 3) % 360
        if self._data:
            self._draw_ring(self._data.get("percent", 0),
                            self._data.get("charging", False))
        self.after(50, self._animate)

#Gisris
if __name__ == "__main__":
    # INA219 dene
    ina_ok = _try_ina()
    source_msg = ("Waveshare UPS HAT (INA219) bulundu ✓" if ina_ok
                  else "INA219 bulunamadı → psutil ")
    print(f"[Başlıyor] {source_msg}")
    print(f"[Platform] {platform.system()} {platform.machine()}")

    app = BatteryMonitorApp()

    #Ortala
    app.update_idletasks()
    w, h = app.winfo_width(), app.winfo_height()
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    app.geometry(f"+{(sw-w)//2}+{(sh-h)//2}")

    app.mainloop()
