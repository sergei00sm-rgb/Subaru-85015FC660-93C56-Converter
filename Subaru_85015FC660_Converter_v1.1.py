# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_VERSION = "1.2"
EXPECTED_SIZE = 256
ODO_START, ODO_END = 0x60, 0x80
TEMP_START, TEMP_END = 0x80, 0x86
COEFF_START, COEFF_END = 0x24, 0x2C

TEMP_F = bytes.fromhex("55 99 55 99 55 99")
TEMP_C = bytes.fromhex("33 55 33 55 33 55")
COEFF_MILES = bytes.fromhex("08 10 00 00 08 10 00 00")
COEFF_KM    = bytes.fromhex("F4 09 02 00 F4 09 00 00")

ENC_NIBBLE = [0x0,0x7,0xC,0xB,0x6,0x1,0xA,0xD,0x3,0x4,0xF,0x8,0x5,0x2,0x9,0xE]
DEC_NIBBLE = {v:i for i,v in enumerate(ENC_NIBBLE)}

TEXT = {
"ru":{"title":"Subaru 85015FC660 — Miles→KM / импульсы / °F→°C","open":"Открыть BIN","save":"Создать новый BIN","language":"English","details":"Данные BIN","file":"Файл","cluster":"Щиток","miles":"Пробег в исходном BIN","km_exact":"Точный эквивалент","km_output":"Пробег для нового BIN","journal":"Журнал 0x60–0x7F","coeff":"Коэффициент импульсов","temp":"Температура","status":"Статус","not_loaded":"BIN не загружен","valid":"OK — структура распознана","coeff_miles":"Miles — американский коэффициент","coeff_km":"KM — километровый коэффициент","coeff_unknown":"Неизвестная сигнатура","temp_f":"°F — распознано","temp_c":"°C — уже установлено","temp_unknown":"Неизвестная сигнатура","opt_km":"Пересчитать сохранённый пробег Miles → KM","opt_coeff":"Переключить коэффициент импульсов Miles → KM","opt_c":"Заменить °F → °C","report":"Создать TXT-отчёт","warning":"Важно","warning_text":"Только для Subaru 85015FC660 / EEPROM 93C56 x16.\nОригинальный BIN не перезаписывается.\nПеред записью обязательно сохраните исходный дамп.","bad_size":"Ожидался BIN размером 256 байт, получено: {size}.","decode_error":"Не удалось декодировать пробег:\n{err}","choose_first":"Сначала откройте исходный BIN.","nothing":"Не выбрано ни одной операции.","coeff_refuse":"Сигнатура коэффициента не похожа ни на Miles, ни на KM. Для безопасности коэффициент не изменён.","temp_refuse":"Сигнатура температуры не похожа ни на штатный °F, ни на °C. Для безопасности температура не изменена.","saved":"Готово","saved_text":"Создан новый BIN:\n{path}\n\nИзменено байт: {count}","rounding":"Пробег округляется до ближайшего целого километра.","about":"Проверено на реальном щитке 85015FC660: пробег, коэффициент импульсов и °F→°C."},
"en":{"title":"Subaru 85015FC660 — Miles→KM / pulse coefficient / °F→°C","open":"Open BIN","save":"Create new BIN","language":"Русский","details":"BIN data","file":"File","cluster":"Cluster","miles":"Mileage decoded from source BIN","km_exact":"Exact equivalent","km_output":"Mileage for new BIN","journal":"Journal 0x60–0x7F","coeff":"Distance pulse coefficient","temp":"Temperature units","status":"Status","not_loaded":"No BIN loaded","valid":"OK — structure recognized","coeff_miles":"Miles — US coefficient","coeff_km":"KM — kilometer coefficient","coeff_unknown":"Unknown signature","temp_f":"°F — recognized","temp_c":"°C — already set","temp_unknown":"Unknown signature","opt_km":"Convert stored odometer Miles → KM","opt_coeff":"Switch distance pulse coefficient Miles → KM","opt_c":"Replace °F → °C","report":"Create TXT report","warning":"Important","warning_text":"For Subaru 85015FC660 / 93C56 x16 only.\nThe original BIN is never overwritten.\nAlways keep the original EEPROM dump.","bad_size":"Expected a 256-byte BIN; got {size} bytes.","decode_error":"Could not decode mileage:\n{err}","choose_first":"Open the source BIN first.","nothing":"No operation selected.","coeff_refuse":"Pulse-coefficient signature is neither known Miles nor KM. It was not changed.","temp_refuse":"Temperature signature is neither known °F nor °C. It was not changed.","saved":"Done","saved_text":"New BIN created:\n{path}\n\nChanged bytes: {count}","rounding":"Mileage is rounded to the nearest whole kilometer.","about":"Verified on a real 85015FC660 cluster: odometer, pulse coefficient and °F→°C."}
}

def u16le(buf,o): return buf[o] | (buf[o+1]<<8)
def encode_q(q): return (q & 0xFFF0) | ENC_NIBBLE[q & 0xF]
def decode_code(code):
    low=code & 0xF
    if low not in DEC_NIBBLE: raise ValueError(f"invalid encoded nibble 0x{low:X}")
    return (code & 0xFFF0) | DEC_NIBBLE[low]
def logical_halves(buf):
    vals=[]
    for off in range(ODO_START, ODO_END, 4):
        vals += [u16le(buf,off), u16le(buf,off+2)^0xFFFF]
    return vals
def decode_mileage(buf):
    qs=[decode_code(c) for c in logical_halves(buf)]
    if len(set(qs))==1:
        q=qs[0]; return q*16+15, {"q":q,"r":15,"prefix_halves":16}
    q_new=qs[0]; k=0
    while k<16 and qs[k]==q_new: k+=1
    if not 1<=k<=15: raise ValueError("invalid journal transition")
    q_old=q_new-1
    if q_old<0 or any(q!=q_old for q in qs[k:]): raise ValueError("invalid journal sequence")
    r=k-1
    return q_new*16+r, {"q":q_new,"r":r,"prefix_halves":k}
def encode_mileage(mileage):
    q,r=divmod(int(mileage),16)
    new=encode_q(q); old=encode_q(q-1) if q>0 else new
    halves=[new]*(r+1)+[old]*(15-r)
    out=bytearray()
    for s in range(8):
        out += halves[s*2].to_bytes(2,"little")
        out += (halves[s*2+1]^0xFFFF).to_bytes(2,"little")
    return bytes(out)
def detect_temp(buf):
    sig=buf[TEMP_START:TEMP_END]
    return "F" if sig==TEMP_F else "C" if sig==TEMP_C else "?"
def detect_coeff(buf):
    sig=buf[COEFF_START:COEFF_END]
    return "MILES" if sig==COEFF_MILES else "KM" if sig==COEFF_KM else "?"
def sha256(data): return hashlib.sha256(data).hexdigest()

class App:
    def __init__(self,root):
        self.root=root; self.lang="ru"; self.src=None; self.src_path=None; self.src_miles=None; self.src_info=None
        self.temp_state="?"; self.coeff_state="?"
        root.geometry("800x700")
        m=ttk.Frame(root,padding=16); m.pack(fill="both",expand=True)
        top=ttk.Frame(m); top.pack(fill="x")
        self.btn_open=ttk.Button(top,command=self.open_bin); self.btn_open.pack(side="left")
        self.btn_lang=ttk.Button(top,command=self.toggle_lang); self.btn_lang.pack(side="right")
        self.info=ttk.LabelFrame(m,padding=12); self.info.pack(fill="x",pady=(14,10))
        keys=["file","cluster","miles","km_exact","km_output","journal","coeff","temp","status"]
        self.vars={k:tk.StringVar() for k in keys}; self.labels={}
        for r,k in enumerate(keys):
            lab=ttk.Label(self.info); lab.grid(row=r,column=0,sticky="w",padx=(0,14),pady=4); self.labels[k]=lab
            ttk.Label(self.info,textvariable=self.vars[k]).grid(row=r,column=1,sticky="w",pady=4)
        self.opt_km=tk.BooleanVar(value=True); self.opt_coeff=tk.BooleanVar(value=False); self.opt_c=tk.BooleanVar(value=False); self.opt_report=tk.BooleanVar(value=True)
        self.chk_km=ttk.Checkbutton(m,variable=self.opt_km); self.chk_km.pack(anchor="w",pady=2)
        self.chk_coeff=ttk.Checkbutton(m,variable=self.opt_coeff); self.chk_coeff.pack(anchor="w",pady=2)
        self.chk_c=ttk.Checkbutton(m,variable=self.opt_c); self.chk_c.pack(anchor="w",pady=2)
        self.chk_report=ttk.Checkbutton(m,variable=self.opt_report); self.chk_report.pack(anchor="w",pady=2)
        self.warn=ttk.LabelFrame(m,padding=12); self.warn.pack(fill="x",pady=(8,12))
        self.warn_text=ttk.Label(self.warn,wraplength=730,justify="left"); self.warn_text.pack(fill="x")
        self.btn_save=ttk.Button(m,command=self.save_bin); self.btn_save.pack(fill="x",ipady=7)
        self.footer=ttk.Label(m,wraplength=730,justify="left"); self.footer.pack(fill="x",pady=(14,0))
        self.refresh()
    def t(self,k): return TEXT[self.lang][k]
    def refresh(self):
        self.root.title(f"{self.t('title')} v{APP_VERSION}")
        self.btn_open.config(text=self.t("open")); self.btn_lang.config(text=self.t("language")); self.btn_save.config(text=self.t("save"))
        self.info.config(text=self.t("details")); self.warn.config(text=self.t("warning")); self.warn_text.config(text=self.t("warning_text"))
        self.chk_km.config(text=self.t("opt_km")); self.chk_coeff.config(text=self.t("opt_coeff")); self.chk_c.config(text=self.t("opt_c")); self.chk_report.config(text=self.t("report"))
        self.footer.config(text=self.t("rounding")+"\n"+self.t("about"))
        for k,l in self.labels.items(): l.config(text=self.t(k)+":")
        self.vars["cluster"].set("85015FC660 / 93C56 x16")
        if self.src is None:
            self.vars["file"].set(self.t("not_loaded"))
            for k in ["miles","km_exact","km_output","journal","coeff","temp","status"]: self.vars[k].set("—")
        else: self.populate()
    def toggle_lang(self):
        self.lang="en" if self.lang=="ru" else "ru"; self.refresh()
    def open_bin(self):
        name=filedialog.askopenfilename(title=self.t("open"),filetypes=[("BIN","*.bin *.BIN"),("All files","*.*")])
        if not name: return
        p=Path(name); data=p.read_bytes()
        if len(data)!=EXPECTED_SIZE:
            messagebox.showerror(self.t("status"),self.t("bad_size").format(size=len(data))); return
        try: miles,info=decode_mileage(data)
        except Exception as e:
            messagebox.showerror(self.t("status"),self.t("decode_error").format(err=e)); return
        self.src_path=p; self.src=data; self.src_miles=miles; self.src_info=info
        self.temp_state=detect_temp(data); self.coeff_state=detect_coeff(data)
        self.opt_c.set(self.temp_state=="F"); self.opt_coeff.set(self.coeff_state=="MILES"); self.opt_km.set(self.coeff_state=="MILES")
        self.populate()
    def populate(self):
        km_exact=self.src_miles*1.609344; km_out=int(km_exact+0.5)
        self.vars["file"].set(self.src_path.name); self.vars["miles"].set(str(self.src_miles))
        self.vars["km_exact"].set(f"{km_exact:.6f} km"); self.vars["km_output"].set(f"{km_out} km")
        self.vars["journal"].set(f"Q=0x{self.src_info['q']:04X}, R={self.src_info['r']}, halves={self.src_info['prefix_halves']}/16")
        self.vars["coeff"].set({"MILES":self.t("coeff_miles"),"KM":self.t("coeff_km"),"?":self.t("coeff_unknown")}[self.coeff_state])
        self.vars["temp"].set({"F":self.t("temp_f"),"C":self.t("temp_c"),"?":self.t("temp_unknown")}[self.temp_state])
        self.vars["status"].set(self.t("valid"))
    def save_bin(self):
        if self.src is None:
            messagebox.showwarning(self.t("status"),self.t("choose_first")); return
        if not (self.opt_km.get() or self.opt_coeff.get() or self.opt_c.get()):
            messagebox.showwarning(self.t("status"),self.t("nothing")); return
        out=bytearray(self.src); km_exact=self.src_miles*1.609344; km_out=int(km_exact+0.5)
        if self.opt_km.get(): out[ODO_START:ODO_END]=encode_mileage(km_out)
        if self.opt_coeff.get():
            if self.coeff_state=="MILES": out[COEFF_START:COEFF_END]=COEFF_KM
            elif self.coeff_state!="KM": messagebox.showwarning(self.t("warning"),self.t("coeff_refuse"))
        if self.opt_c.get():
            if self.temp_state=="F": out[TEMP_START:TEMP_END]=TEMP_C
            elif self.temp_state!="C": messagebox.showwarning(self.t("warning"),self.t("temp_refuse"))
        default=f"{self.src_path.stem}_converted_v1.2.bin"
        name=filedialog.asksaveasfilename(title=self.t("save"),initialdir=str(self.src_path.parent),initialfile=default,defaultextension=".bin",filetypes=[("BIN","*.bin"),("All files","*.*")])
        if not name: return
        dst=Path(name)
        if dst.resolve()==self.src_path.resolve(): dst=dst.with_name(dst.stem+"_converted"+dst.suffix)
        out=bytes(out); dst.write_bytes(out)
        changed=[i for i,(a,b) in enumerate(zip(self.src,out)) if a!=b]
        if self.opt_report.get():
            rpt=dst.with_suffix(".txt")
            rpt.write_text(
                f"Subaru 85015FC660 / 93C56 x16\nConverter version: {APP_VERSION}\n\n"
                f"Source file: {self.src_path.name}\nDecoded source odometer: {self.src_miles}\n"
                f"Exact miles->km equivalent: {km_exact:.6f} km\nWritten odometer value: {km_out if self.opt_km.get() else 'unchanged'}\n"
                f"Pulse coefficient source: {self.coeff_state}\nTemperature source: {self.temp_state}\n"
                f"Changed bytes: {len(changed)}\nChanged offsets: {' '.join(f'{x:02X}' for x in changed)}\n\n"
                f"Miles coeff: {COEFF_MILES.hex(' ').upper()}\nKM coeff: {COEFF_KM.hex(' ').upper()}\n"
                f"F temp: {TEMP_F.hex(' ').upper()}\nC temp: {TEMP_C.hex(' ').upper()}\n",
                encoding="utf-8")
        messagebox.showinfo(self.t("saved"),self.t("saved_text").format(path=dst,count=len(changed)))

def self_test():
    for m in [271445,271610,271898,272079,272080,272081,436848,436917]:
        b=bytearray([0]*256); b[ODO_START:ODO_END]=encode_mileage(m)
        got,_=decode_mileage(bytes(b)); assert got==m

if __name__=="__main__":
    self_test()
    root=tk.Tk(); App(root); root.mainloop()
