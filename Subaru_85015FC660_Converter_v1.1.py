# -*- coding: utf-8 -*-
"""
Subaru Forester 85015FC660 / 93C56 x16
Miles -> KM + Fahrenheit -> Celsius converter

Verified target:
- Cluster: Subaru 85015FC660
- EEPROM: 93C56 x16, 256 bytes
- Odometer journal: 0x60..0x7F
- Temperature-unit bytes:
    Fahrenheit: 55 99 55 99 55 99
    Celsius:    33 55 33 55 33 55

The program never overwrites the source BIN.
"""

from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_VERSION = "1.1"
EXPECTED_SIZE = 256

ODO_START = 0x60
ODO_END   = 0x80

TEMP_START = 0x80
TEMP_END   = 0x86
TEMP_F = bytes.fromhex("55 99 55 99 55 99")
TEMP_C = bytes.fromhex("33 55 33 55 33 55")

ENC_NIBBLE = [0x0, 0x7, 0xC, 0xB, 0x6, 0x1, 0xA, 0xD,
              0x3, 0x4, 0xF, 0x8, 0x5, 0x2, 0x9, 0xE]
DEC_NIBBLE = {v: i for i, v in enumerate(ENC_NIBBLE)}

TEXT = {
    "ru": {
        "title": "Subaru 85015FC660 — Miles → KM / °F → °C",
        "open": "Открыть BIN",
        "save": "Создать новый BIN",
        "language": "English",
        "details": "Данные BIN",
        "file": "Файл",
        "cluster": "Щиток",
        "miles": "Пробег в исходном BIN",
        "km_exact": "Точный эквивалент",
        "km_output": "Пробег для нового BIN",
        "journal": "Журнал 0x60–0x7F",
        "temp": "Температура",
        "status": "Статус",
        "not_loaded": "BIN не загружен",
        "valid": "OK — структура пробега распознана",
        "temp_f": "°F — распознано",
        "temp_c": "°C — уже установлено",
        "temp_unknown": "Неизвестная сигнатура",
        "opt_km": "Конвертировать Miles → KM",
        "opt_c": "Заменить °F → °C",
        "report": "Создать TXT-отчёт",
        "warning": "Важно",
        "warning_text": (
            "Только для Subaru 85015FC660 / EEPROM 93C56 x16.\n"
            "Оригинальный BIN не перезаписывается.\n"
            "Перед записью обязательно сохраните исходный дамп."
        ),
        "bad_size": "Ожидался BIN размером 256 байт, получено: {size}.",
        "decode_error": "Не удалось декодировать пробег:\n{err}",
        "choose_first": "Сначала откройте исходный BIN.",
        "nothing": "Не выбрано ни одной операции.",
        "temp_refuse": (
            "Сигнатура температуры не похожа ни на штатный °F, ни на штатный °C.\n"
            "Для безопасности °F → °C не выполнено."
        ),
        "saved": "Готово",
        "saved_text": "Создан новый BIN:\n{path}\n\nИзменено байт: {count}",
        "rounding": "Пробег округляется до ближайшего целого километра.",
        "about": "Алгоритм 0x60–0x7F и °F→°C проверен на реальном щитке 85015FC660.",
    },
    "en": {
        "title": "Subaru 85015FC660 — Miles → KM / °F → °C",
        "open": "Open BIN",
        "save": "Create new BIN",
        "language": "Русский",
        "details": "BIN data",
        "file": "File",
        "cluster": "Cluster",
        "miles": "Mileage decoded from source BIN",
        "km_exact": "Exact equivalent",
        "km_output": "Mileage for new BIN",
        "journal": "Journal 0x60–0x7F",
        "temp": "Temperature units",
        "status": "Status",
        "not_loaded": "No BIN loaded",
        "valid": "OK — odometer structure recognized",
        "temp_f": "°F — recognized",
        "temp_c": "°C — already set",
        "temp_unknown": "Unknown signature",
        "opt_km": "Convert Miles → KM",
        "opt_c": "Replace °F → °C",
        "report": "Create TXT report",
        "warning": "Important",
        "warning_text": (
            "For Subaru 85015FC660 / 93C56 x16 only.\n"
            "The original BIN is never overwritten.\n"
            "Always keep the original EEPROM dump."
        ),
        "bad_size": "Expected a 256-byte BIN; got {size} bytes.",
        "decode_error": "Could not decode mileage:\n{err}",
        "choose_first": "Open the source BIN first.",
        "nothing": "No operation selected.",
        "temp_refuse": (
            "The temperature signature is neither the known °F nor the known °C pattern.\n"
            "For safety, °F → °C was not performed."
        ),
        "saved": "Done",
        "saved_text": "New BIN created:\n{path}\n\nChanged bytes: {count}",
        "rounding": "Mileage is rounded to the nearest whole kilometer.",
        "about": "The 0x60–0x7F and °F→°C algorithms were verified on a real 85015FC660 cluster.",
    },
}


def u16le(buf: bytes, off: int) -> int:
    return buf[off] | (buf[off + 1] << 8)


def encode_q(q: int) -> int:
    return (q & 0xFFF0) | ENC_NIBBLE[q & 0x0F]


def decode_code(code: int) -> int:
    low = code & 0x0F
    if low not in DEC_NIBBLE:
        raise ValueError(f"invalid encoded low nibble 0x{low:X}")
    return (code & 0xFFF0) | DEC_NIBBLE[low]


def logical_halves(buf: bytes) -> list[int]:
    vals = []
    for off in range(ODO_START, ODO_END, 4):
        data = u16le(buf, off)
        inv = u16le(buf, off + 2)
        vals.append(data)
        vals.append(inv ^ 0xFFFF)
    return vals


def decode_mileage(buf: bytes) -> tuple[int, dict]:
    if len(buf) != EXPECTED_SIZE:
        raise ValueError("wrong BIN size")

    codes = logical_halves(buf)
    qs = [decode_code(c) for c in codes]

    if len(set(qs)) == 1:
        q = qs[0]
        r = 15
        return q * 16 + r, {
            "q": q,
            "r": r,
            "prefix_halves": 16,
            "codes": codes,
        }

    q_new = qs[0]
    k = 0
    while k < 16 and qs[k] == q_new:
        k += 1

    if not (1 <= k <= 15):
        raise ValueError("invalid journal transition length")

    q_old = q_new - 1
    if q_old < 0 or any(q != q_old for q in qs[k:]):
        raise ValueError("invalid journal sequence")

    r = k - 1
    return q_new * 16 + r, {
        "q": q_new,
        "r": r,
        "prefix_halves": k,
        "codes": codes,
    }


def encode_mileage(mileage: int) -> bytes:
    if mileage < 0:
        raise ValueError("mileage must be >= 0")

    q, r = divmod(int(mileage), 16)
    if q > 0xFFFF:
        raise ValueError("mileage is outside supported range")

    new_code = encode_q(q)
    old_code = encode_q(q - 1) if q > 0 else new_code

    halves = [new_code] * (r + 1) + [old_code] * (15 - r)

    out = bytearray()
    for slot in range(8):
        data_code = halves[slot * 2]
        inv_code = halves[slot * 2 + 1] ^ 0xFFFF
        out += data_code.to_bytes(2, "little")
        out += inv_code.to_bytes(2, "little")
    return bytes(out)


def detect_temp(buf: bytes) -> str:
    sig = buf[TEMP_START:TEMP_END]
    if sig == TEMP_F:
        return "F"
    if sig == TEMP_C:
        return "C"
    return "?"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "ru"
        self.src_path = None
        self.src = None
        self.src_miles = None
        self.src_info = None
        self.temp_state = "?"

        root.geometry("760x640")
        root.minsize(720, 600)

        self.main = ttk.Frame(root, padding=16)
        self.main.pack(fill="both", expand=True)

        top = ttk.Frame(self.main)
        top.pack(fill="x")
        self.btn_open = ttk.Button(top, command=self.open_bin)
        self.btn_open.pack(side="left")
        self.btn_lang = ttk.Button(top, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.info = ttk.LabelFrame(self.main, padding=12)
        self.info.pack(fill="x", pady=(14, 10))

        keys = ["file", "cluster", "miles", "km_exact", "km_output", "journal", "temp", "status"]
        self.vars = {k: tk.StringVar() for k in keys}
        self.labels = {}

        for r, key in enumerate(keys):
            lab = ttk.Label(self.info)
            lab.grid(row=r, column=0, sticky="w", padx=(0, 14), pady=4)
            self.labels[key] = lab
            ttk.Label(self.info, textvariable=self.vars[key]).grid(row=r, column=1, sticky="w", pady=4)

        self.info.columnconfigure(1, weight=1)

        self.options = ttk.Frame(self.main)
        self.options.pack(fill="x", pady=(4, 8))

        self.opt_km = tk.BooleanVar(value=True)
        self.opt_c = tk.BooleanVar(value=False)
        self.opt_report = tk.BooleanVar(value=True)

        self.chk_km = ttk.Checkbutton(self.options, variable=self.opt_km)
        self.chk_km.pack(anchor="w", pady=2)
        self.chk_c = ttk.Checkbutton(self.options, variable=self.opt_c)
        self.chk_c.pack(anchor="w", pady=2)
        self.chk_report = ttk.Checkbutton(self.options, variable=self.opt_report)
        self.chk_report.pack(anchor="w", pady=2)

        self.warn = ttk.LabelFrame(self.main, padding=12)
        self.warn.pack(fill="x", pady=(8, 12))
        self.warn_text = ttk.Label(self.warn, wraplength=700, justify="left")
        self.warn_text.pack(fill="x")

        self.btn_save = ttk.Button(self.main, command=self.save_bin)
        self.btn_save.pack(fill="x", ipady=7)

        self.footer = ttk.Label(self.main, wraplength=700, justify="left")
        self.footer.pack(fill="x", pady=(14, 0))

        self.refresh_text()

    def t(self, key):
        return TEXT[self.lang][key]

    def refresh_text(self):
        self.root.title(f"{self.t('title')} v{APP_VERSION}")
        self.btn_open.config(text=self.t("open"))
        self.btn_lang.config(text=self.t("language"))
        self.btn_save.config(text=self.t("save"))
        self.info.config(text=self.t("details"))

        for key in self.labels:
            self.labels[key].config(text=self.t(key) + ":")

        self.chk_km.config(text=self.t("opt_km"))
        self.chk_c.config(text=self.t("opt_c"))
        self.chk_report.config(text=self.t("report"))

        self.warn.config(text=self.t("warning"))
        self.warn_text.config(text=self.t("warning_text"))
        self.footer.config(text=self.t("rounding") + "\n" + self.t("about"))

        self.vars["cluster"].set("85015FC660 / 93C56 x16")

        if self.src is None:
            self.vars["file"].set(self.t("not_loaded"))
            for k in ["miles", "km_exact", "km_output", "journal", "temp", "status"]:
                self.vars[k].set("—")
        else:
            self.populate()

    def toggle_lang(self):
        self.lang = "en" if self.lang == "ru" else "ru"
        self.refresh_text()

    def open_bin(self):
        name = filedialog.askopenfilename(
            title=self.t("open"),
            filetypes=[("BIN", "*.bin *.BIN"), ("All files", "*.*")]
        )
        if not name:
            return

        p = Path(name)
        data = p.read_bytes()

        if len(data) != EXPECTED_SIZE:
            messagebox.showerror(self.t("status"), self.t("bad_size").format(size=len(data)))
            return

        try:
            miles, info = decode_mileage(data)
        except Exception as e:
            messagebox.showerror(self.t("status"), self.t("decode_error").format(err=e))
            return

        self.src_path = p
        self.src = data
        self.src_miles = miles
        self.src_info = info
        self.temp_state = detect_temp(data)

        # If source is Fahrenheit, enable F->C by default.
        self.opt_c.set(self.temp_state == "F")
        self.populate()

    def populate(self):
        km_exact = self.src_miles * 1.609344
        km_out = int(km_exact + 0.5)

        self.vars["file"].set(self.src_path.name)
        self.vars["miles"].set(f"{self.src_miles:,} mi".replace(",", " "))
        self.vars["km_exact"].set(f"{km_exact:,.6f} km".replace(",", " "))
        self.vars["km_output"].set(f"{km_out:,} km".replace(",", " "))
        self.vars["journal"].set(
            f"Q=0x{self.src_info['q']:04X}, R={self.src_info['r']}, "
            f"halves={self.src_info['prefix_halves']}/16"
        )
        self.vars["temp"].set({
            "F": self.t("temp_f"),
            "C": self.t("temp_c"),
            "?": self.t("temp_unknown"),
        }[self.temp_state])
        self.vars["status"].set(self.t("valid"))

    def save_bin(self):
        if self.src is None:
            messagebox.showwarning(self.t("status"), self.t("choose_first"))
            return

        if not self.opt_km.get() and not self.opt_c.get():
            messagebox.showwarning(self.t("status"), self.t("nothing"))
            return

        out = bytearray(self.src)
        km_exact = self.src_miles * 1.609344
        km_out = int(km_exact + 0.5)
        actions = []

        if self.opt_km.get():
            out[ODO_START:ODO_END] = encode_mileage(km_out)
            actions.append(f"Miles -> KM: {self.src_miles} mi -> {km_out} km")

        temp_changed = False
        if self.opt_c.get():
            if self.temp_state == "F":
                out[TEMP_START:TEMP_END] = TEMP_C
                temp_changed = True
                actions.append("Temperature: °F -> °C")
            elif self.temp_state == "C":
                actions.append("Temperature: already °C, no change")
            else:
                messagebox.showwarning(self.t("warning"), self.t("temp_refuse"))
                actions.append("Temperature: unknown signature, no change")

        suffix = []
        if self.opt_km.get():
            suffix.append(f"{km_out}km")
        if temp_changed:
            suffix.append("C")
        if not suffix:
            suffix.append("converted")

        default = f"{self.src_path.stem}_{'_'.join(suffix)}.bin"

        name = filedialog.asksaveasfilename(
            title=self.t("save"),
            initialdir=str(self.src_path.parent),
            initialfile=default,
            defaultextension=".bin",
            filetypes=[("BIN", "*.bin"), ("All files", "*.*")]
        )
        if not name:
            return

        dst = Path(name)
        try:
            if dst.resolve() == self.src_path.resolve():
                dst = dst.with_name(dst.stem + "_converted" + dst.suffix)
        except Exception:
            pass

        out = bytes(out)
        dst.write_bytes(out)

        changed = [i for i, (a, b) in enumerate(zip(self.src, out)) if a != b]

        if self.opt_report.get():
            rpt = dst.with_suffix(".txt")
            lines = [
                "Subaru 85015FC660 / 93C56 x16",
                f"Converter version: {APP_VERSION}",
                "",
                f"Source file: {self.src_path.name}",
                f"Source mileage: {self.src_miles} miles",
                f"Exact equivalent: {km_exact:.6f} km",
                f"Written odometer value: {km_out} km" if self.opt_km.get() else "Odometer: unchanged",
                f"Temperature source: {self.temp_state}",
                f"Temperature output: {'C' if (temp_changed or self.temp_state == 'C') else self.temp_state}",
                "",
                "Actions:",
                *[f"- {x}" for x in actions],
                "",
                f"Source SHA-256: {sha256(self.src)}",
                f"Output SHA-256: {sha256(out)}",
                f"Changed byte count: {len(changed)}",
                "Changed offsets: " + (" ".join(f"{x:02X}" for x in changed) if changed else "-"),
                "",
                f"Known °F signature @0x80: {TEMP_F.hex(' ').upper()}",
                f"Known °C signature @0x80: {TEMP_C.hex(' ').upper()}",
                "",
                "Keep the original EEPROM dump.",
            ]
            rpt.write_text("\n".join(lines), encoding="utf-8")

        messagebox.showinfo(
            self.t("saved"),
            self.t("saved_text").format(path=dst, count=len(changed))
        )


def self_test():
    # Odometer algorithm checkpoints.
    for m in [271445, 271610, 271898, 272079, 272080, 272081, 436848]:
        buf = bytearray([0] * EXPECTED_SIZE)
        buf[ODO_START:ODO_END] = encode_mileage(m)
        got, _ = decode_mileage(bytes(buf))
        assert got == m, (m, got)

    expected_436848 = bytes.fromhex(
        "AD 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95 "
        "AA 6A 55 95"
    )
    assert encode_mileage(436848) == expected_436848

    # Temperature signatures.
    b = bytearray([0] * EXPECTED_SIZE)
    b[TEMP_START:TEMP_END] = TEMP_F
    assert detect_temp(bytes(b)) == "F"
    b[TEMP_START:TEMP_END] = TEMP_C
    assert detect_temp(bytes(b)) == "C"


if __name__ == "__main__":
    self_test()
    root = tk.Tk()
    App(root)
    root.mainloop()
