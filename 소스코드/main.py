# main.py
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Tuple

from config import APP_TITLE, VERSION, SESSIONS, ROLE_COLOR
from utils import color_for
from data_models import Roster, Person
from reservation import ReservationPanel, UI

def _same_person(a: Optional[Person], b: Optional[Person]) -> bool:
    if a is None or b is None:
        return a is b
    return (a.name == b.name) and (a.phone == b.phone) and (a.role == b.role)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {VERSION}")
        self.geometry("1120x820")
        self.minsize(1000, 680)

        self.roster = Roster()

        self.slot_timers: Dict[Tuple[str,int], float] = {}

        self._global_running = False
        self._paused_now_ts: Optional[float] = time.time()
        self._tick_after = None

        self.slot_widgets: Dict[Tuple[str,int], tk.Label] = {}
        self.widget_to_slot: Dict[tk.Label, Tuple[str,int]] = {}
        self._drag_src: Optional[Tuple[str,int]] = None
        self._press_xy: Tuple[int,int] = (0,0)
        self._dragging: bool = False
        self._drag_offset: Tuple[int,int] = (0,0)
        self._ghost: Optional[tk.Toplevel] = None
        self._ghost_size: Tuple[int,int] = (0,0)
        self._highlight_target: Optional[Tuple[str,int]] = None

        self._build_menu()
        self._build_tabs()
        self._build_dashboard()
        self._build_settings()

        self._load_people_from_sheet()
        self._reset_all_slot_timers_to_now()
        self.refresh_dashboard()

    def _now(self) -> float:
        if not self._global_running and self._paused_now_ts is not None:
            return self._paused_now_ts
        return time.time()

    def _build_menu(self):
        menubar = tk.Menu(self)

        actionmenu = tk.Menu(menubar, tearoff=0)
        actionmenu.add_command(label="현재 세션 자동 할당", command=self.auto_assign_and_refresh)
        actionmenu.add_separator()
        actionmenu.add_command(label="종료", command=self.quit)
        menubar.add_cascade(label="동작", menu=actionmenu)

        self.config(menu=menubar)

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self)
        self.tab_dashboard = ttk.Frame(self.tabs)
        self.tab_settings  = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_dashboard, text="대시보드")
        self.tabs.add(self.tab_settings,  text="설정")
        self.tabs.pack(fill="both", expand=True)

    def _build_dashboard(self):
        parent = self.tab_dashboard

        topbar = ttk.Frame(parent); topbar.pack(side="top", fill="x", padx=10, pady=10)
        ttk.Label(topbar, text="세션:").pack(side="left")
        self.session_var = tk.StringVar(value=SESSIONS[0])
        self.session_cb = ttk.Combobox(topbar, textvariable=self.session_var, values=SESSIONS, state="readonly", width=20)
        self.session_cb.pack(side="left", padx=(5, 15))
        self.session_cb.bind("<<ComboboxSelected>>", self.on_session_changed)
        ttk.Button(topbar, text="자동 할당", command=self.auto_assign_and_refresh).pack(side="left")
        ttk.Label(topbar, text="    우주탐사공학실험 동아리 송파교육박람회 인원관리 프로그램").pack(side="left", padx=10)

        body = ttk.Frame(parent); body.pack(fill="both", expand=True, padx=10, pady=5)

        inside_frame = ttk.LabelFrame(body, text="내부 (8)")
        inside_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=5)
        body.grid_columnconfigure(0, weight=1); body.grid_columnconfigure(1, weight=0); body.grid_columnconfigure(2, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.inside_cells = []
        for r in range(4):
            for c in range(2):
                idx = r*2 + c
                lbl = tk.Label(inside_frame, text="(빈 자리)", bg=color_for("inside", "빈칸"),
                               relief="groove", bd=2, cursor="hand2", justify="center")
                lbl.grid(row=r, column=c, sticky="nsew", padx=6, pady=6, ipady=12)
                inside_frame.grid_columnconfigure(c, weight=1)
                inside_frame.grid_rowconfigure(r, weight=1)
                self._register_slot_widget(lbl, "inside", idx)
                self.inside_cells.append(lbl)

        legend_frame = ttk.Frame(body); legend_frame.grid(row=0, column=1, sticky="ns", pady=5)
        ttk.Label(legend_frame, text="역할 색상", font=("Segoe UI", 10, "bold")).pack(pady=(8,4))
        for role in ["부스", "홍보", "상주"]:
            swatch = tk.Label(legend_frame, text=f" {role} ", bg=ROLE_COLOR[role], relief="groove")
            swatch.pack(fill="x", padx=4, pady=4)
        ttk.Separator(legend_frame, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(legend_frame, text="부스 내에는\n반드시 상주인원이\n1명 이상 존재할 것", justify="center").pack()

        right_frame = ttk.Frame(body); right_frame.grid(row=0, column=2, sticky="nsew")

        outside_frame = ttk.LabelFrame(right_frame, text="외부 (3)")
        outside_frame.pack(fill="x", padx=0, pady=(0, 8))
        self.outside_cells = []
        for c in range(3):
            lbl = tk.Label(outside_frame, text="(빈 자리)", bg=color_for("outside", "빈칸"),
                           relief="groove", bd=2, cursor="hand2", justify="center")
            lbl.grid(row=0, column=c, sticky="nsew", padx=6, pady=6, ipady=12)
            outside_frame.grid_columnconfigure(c, weight=1)
            self._register_slot_widget(lbl, "outside", c)
            self.outside_cells.append(lbl)

        rest_frame = ttk.LabelFrame(right_frame, text="휴식 (3)")
        rest_frame.pack(fill="x", padx=0, pady=(0, 8))
        self.rest_cells = []
        for c in range(3):
            lbl = tk.Label(rest_frame, text="(빈 자리)", bg=color_for("rest", "빈칸"), relief="sunken", bd=2, justify="center")
            lbl.grid(row=0, column=c, sticky="nsew", padx=6, pady=6, ipady=12)
            rest_frame.grid_columnconfigure(c, weight=1)
            self._register_slot_widget(lbl, "rest", c)
            self.rest_cells.append(lbl)

        reserve_box = ttk.LabelFrame(right_frame, text="예약 (우주정거장 / 우주탐사차량)")
        reserve_box.pack(fill="both", expand=True, padx=0, pady=(0, 6))
        self.reservation_panel = ReservationPanel(reserve_box); self.reservation_panel.pack(fill="both", expand=True)

        self._build_global_stopwatch_bar(parent)

    def _register_slot_widget(self, lbl: tk.Label, area: str, index: int):
        self.slot_widgets[(area, index)] = lbl
        self.widget_to_slot[lbl] = (area, index)
        lbl.bind("<ButtonPress-1>", lambda e, a=area, i=index: self.on_slot_press(e, a, i))
        lbl.bind("<B1-Motion>", self.on_slot_motion)
        lbl.bind("<ButtonRelease-1>", lambda e, a=area, i=index: self.on_slot_release(e, a, i))

    def _build_global_stopwatch_bar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        style = ttk.Style(self); style.configure("Mini.TButton", padding=(6, 1))
        self.btn_sw_toggle = ttk.Button(bar, text="시작", width=8, style="Mini.TButton",
                                        command=self.toggle_global_stopwatch)
        self.btn_sw_toggle.pack(side="left")

        self.btn_sw_reset = ttk.Button(bar, text="초기화", width=8, style="Mini.TButton",
                                       command=self.reset_global_stopwatch)
        self.btn_sw_reset.pack(side="left", padx=(6, 0))

        self._sw_status = tk.StringVar(value="⏱ 정지")
        ttk.Label(bar, textvariable=self._sw_status, foreground="#444").pack(side="left", padx=(8, 0))

    def toggle_global_stopwatch(self):
        if self._global_running:
            self._paused_now_ts = time.time()
            self._global_running = False
            self._sw_status.set("⏱ 정지")
            self.btn_sw_toggle.config(text="시작")
            if self._tick_after:
                try: self.after_cancel(self._tick_after)
                except Exception: pass
                self._tick_after = None
        else:
            now = time.time()
            paused_gap = 0.0
            if self._paused_now_ts is not None:
                paused_gap = now - self._paused_now_ts
            if paused_gap > 1e-9:
                for k in list(self.slot_timers.keys()):
                    self.slot_timers[k] += paused_gap
            self._paused_now_ts = None
            self._global_running = True
            self._sw_status.set("⏱ 실행중")
            self.btn_sw_toggle.config(text="정지")
            self._start_tick_loop()
        self.refresh_dashboard()

    def reset_global_stopwatch(self):
        self._reset_all_slot_timers_to_now()
        self.refresh_dashboard()

    def _snapshot_layout(self) -> Dict[Tuple[str,int], Optional[Person]]:
        snap = {}
        for i in range(len(self.inside_cells)):  snap[("inside", i)] = self.roster.inside_slots[i]
        for i in range(len(self.outside_cells)): snap[("outside", i)] = self.roster.outside_slots[i]
        for i in range(len(self.rest_cells)):    snap[("rest", i)] = self.roster.rest_slots[i]
        return snap

    def _reset_all_slot_timers_to_now(self):
        now = self._now()
        for key, person in self._snapshot_layout().items():
            if person is not None: self.slot_timers[key] = now
            elif key in self.slot_timers: del self.slot_timers[key]

    def _update_slot_timers_after_change(self, prev: Dict[Tuple[str,int], Optional[Person]]):
        now = self._now()
        curr = self._snapshot_layout()
        for key, curp in curr.items():
            prevp = prev.get(key)
            if curp is None:
                if key in self.slot_timers: del self.slot_timers[key]
            else:
                if not _same_person(prevp, curp):
                    self.slot_timers[key] = now

    def _format_elapsed(self, key: Tuple[str,int]) -> str:
        ts = self.slot_timers.get(key)
        if ts is None: return ""
        sec = max(0, int(self._now() - ts))
        h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _start_tick_loop(self):
        if self._tick_after:
            try: self.after_cancel(self._tick_after)
            except Exception: pass
            self._tick_after = None
        if self._global_running:
            self._tick()

    def _tick(self):
        if not self._global_running: return
        self.refresh_dashboard()
        self._tick_after = self.after(1000, self._tick)

    def _create_ghost(self, src_lbl: tk.Label, text: str, bg: str):
        if self._ghost:
            try: self._ghost.destroy()
            except Exception: pass
            self._ghost = None
        self.update_idletasks()
        w = src_lbl.winfo_width()
        h = src_lbl.winfo_height()
        self._ghost_size = (w, h)

        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        try:
            ghost.wm_attributes("-topmost", True)
            ghost.wm_attributes("-alpha", 0.6)
        except Exception:
            pass
        frame = tk.Frame(ghost, bg=bg, bd=2, relief="ridge")
        frame.pack(fill="both", expand=True)
        lbl = tk.Label(frame, text=text, bg=bg, justify="center")
        lbl.pack(fill="both", expand=True, padx=4, pady=6)
        self._ghost = ghost

    def _move_ghost_to(self, x_root: int, y_root: int):
        if not self._ghost: return
        dx, dy = self._drag_offset
        x = x_root - dx
        y = y_root - dy
        w, h = self._ghost_size
        self._ghost.geometry(f"{w}x{h}+{x}+{y}")

    def _rect_for_widget(self, wdg: tk.Widget) -> Tuple[int,int,int,int]:
        x1 = wdg.winfo_rootx(); y1 = wdg.winfo_rooty()
        x2 = x1 + wdg.winfo_width(); y2 = y1 + wdg.winfo_height()
        return x1, y1, x2, y2

    def _target_slot_at(self, x_root: int, y_root: int, exclude: Tuple[str,int]) -> Optional[Tuple[str,int]]:
        for key, wdg in self.slot_widgets.items():
            if key == exclude:
                continue
            x1, y1, x2, y2 = self._rect_for_widget(wdg)
            if (x1 <= x_root <= x2) and (y1 <= y_root <= y2):
                return key
        return None

    def _set_highlight(self, target: Optional[Tuple[str,int]]):
        if self._highlight_target == target:
            return
        if self._highlight_target:
            area, idx = self._highlight_target
            w = self.slot_widgets[(area, idx)]
            default_relief = "sunken" if area == "rest" else "groove"
            w.config(bd=2, relief=default_relief)
        self._highlight_target = target
        if target:
            area, idx = target
            w = self.slot_widgets[(area, idx)]
            w.config(bd=4, relief="ridge")

    def on_slot_press(self, event, area, index):
        self._drag_src = (area, index)
        self._press_xy = (event.x_root, event.y_root)
        self._drag_offset = (event.x, event.y)
        self._dragging = False
        src_p = self._slot_person(area, index)
        if src_p:
            text = f"{src_p.name}\n{self._format_elapsed((area, index))}"
            bg = color_for(area, src_p.role)
            self._create_ghost(self.slot_widgets[(area, index)], text, bg)
            self._move_ghost_to(event.x_root, event.y_root)
        else:
            self._ghost = None

    def on_slot_motion(self, event):
        if self._drag_src is None:
            return
        dx = event.x_root - self._press_xy[0]; dy = event.y_root - self._press_xy[1]
        if (abs(dx) + abs(dy)) > 4:
            self._dragging = True
        if self._ghost:
            self._move_ghost_to(event.x_root, event.y_root)
            cand = self._target_slot_at(event.x_root, event.y_root, self._drag_src)
            if cand and self._dnd_is_potentially_valid(self._drag_src, cand):
                self._set_highlight(cand)
            else:
                self._set_highlight(None)

    def on_slot_release(self, event, area, index):
        if self._ghost:
            try: self._ghost.destroy()
            except Exception: pass
            self._ghost = None
        self._set_highlight(None)

        if self._drag_src is None:
            return

        if not self._dragging:
            self.handle_cell_click(area, index)
            self._drag_src = None
            return

        cand = self._target_slot_at(event.x_root, event.y_root, self._drag_src)
        src_area, src_idx = self._drag_src
        self._drag_src = None

        if not cand:
            return

        if not self._dnd_is_potentially_valid((src_area, src_idx), cand):
            sa = self._slot_type(src_area, src_idx)
            da = self._slot_type(cand[0], cand[1])
            if "상주" in (sa, da):
                UI.warn("교대 불가", "상주는 '부스 내 ↔ 부스 외' 슬롯끼리만 드래그 교대할 수 있습니다.")
            else:
                UI.warn("교대 불가", "부스/홍보는 '근무 슬롯 ↔ 휴식' 사이에서 동일 역할끼리만 교대할 수 있습니다.")
            return

        dst_area, dst_idx = cand
        self._attempt_drag_swap(src_area, src_idx, dst_area, dst_idx)

    def _slot_type(self, area: str, idx: int) -> str:
        if area == "inside":  return self.roster.inside_types[idx]
        if area == "outside": return self.roster.outside_types[idx]
        return self.roster.rest_types[idx]

    def _slot_person(self, area: str, idx: int) -> Optional[Person]:
        if area == "inside":  return self.roster.inside_slots[idx]
        if area == "outside": return self.roster.outside_slots[idx]
        return self.roster.rest_slots[idx]

    def _dnd_is_potentially_valid(self, src: Tuple[str,int], dst: Tuple[str,int]) -> bool:
        src_area, src_idx = src; dst_area, dst_idx = dst
        src_type = self._slot_type(src_area, src_idx)
        dst_type = self._slot_type(dst_area, dst_idx)
        src_p = self._slot_person(src_area, src_idx)
        dst_p = self._slot_person(dst_area, dst_idx)

        if src_p is None:
            return False

        if src_type == "상주" or dst_type == "상주":
            cond = ((src_area == "inside" and src_type == "상주" and dst_area == "outside" and dst_type == "상주") or
                    (dst_area == "inside" and dst_type == "상주" and src_area == "outside" and src_type == "상주"))
            return cond

        if "rest" not in (src_area, dst_area):
            return False
        work_area, work_idx = (src_area, src_idx) if src_area != "rest" else (dst_area, dst_idx)
        work_type = self._slot_type(work_area, work_idx)
        if work_type == "상주":
            return False

        rest_area, rest_idx = (src_area, src_idx) if src_area == "rest" else (dst_area, dst_idx)
        rest_p = self._slot_person(rest_area, rest_idx)
        if rest_p is None:
            return False

        return rest_p.role == work_type

    def _attempt_drag_swap(self, src_area: str, src_idx: int, dst_area: str, dst_idx: int):
        src_type = self._slot_type(src_area, src_idx)
        dst_type = self._slot_type(dst_area, dst_idx)
        src_p = self._slot_person(src_area, src_idx)
        dst_p = self._slot_person(dst_area, dst_idx)

        if src_p is None:
            return

        if "상주" in (src_type, dst_type):
            cond = ((src_area == "inside" and src_type == "상주" and dst_area == "outside" and dst_type == "상주") or
                    (dst_area == "inside" and dst_type == "상주" and src_area == "outside" and src_type == "상주"))
            if not cond:
                UI.warn("교대 불가", "상주는 '부스 내 ↔ 부스 외' 슬롯끼리만 드래그 교대할 수 있습니다.")
                return
            a = f"{src_p.name if src_p else '(empty)'}"
            b = f"{dst_p.name if dst_p else '(empty)'}"
            if not UI.ask_yesno("교대 확인", f"[상주] {a} ↔ {b} 교대하시겠습니까?"):
                return
            prev = self._snapshot_layout()
            if src_area == "inside":
                inside_idx, outside_idx = src_idx, dst_idx
            else:
                inside_idx, outside_idx = dst_idx, src_idx
            ok, msg = self.roster.swap_resident_inside_outside(inside_idx, outside_idx)
            if ok:
                self._update_slot_timers_after_change(prev)
                self.refresh_dashboard()
            else:
                UI.error("교대 실패", msg)
            return

        if not (("rest" in (src_area, dst_area)) and (("inside" in (src_area, dst_area)) or ("outside" in (src_area, dst_area)))): 
            UI.warn("교대 불가", "부스/홍보는 '근무 슬롯 ↔ 휴식' 사이에서만 드래그 교대할 수 있습니다.")
            return

        if src_area == "rest":
            rest_person = src_p
            work_area, work_idx = dst_area, dst_idx
            work_type = self._slot_type(work_area, work_idx)
        else:
            rest_person = dst_p
            work_area, work_idx = src_area, src_idx
            work_type = self._slot_type(work_area, work_idx)

        if work_type == "상주":
            UI.warn("교대 불가", "상주는 휴식과 교대할 수 없습니다.")
            return

        if rest_person is None:
            UI.warn("교대 불가", "해당 휴식 슬롯에 인원이 없습니다. 휴식 중인 동일 역할 인원과만 교대할 수 있습니다.")
            return

        if rest_person.role != work_type:
            UI.warn("교대 불가", f"이 근무 칸은 '{work_type}' 전용입니다. 동일 역할의 휴식 인원과만 교대할 수 있어요.")
            return

        a = f"{self._slot_person(work_area, work_idx).name if self._slot_person(work_area, work_idx) else '(empty)'}"
        b = f"{rest_person.name}"
        if not UI.ask_yesno("교대 확인", f"[{work_type}] {a} ↔ {b} 교대하시겠습니까?"):
            return

        prev = self._snapshot_layout()
        ok, msg = self.roster.swap_with_rest(work_area, work_idx, rest_person)
        if ok:
            self._update_slot_timers_after_change(prev)
            self.refresh_dashboard()
        else:
            UI.error("교대 실패", msg)

    def _build_settings(self):
        parent = self.tab_settings
        wrap = ttk.Frame(parent); wrap.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(wrap); left.pack(side="left", fill="both", expand=True)
        form = ttk.LabelFrame(left, text="인원 추가 (오늘)"); form.pack(fill="x", pady=(0, 8))

        self.entry_name = ttk.Entry(form, width=18)
        self.entry_phone = ttk.Entry(form, width=18)
        self.role_var = tk.StringVar(value="부스")
        self.sess1_var = tk.BooleanVar(value=True)
        self.sess2_var = tk.BooleanVar(value=True)

        ttk.Label(form, text="이름").grid(row=0, column=0, padx=4, pady=4, sticky="e")
        self.entry_name.grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(form, text="전화번호").grid(row=0, column=2, padx=4, pady=4, sticky="e")
        self.entry_phone.grid(row=0, column=3, padx=4, pady=4)

        ttk.Label(form, text="역할").grid(row=1, column=0, padx=4, pady=4, sticky="e")
        ttk.Combobox(form, textvariable=self.role_var, values=["부스", "홍보", "상주"], state="readonly", width=8).grid(row=1, column=1, padx=4, pady=4, sticky="w")

        ttk.Label(form, text="참여 시간").grid(row=1, column=2, padx=4, pady=4, sticky="e")
        ttk.Checkbutton(form, text="1부", variable=self.sess1_var).grid(row=1, column=3, padx=2, pady=4, sticky="w")
        ttk.Checkbutton(form, text="2부", variable=self.sess2_var).grid(row=1, column=4, padx=2, pady=4, sticky="w")

        ttk.Button(form, text="추가", command=self.add_person).grid(row=0, column=4, padx=6, pady=4, sticky="w")

        list_frame = ttk.LabelFrame(left, text="인원 목록 (Google Sheets와 동기화됨)"); list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, columns=("이름", "전화번호", "역할", "참여 시간"), show="headings", height=12)
        self.tree.heading("이름", text="이름"); self.tree.heading("전화번호", text="전화번호"); self.tree.heading("역할", text="역할"); self.tree.heading("참여 시간", text="참여 시간")
        self.tree.column("이름", width=100, anchor="center")
        self.tree.column("전화번호", width=110, anchor="center")
        self.tree.column("역할", width=60, anchor="center")
        self.tree.column("참여 시간", width=120, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.edit_selected_person)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side="right", fill="y")

        btns = ttk.Frame(left); btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="선택 삭제", command=self.delete_selected).pack(side="left")
        ttk.Button(btns, text="전체 삭제", command=self.clear_people).pack(side="left", padx=6)

        right = ttk.LabelFrame(wrap, text="세션별 목표 인원 (현장)")
        right.pack(side="left", fill="y", padx=(10,0))

        self.spins = {}
        for ridx, sess in enumerate(["1부", "2부"]):
            f = ttk.Frame(right)
            f.pack(fill="x", padx=8, pady=(8 if ridx==0 else 2, 6))
            ttk.Label(f, text=f"{sess} 목표").grid(row=0, column=0, padx=4, sticky="w")
            for cidx, role in enumerate(["부스", "홍보", "상주"]):
                ttk.Label(f, text=role).grid(row=1, column=cidx*2, padx=4, sticky="e")
                var = tk.IntVar(value=self.roster.targets[sess][role])
                spin = ttk.Spinbox(f, from_=0, to=99, width=5, textvariable=var, command=self._update_targets_from_spins)
                spin.grid(row=1, column=cidx*2+1, padx=(0,10), sticky="w")
                self.spins[(sess, role)] = var

        ttk.Button(right, text="적용 및 자동 할당", command=self.apply_targets_and_auto_assign).pack(pady=8)
        ttk.Label(right, text="송파교육박람회 우주탐사공학실험 동아리 인원관리 프로그램", justify="left").pack(padx=8, pady=6)

    def _load_people_from_sheet(self):
        try:
            self.roster.people = self.reservation_panel.helper.read_people()
            
            if not self.roster.people:
                if UI.ask_yesno("예시 데이터 추가", "스프레드시트의 '인원명단' 시트가 비어 있습니다. 예시 데이터를 추가할까요?"):
                    self._seed_example_data_to_sheet()
            
            self._refresh_people_tree()
            self.auto_assign_and_refresh()
        except Exception as e:
            UI.error("인원 명단 로딩 실패", f"스프레드시트에서 인원 명단을 불러오는 데 실패했습니다.\n\n{e}")
            self.roster.people = []
            self._refresh_people_tree()

    def _seed_example_data_to_sheet(self):
        examples = [
            ("상주A","010-0000-0001","상주", {"1부","2부"}),
            ("상주B","010-0000-0002","상주", {"1부","2부"}),
            ("상주C","010-0000-0003","상주", {"1부","2부"}),
            ("상주D","010-0000-0004","상주", {"1부","2부"}),
            ("상주E","010-0000-0005","상주", {"1부","2부"}),
            ("부스1","010-1000-0001","부스", {"1부","2부"}),
            ("부스2","010-1000-0002","부스", {"1부","2부"}),
            ("부스3","010-1000-0003","부스", {"1부","2부"}),
            ("부스4","010-1000-0004","부스", {"1부","2부"}),
            ("부스5","010-1000-0005","부스", {"1부","2부"}),
            ("부스6","010-1000-0006","부스", {"1부","2부"}),
            ("홍보1","010-2000-0001","홍보", {"1부","2부"}),
            ("홍보2","010-2000-0002","홍보", {"1부","2부"}),
            ("홍보3","010-2000-0003","홍보", {"1부","2부"}),
        ]
        for name, phone, role, sess in examples:
            self.roster.people.append(Person(name, phone, role, sess))
        
        self._sync_people_to_sheet()

    def _sync_people_to_sheet(self):
        try:
            self.reservation_panel.helper.write_people(self.roster.people)
        except Exception as e:
            UI.error("인원 명단 동기화 실패", f"스프레드시트에 인원 명단을 저장하는 데 실패했습니다.\n\n{e}")




    def add_person(self):
        name = self.entry_name.get().strip()
        phone = self.entry_phone.get().strip()
        role = self.role_var.get()
        sess = set()
        if self.sess1_var.get(): sess.add("1부")
        if self.sess2_var.get(): sess.add("2부")

        if not name:
            messagebox.showwarning("입력 오류", "이름을 입력하세요."); return
        if any(p.name == name for p in self.roster.people):
            messagebox.showwarning("입력 오류", f"'{name}' 이름은 이미 존재합니다. 다른 이름을 사용하세요."); return
        if role not in ("부스", "홍보", "상주"):
            messagebox.showwarning("입력 오류", "역할을 선택하세요."); return
        if not sess:
            messagebox.showwarning("입력 오류", "하나 이상의 참여 시간을 선택하세요."); return

        self.roster.people.append(Person(name, phone, role, sess))
        self.entry_name.delete(0, tk.END); self.entry_phone.delete(0, tk.END)
        self._refresh_people_tree()
        self._sync_people_to_sheet()

    def edit_selected_person(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        item_id = sel[0]
        
        old_name = self.tree.item(item_id, "values")[0]
        person_to_edit = next((p for p in self.roster.people if p.name == old_name), None)
        if not person_to_edit: return

        win = EditPersonWindow(self, person_to_edit, self.roster.people)
        self.wait_window(win)
        if win.saved:
            self._sync_people_to_sheet()
            self._refresh_people_tree()
            self.auto_assign_and_refresh()

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel: return
        
        if not messagebox.askyesno("삭제 확인", "선택된 인원을 삭제할까요? 이 작업은 스프레드시트에도 반영됩니다."):
            return

        for iid in sel:
            name_to_delete = self.tree.item(iid, "values")[0]
            self.roster.people = [p for p in self.roster.people if p.name != name_to_delete]
        
        self._refresh_people_tree()
        self._sync_people_to_sheet()
        self.auto_assign_and_refresh()

    def clear_people(self):
        if messagebox.askyesno("전체 삭제 확인", "모든 인원을 삭제할까요? 이 작업은 스프레드시트의 '인원명단' 시트를 비웁니다."):
            self.roster.people.clear()
            self._refresh_people_tree()
            self._sync_people_to_sheet()
            self.auto_assign_and_refresh()

    def _refresh_people_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for p in sorted(self.roster.people, key=lambda x: x.name):
            sessions_txt = ",".join(sorted(list(p.sessions)))
            self.tree.insert("", "end", values=(p.name, p.phone, p.role, sessions_txt))

    def _update_targets_from_spins(self):
        for (sess, role), var in self.spins.items():
            self.roster.targets[sess][role] = int(var.get())

    def apply_targets_and_auto_assign(self):
        self._update_targets_from_spins()
        self.auto_assign_and_refresh()

    def auto_assign_and_refresh(self):
        prev = self._snapshot_layout()
        warnings = self.roster.auto_assign()
        self._update_slot_timers_after_change(prev)
        self.refresh_dashboard()
        if warnings:
            messagebox.showwarning("Warning", "\n".join(warnings))

    def on_session_changed(self, event=None):
        text = self.session_var.get()
        self.roster.current_session = "1부" if text.startswith("1부") else "2부"
        self.auto_assign_and_refresh()

    def refresh_dashboard(self):
        for i, lbl in enumerate(self.inside_cells):
            p = self.roster.inside_slots[i]
            slot_role = self.roster.inside_types[i]
            if p:
                elapsed = self._format_elapsed(("inside", i))
                lbl.config(text=f"{p.name}\n{elapsed}", bg=color_for("inside", p.role))
            else:
                lbl.config(text=f"(empty)\n<{slot_role}>")
        for i, lbl in enumerate(self.outside_cells):
            p = self.roster.outside_slots[i]
            slot_role = self.roster.outside_types[i]
            if p:
                elapsed = self._format_elapsed(("outside", i))
                lbl.config(text=f"{p.name}\n{elapsed}", bg=color_for("outside", p.role))
            else:
                lbl.config(text=f"(empty)\n<{slot_role}>")
        for i, lbl in enumerate(self.rest_cells):
            p = self.roster.rest_slots[i]
            slot_role = self.roster.rest_types[i]
            if p:
                elapsed = self._format_elapsed(("rest", i))
                lbl.config(text=f"{p.name}\n{elapsed}", bg=color_for("rest", p.role))
            else:
                lbl.config(text=f"(empty)\n<{slot_role}>")

    def handle_cell_click(self, area, index):
        if area == "rest": return # 휴식 슬롯은 클릭으로 교대하지 않음

        if area == "inside":
            slot_role = self.roster.inside_types[index]
            occupant = self.roster.inside_slots[index]
        else: # outside
            slot_role = self.roster.outside_types[index]
            occupant = self.roster.outside_slots[index]

        if slot_role == "상주":
            self._handle_resident_swap_click(area, index, occupant)
        else: # 부스, 홍보
            self._handle_role_swap_click(area, index, slot_role, occupant)

    def _handle_resident_swap_click(self, area, index, occupant):
        if area == "inside":
            try:
                out_idx = self.roster.outside_types.index("상주")
                candidate = self.roster.outside_slots[out_idx]
            except ValueError:
                messagebox.showinfo("오류", "외부 상주 슬롯이 설정되지 않았습니다.")
                return

            if not candidate:
                messagebox.showinfo("교대 불가", "현재 부스 외 상주 인원이 없습니다.")
                return

            current_txt = f"{occupant.name} ({occupant.phone})" if occupant else "(빈 자리)"
            win = tk.Toplevel(self)
            win.title("상주 교대 (내부 ↔ 외부)")
            win.transient(self); win.grab_set()
            ttk.Label(win, text=f"선택된 칸: inside #{index+1} / 역할: 상주").pack(padx=10, pady=(10,4))
            ttk.Label(win, text=f"현재: {current_txt}").pack(padx=10, pady=(0,8))
            ttk.Label(win, text=f"교대 대상(외부): {candidate.name} ({candidate.phone})").pack(padx=10, pady=(0,8))

            def do_swap():
                prev = self._snapshot_layout()
                ok, msg = self.roster.swap_resident_inside_outside(index, out_idx)
                if ok:
                    self._update_slot_timers_after_change(prev)
                    self.refresh_dashboard(); win.destroy()
                else:
                    messagebox.showerror("교대 실패", msg)

            btns = ttk.Frame(win); btns.pack(pady=8)
            ttk.Button(btns, text="교대", command=do_swap).pack(side="left", padx=6)
            ttk.Button(btns, text="닫기", command=win.destroy).pack(side="left", padx=6)

        else:  # area == "outside"
            in_indices = [i for i, t in enumerate(self.roster.inside_types) if t == "상주"]
            candidates = [(i, self.roster.inside_slots[i]) for i in in_indices if self.roster.inside_slots[i] is not None]
            if not candidates:
                messagebox.showinfo("교대 불가", "현재 부스 내 상주 인원이 없습니다.")
                return

            win = tk.Toplevel(self)
            win.title("상주 교대 (외부 ↔ 내부)")
            win.transient(self); win.grab_set()
            occ_txt = f"{occupant.name} ({occupant.phone})" if occupant else "(빈 자리)"
            ttk.Label(win, text=f"선택된 칸: outside #{index+1} / 역할: 상주").pack(padx=10, pady=(10,4))
            ttk.Label(win, text=f"현재(외부): {occ_txt}").pack(padx=10, pady=(0,8))

            frame = ttk.Frame(win); frame.pack(fill="both", expand=True, padx=10, pady=4)
            cols = ("idx","name","phone")
            tree = ttk.Treeview(frame, columns=cols, show="headings", height=6, selectmode="browse")
            tree.heading("idx", text="내부#"); tree.heading("name", text="이름"); tree.heading("phone", text="전화번호")
            tree.column("idx", width=60, anchor="center"); tree.column("name", width=120); tree.column("phone", width=120)
            tree.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")

            for i, p in candidates:
                tree.insert("", "end", iid=str(i), values=(i+1, p.name, p.phone))

            def do_swap():
                sel = tree.selection()
                if not sel:
                    messagebox.showwarning("선택", "교대할 내부 상주를 선택하세요.")
                    return
                inside_idx = int(sel[0])
                prev = self._snapshot_layout()
                ok, msg = self.roster.swap_resident_inside_outside(inside_idx, index)
                if ok:
                    self._update_slot_timers_after_change(prev)
                    self.refresh_dashboard(); win.destroy()
                else:
                    messagebox.showerror("교대 실패", msg)

            btns = ttk.Frame(win); btns.pack(pady=8)
            ttk.Button(btns, text="교대", command=do_swap).pack(side="left", padx=6)
            ttk.Button(btns, text="닫기", command=win.destroy).pack(side="left", padx=6)

    def _handle_role_swap_click(self, area, index, slot_role, occupant):
        rest_candidates = [p for p in self.roster.rest_slots if p and p.role == slot_role]
        if not rest_candidates:
            messagebox.showinfo("교대 불가", f"휴식 중인 '{slot_role}' 인원이 없습니다.")
            return

        win = tk.Toplevel(self)
        win.title("교대 (휴식 ↔ 배치)")
        win.transient(self); win.grab_set()

        area_txt = "내부" if area == "inside" else "외부"
        ttk.Label(win, text=f"선택된 칸: {area_txt} #{index+1} / 역할: {slot_role}").pack(padx=10, pady=(10,4))
        occ_txt = f"{occupant.name} ({occupant.phone})" if occupant else "(빈 자리)"
        ttk.Label(win, text=f"현재: {occ_txt}").pack(padx=10, pady=(0,8))

        frame = ttk.Frame(win); frame.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("name","phone")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=6, selectmode="browse")
        tree.heading("name", text="휴식 중"); tree.heading("phone", text="전화번호")
        tree.column("name", width=140); tree.column("phone", width=120)
        tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")

        for p in rest_candidates:
            tree.insert("", "end", iid=p.name, values=(p.name, p.phone))

        def confirm_swap():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("선택", "교대할 휴식 인원을 선택하세요."); return
            
            name = tree.item(sel[0], "values")[0]
            rp = next((p for p in rest_candidates if p.name == name), None)
            
            prev = self._snapshot_layout()
            ok, msg = self.roster.swap_with_rest(area, index, rp)
            if ok:
                self._update_slot_timers_after_change(prev)
                self.refresh_dashboard(); win.destroy()
            else:
                messagebox.showerror("교대 실패", msg)

        btns = ttk.Frame(win); btns.pack(pady=8)
        ttk.Button(btns, text="교대", command=confirm_swap).pack(side="left", padx=6)
        ttk.Button(btns, text="닫기", command=win.destroy).pack(side="left", padx=6)


class EditPersonWindow(tk.Toplevel):
    def __init__(self, parent, person: Person, all_people: list[Person]):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("인원 정보 수정")

        self.person = person
        self.all_people = all_people
        self.saved = False

        self.name_var = tk.StringVar(value=person.name)
        self.phone_var = tk.StringVar(value=person.phone)
        self.role_var = tk.StringVar(value=person.role)
        self.sess1_var = tk.BooleanVar(value="1부" in person.sessions)
        self.sess2_var = tk.BooleanVar(value="2부" in person.sessions)

        form = ttk.Frame(self); form.pack(padx=15, pady=10)

        ttk.Label(form, text="이름").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        name_entry = ttk.Entry(form, textvariable=self.name_var, width=20)
        name_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form, text="전화번호").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(form, textvariable=self.phone_var, width=20).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(form, text="역할").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        ttk.Combobox(form, textvariable=self.role_var, values=["부스", "홍보", "상주"], state="readonly", width=10).grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(form, text="참여 시간").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        s_frame = ttk.Frame(form)
        s_frame.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(s_frame, text="1부", variable=self.sess1_var).pack(side="left")
        ttk.Checkbutton(s_frame, text="2부", variable=self.sess2_var).pack(side="left", padx=5)

        btn_frame = ttk.Frame(self); btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="저장", command=self.save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        name_entry.focus_set()
        name_entry.select_range(0, tk.END)

    def save(self):
        new_name = self.name_var.get().strip()
        new_phone = self.phone_var.get().strip()
        new_role = self.role_var.get()
        new_sessions = set()
        if self.sess1_var.get(): new_sessions.add("1부")
        if self.sess2_var.get(): new_sessions.add("2부")

        if not new_name:
            messagebox.showwarning("입력 오류", "이름을 입력하세요.", parent=self)
            return
        
        if new_name != self.person.name and any(p.name == new_name for p in self.all_people):
            messagebox.showwarning("입력 오류", f"'{new_name}' 이름은 이미 존재합니다. 다른 이름을 사용하세요.", parent=self)
            return

        if not new_sessions:
            messagebox.showwarning("입력 오류", "하나 이상의 참여 시간을 선택하세요.", parent=self)
            return

        self.person.name = new_name
        self.person.phone = new_phone
        self.person.role = new_role
        self.person.sessions = new_sessions
        
        self.saved = True
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
