# reservation.py
import json
import os
import datetime as dt
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Optional, Tuple

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import (
    SPREADSHEET_NAME, WORKSHEET_NAME_DATA, WORKSHEET_NAME_CONF,
    WORKSHEET_NAME_PEOPLE, PEOPLE_HEADERS,
    CATEGORIES, HEADERS, CHECK_DONE, CHECK_EMPTY, THRESHOLDS
)
from data_models import Person
from utils import google_credentials_path

class GSpreadHelper:
    def __init__(self, credentials_path: str, spreadsheet_name: str):
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, self.scope)
        self.client = gspread.authorize(self.creds)
        self.spreadsheet = self.client.open(spreadsheet_name)
        self.data_sheet = self._get_or_create_worksheet(WORKSHEET_NAME_DATA, HEADERS)
        self.conf_sheet = self._get_or_create_worksheet(WORKSHEET_NAME_CONF, ["키", "값"])
        self.people_sheet = self._get_or_create_worksheet(WORKSHEET_NAME_PEOPLE, PEOPLE_HEADERS)

    def _get_or_create_worksheet(self, sheet_name: str, header: List[str]) -> gspread.Worksheet:
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")
            sheet.append_row(header)
        return sheet

    def read_people(self) -> List[Person]:
        records = self.people_sheet.get_all_records()
        people = []
        for r in records:
            name = r.get("이름", "").strip()
            if not name:
                continue
            phone = r.get("전화번호", "")
            role = r.get("역할", "")
            sessions_str = r.get("참여시간", "")
            sessions = {s.strip() for s in sessions_str.split(",") if s.strip()}
            people.append(Person(name, phone, role, sessions))
        return people

    def write_people(self, people: List[Person]):
        self.people_sheet.clear()
        self.people_sheet.append_row(PEOPLE_HEADERS)
        rows = []
        for p in sorted(people, key=lambda x: x.name):
            sessions_str = ",".join(sorted(list(p.sessions)))
            rows.append([p.name, p.phone, p.role, sessions_str])
        if rows:
            self.people_sheet.append_rows(rows)

    def read_targets(self) -> Dict[str, Dict[str, int]]:
        records = self.conf_sheet.get_all_records()
        data = {r["키"]: r["값"] for r in records}
        targets = {
            "1부": {"부스": 0, "홍보": 0, "상주": 0},
            "2부": {"부스": 0, "홍보": 0, "상주": 0},
        }
        for sess in ["1부", "2부"]:
            for role in ["부스", "홍보", "상주"]:
                key = f"target_{sess}_{role}"
                if key in data:
                    try:
                        targets[sess][role] = int(data[key])
                    except (ValueError, TypeError):
                        pass # Keep default 0 if value is not a valid int
        return targets

    def write_targets(self, targets: Dict[str, Dict[str, int]]):
        all_keys = self.conf_sheet.col_values(1)
        for sess, roles in targets.items():
            for role, val in roles.items():
                key = f"target_{sess}_{role}"
                try:
                    row_idx = all_keys.index(key) + 1
                    self.conf_sheet.update_cell(row_idx, 2, int(max(0, val)))
                except ValueError:
                    self.conf_sheet.append_row([key, int(max(0, val))])
                    all_keys.append(key) # Avoid re-reading the sheet


    def read_rows(self) -> List[Dict]:
        records = self.data_sheet.get_all_records()
        # gspread는 빈 행을 건너뛰므로, 각 행에 원본 시트의 행 번호를 주입해줘야 합니다.
        # get_all_values()를 쓰고 직접 파싱하는 것이 더 안정적입니다.
        values = self.data_sheet.get_all_values()
        header = values[0]
        rows = []
        for i, row_values in enumerate(values[1:], start=2):
            row_dict = dict(zip(header, row_values))
            row_dict["_sheet_row"] = i
            # 참여 여부를 boolean으로 변환
            row_dict["참여"] = (row_dict.get("참여") == str(True))
            rows.append(row_dict)
        return rows

    def next_id(self) -> int:
        ids = self.data_sheet.col_values(1)[1:] # ID 컬럼, 헤더 제외
        if not ids:
            return 1
        max_id = 0
        for i in ids:
            try:
                max_id = max(max_id, int(i))
            except (ValueError, TypeError):
                continue
        return max_id + 1

    def get_capacities(self) -> Dict[str, int]:
        records = self.conf_sheet.get_all_records()
        data = {r["키"]: r["값"] for r in records}
        return {
            CATEGORIES[0]: int(data.get(f"capacity_{CATEGORIES[0]}", 0)),
            CATEGORIES[1]: int(data.get(f"capacity_{CATEGORIES[1]}", 0)),
        }

    def set_capacities(self, a: int, b: int) -> None:
        keys = self.conf_sheet.col_values(1)
        for cat, val in zip(CATEGORIES, (a,b)):
            key = f"capacity_{cat}"
            try:
                row_idx = keys.index(key) + 1
                self.conf_sheet.update_cell(row_idx, 2, int(max(0, val)))
            except ValueError:
                self.conf_sheet.append_row([key, int(max(0, val))])

    def count_by_category(self) -> Dict[str, int]:
        records = self.data_sheet.get_all_records()
        counts = {CATEGORIES[0]:0, CATEGORIES[1]:0}
        for r in records:
            if r["체험"] in counts:
                counts[r["체험"]] += 1
        return counts

    def remaining_by_category(self) -> Dict[str, int]:
        caps = self.get_capacities()
        cnt = self.count_by_category()
        return {
            CATEGORIES[0]: max(0, caps[CATEGORIES[0]] - cnt[CATEGORIES[0]]),
            CATEGORIES[1]: max(0, caps[CATEGORIES[1]] - cnt[CATEGORIES[1]]),
        }

    def append_row(self, data: Dict) -> None:
        # HEADERS 순서에 맞게 값을 채워넣어야 합니다.
        row_values = [data.get(h, None) for h in HEADERS]
        self.data_sheet.append_row(row_values)
        self.update_duplicate_last4_highlight()

    def set_participated(self, sheet_row: int, participated: bool) -> None:
        # 참여 여부 업데이트 (6번째 컬럼)
        self.data_sheet.update_cell(sheet_row, 6, str(participated))
        # 참여 시각 업데이트 (7번째 컬럼)
        now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if participated else ""
        self.data_sheet.update_cell(sheet_row, 7, now_str)

        # 취소선 및 회색 배경 적용
        format_rules = self.data_sheet.spreadsheet.get_worksheet_format(self.data_sheet.title)
        
        # 기존 규칙 제거 (해당 행에 대한)
        if 'sheets' in format_rules:
            sheet_format = next((s for s in format_rules['sheets'] if s.get('properties', {}).get('sheetId') == self.data_sheet.id), None)
            if sheet_format and 'conditionalFormats' in sheet_format:
                # gspread에서 직접 규칙을 다루기 복잡하므로, 여기서는 간단히 셀 포맷팅만 시도합니다.
                # 복잡한 조건부 서식은 gspread에서 직접 지원하지 않을 수 있습니다.
                # 대신, 셀의 기본 형식을 변경합니다.
                pass # gspread v5.3.0+ 에서는 batch_format 사용 가능

        if participated:
            self.data_sheet.format(f'C{sheet_row}:E{sheet_row}', {
                "textFormat": {"strikethrough": True},
                "backgroundColor": {"red": 0.6, "green": 0.6, "blue": 0.6}
            })
        else:
            self.data_sheet.format(f'C{sheet_row}:E{sheet_row}', {
                "textFormat": {"strikethrough": False},
                "backgroundColor": {"red": 1, "green": 1, "blue": 1}
            })
        self.update_duplicate_last4_highlight()

    def delete_row(self, sheet_row: int) -> None:
        self.data_sheet.delete_rows(sheet_row)
        self.update_duplicate_last4_highlight()

    def update_duplicate_last4_highlight(self):
        # gspread로는 조건부 서식을 직접 제어하기가 매우 복잡합니다.
        # 여기서는 모든 전화번호를 읽어와서 중복되는 번호를 찾고,
        # 해당 번호를 가진 모든 행의 배경색을 직접 노란색으로 칠합니다.
        # 참여한 행은 제외합니다.
        all_values = self.data_sheet.get_all_values()
        if len(all_values) < 2: return

        header = all_values[0]
        try:
            last4_idx = header.index("전화뒷4자리")
            participated_idx = header.index("참여")
        except ValueError:
            return # 필요한 컬럼이 없음

        counts: Dict[str, int] = {}
        rows_by_last4: Dict[str, List[int]] = {}

        for i, row in enumerate(all_values[1:], start=2):
            last4 = row[last4_idx]
            if not last4: continue
            counts[last4] = counts.get(last4, 0) + 1
            if last4 not in rows_by_last4:
                rows_by_last4[last4] = []
            rows_by_last4[last4].append(i)

        # 포맷팅 초기화 및 적용
        # gspread에서 모든 셀의 포맷을 초기화하는 것은 비용이 크므로,
        # 중복이 있는 번호에 대해서만 포맷을 적용/제거합니다.
        
        # 이 부분은 API 호출이 많아져 성능 저하의 원인이 될 수 있습니다.
        # 실제 운영 환경에서는 batchUpdate를 사용해야 합니다.
        
        # 간단하게 구현하기 위해, 중복 하이라이트는 기능에서 제외하거나
        # 사용자가 수동으로 확인하도록 안내하는 것이 나을 수 있습니다.
        # 여기서는 로직만 남겨둡니다.
        pass


# --- UI Components ---
class UI:
    @staticmethod
    def info(t, m): messagebox.showinfo(t, m)
    @staticmethod
    def warn(t, m): messagebox.showwarning(t, m)
    @staticmethod
    def error(t, m): messagebox.showerror(t, m)
    @staticmethod
    def ask_yesno(t, m) -> bool: return messagebox.askyesno(t, m)

class ListWindow(tk.Toplevel):
    def __init__(self, master, helper: GSpreadHelper, on_change_callback=None):
        super().__init__(master)
        self.title("예약자 명단")
        self.geometry("820x540")
        self.resizable(True, True)
        self.helper = helper
        self.on_change = on_change_callback

        top = ttk.Frame(self, padding=(10,6)); top.pack(fill="x")
        ttk.Label(top, text="검색(이름/전화번호)").pack(side="left")
        self.var_query = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.var_query, width=24); ent.pack(side="left", padx=6)
        ent.bind("<Return>", lambda e: self.refresh())
        ttk.Button(top, text="검색", command=self.refresh).pack(side="left")
        ttk.Button(top, text="초기화", command=self._reset_search).pack(side="left", padx=(6,0))
        ttk.Button(top, text="새로고침", command=self.refresh).pack(side="right")

        cols = ("ID","시간","이름","전화뒷4자리","체험","참여")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (60,160,160,110,160,70)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center")
        self.tree.tag_configure('participated', background='#9e9e9e', foreground='white')
        self.tree.tag_configure('dup', background='#fff59d')

        self.tree.pack(fill="both", expand=True, padx=10, pady=(0,6))
        self.tree.bind("<Double-1>", self.on_toggle_participated)

        bottom = ttk.Frame(self, padding=(10,6)); bottom.pack(fill="x")
        ttk.Button(bottom, text="참여 체크/해제", command=self.on_toggle_participated).pack(side="left")
        ttk.Button(bottom, text="삭제(선택)", command=self.on_delete_selected).pack(side="left", padx=(8,0))

        self.refresh()

    def _reset_search(self):
        self.var_query.set(""); self.refresh()

    def refresh(self):
        query = self.var_query.get().strip()
        for i in self.tree.get_children(): self.tree.delete(i)
        
        try:
            rows = self.helper.read_rows()
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"스프레드시트 데이터를 읽어오는 데 실패했습니다.\n{e}")
            return

        counts = {}
        for r in rows:
            k = str(r.get("전화뒷4자리")) if r.get("전화뒷4자리") is not None else None
            if k: counts[k] = counts.get(k,0)+1
        dup_set = {k for k, c in counts.items() if c >= 2}

        for r in rows:
            name = str(r.get("이름", ""))
            phone = str(r.get("전화뒷4자리", ""))
            if query and (query not in name and query not in phone): continue
            
            check = CHECK_DONE if r.get("참여") else CHECK_EMPTY
            iid = str(r["_sheet_row"])
            tags = []
            if r.get("참여"): tags.append('participated')
            else:
                if phone in dup_set:
                    tags.append('dup')
            
            self.tree.insert("", "end", iid=iid,
                             values=(r.get("ID"), r.get("시간"), name, phone, r.get("체험"), check),
                             tags=tags)

    def on_toggle_participated(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        sheet_row = int(sel[0])
        
        rows = self.helper.read_rows()
        row = next((r for r in rows if r["_sheet_row"] == sheet_row), None)
        if row is None: return
        
        try:
            self.helper.set_participated(sheet_row, not row["참여"])
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"참여 상태를 업데이트하는 데 실패했습니다.\n{e}")
            return
        self.refresh()
        if self.on_change: self.on_change()

    def on_delete_selected(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        sheet_row = int(sel[0])
        if not UI.ask_yesno("삭제 확인", "선택된 예약을 완전히 삭제할까요? (되돌릴 수 없음)"):
            return
        try:
            self.helper.delete_row(sheet_row)
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"행을 삭제하는 데 실패했습니다.\n{e}")
            return
        self.refresh()
        if self.on_change: self.on_change()

class ReservationPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        try:
            credentials_path = google_credentials_path()
            print(f"DEBUG: Attempting to load credentials from: {credentials_path}") # 디버깅 출력 추가
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Google 인증 키 파일이 없습니다: {credentials_path}")
            self.helper = GSpreadHelper(credentials_path, SPREADSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            credentials_path = google_credentials_path()
            client_email = "알 수 없음"
            try:
                with open(credentials_path, "r", encoding="utf-8") as f:
                    creds_data = json.load(f)
                    client_email = creds_data.get("client_email", "JSON 파일에서 이메일을 찾을 수 없습니다.")
            except Exception:
                pass

            error_message = (
                f"Google 스프레드시트를 찾을 수 없습니다.\n\n"
                f"시트 이름: '{SPREADSHEET_NAME}'\n\n"
                "해결 방법:\n"
                "1. Google 스프레드시트의 이름이 위와 일치하는지 확인하세요.\n"
                "2. 아래 서비스 계정 이메일 주소에 스프레드시트의 '편집자' 권한을 부여했는지 확인하세요.\n\n"
                f"서비스 계정 이메일 (복사해서 사용하세요):\n{client_email}"
            )
            UI.error("스프레드시트 찾기 실패", error_message)
            self.master.after(100, self.master.quit)
            return
        except Exception as e:
            error_str = str(e).lower()
            is_api_error = ("api" in error_str and "not enabled" in error_str) or \
                           ("permission" in error_str and "denied" in error_str)

            if is_api_error:
                error_message = (
                    "Google API 인증에 실패했습니다.\n\n"
                    "오류 원인:\n"
                    "Google Cloud 프로젝트에서 'Google Drive API' 또는 'Google Sheets API'가 활성화되지 않았을 가능성이 높습니다.\n\n"
                    "해결 방법:\n"
                    "1. Google Cloud Console(console.cloud.google.com)에 접속합니다.\n"
                    "2. 올바른 프로젝트를 선택했는지 확인합니다.\n"
                    "3. 'API 및 서비스' > '라이브러리'로 이동합니다.\n"
                    "4. 'Google Drive API'를 검색하여 '사용 설정'합니다.\n"
                    "5. 'Google Sheets API'를 검색하여 '사용 설정'합니다.\n\n"
                    f"자세한 오류 내용:\n{e}"
                )
                UI.error("Google API 인증 실패", error_message)
            else:
                # The user reported "response 200", which could mean many things.
                # Let's add a bit more guidance for the generic case.
                error_message = (
                    f"프로그램을 시작할 수 없습니다.\nGoogle API 인증 중 예기치 않은 오류가 발생했습니다.\n\n"
                    "가능한 원인:\n"
                    "1. 인터넷 연결이 불안정합니다.\n"
                    "2. 방화벽이 Google 서비스 연결을 차단하고 있습니다.\n"
                    "3. 인증 정보(JSON 키 파일)가 올바르지 않거나 만료되었습니다.\n\n"
                    f"오류 상세 정보:\n{e}"
                )
                UI.error("초기화 오류", error_message)

            self.master.after(100, self.master.quit)
            return

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)
        self.page_main = ttk.Frame(nb); self.page_settings = ttk.Frame(nb)
        nb.add(self.page_main, text="예약"); nb.add(self.page_settings, text="설정")

        self._build_main(); self._build_settings(); self.refresh_availability()

    def _build_main(self):
        frm = ttk.Frame(self.page_main, padding=8); frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="이름").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.ent_name = ttk.Entry(frm, width=18); self.ent_name.grid(row=0, column=1, sticky="w", pady=(0, 6))

        ttk.Label(frm, text="전화번호 뒤 4자리").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.ent_last4 = ttk.Entry(frm, width=18); self.ent_last4.grid(row=1, column=1, sticky="w", pady=(0, 6))

        ttk.Label(frm, text="체험 선택").grid(row=2, column=0, sticky="w")
        self.var_cat = tk.StringVar(value=CATEGORIES[0])
        self.label_text = {cat: tk.StringVar(value=cat) for cat in CATEGORIES}
        self.rb_cat = {}
        for i, cat in enumerate(CATEGORIES):
            rb = ttk.Radiobutton(frm, textvariable=self.label_text[cat], value=cat, variable=self.var_cat)
            rb.grid(row=2+i, column=1, sticky="w"); self.rb_cat[cat] = rb

        btns = ttk.Frame(frm); btns.grid(row=4, column=1, sticky="we", pady=(8,0))
        ttk.Button(btns, text="저장", command=self.on_save).pack(side="left")
        ttk.Button(btns, text="예약자 명단", command=self.open_list_window).pack(side="left", padx=(8,0))
        
        note = "스프레드시트와 실시간으로 연동됩니다."
        ttk.Label(frm, text=note, foreground="#666").grid(row=5, column=0, columnspan=2, sticky="w", pady=(8,0))

        for i in range(2): frm.columnconfigure(i, weight=1)
        self._list_win = None

    def _build_settings(self):
        frm = ttk.Frame(self.page_settings, padding=8); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="체험 정원 설정").grid(row=0, column=0, columnspan=2, sticky="w")
        self.var_cap = {CATEGORIES[0]: tk.IntVar(value=0), CATEGORIES[1]: tk.IntVar(value=0)}
        ttk.Label(frm, text=f"{CATEGORIES[0]} 정원").grid(row=1, column=0, sticky="e", pady=2)
        ttk.Spinbox(frm, from_=0, to=9999, textvariable=self.var_cap[CATEGORIES[0]], width=8).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(frm, text=f"{CATEGORIES[1]} 정원").grid(row=2, column=0, sticky="e", pady=2)
        ttk.Spinbox(frm, from_=0, to=9999, textvariable=self.var_cap[CATEGORIES[1]], width=8).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Button(frm, text="적용(저장)", command=self.on_apply_caps).grid(row=3, column=1, sticky="w", pady=(6,4))
        self.var_status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.var_status, foreground="#333").grid(row=4, column=0, columnspan=2, sticky="w", pady=(6,4))
        ttk.Button(frm, text="현황 새로고침", command=self.refresh_status).grid(row=5, column=1, sticky="w")

        for c in range(2): frm.columnconfigure(c, weight=1)
        
        try:
            caps = self.helper.get_capacities()
            self.var_cap[CATEGORIES[0]].set(caps[CATEGORIES[0]])
            self.var_cap[CATEGORIES[1]].set(caps[CATEGORIES[1]])
            self.refresh_status()
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"설정 값을 불러오는 데 실패했습니다.\n{e}")


    def refresh_availability(self):
        try:
            rem = self.helper.remaining_by_category()
            for cat in CATEGORIES:
                self.label_text[cat].set(f"{cat} (잔여 {rem[cat]})")
                if rem[cat] > 0: self.rb_cat[cat].state(["!disabled"])
                else: self.rb_cat[cat].state(["disabled"])
            if self.var_cat.get() in CATEGORIES and rem.get(self.var_cat.get(), 0) == 0:
                other = CATEGORIES[1] if self.var_cat.get() == CATEGORIES[0] else CATEGORIES[0]
                if rem.get(other, 0) > 0: self.var_cat.set(other)
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"잔여 인원 정보를 새로고침하지 못했습니다.\n{e}")


    def refresh_status(self):
        try:
            caps = self.helper.get_capacities()
            counts = self.helper.count_by_category()
            rem = self.helper.remaining_by_category()
            msg = (f"{CATEGORIES[0]}: 정원 {caps.get(CATEGORIES[0],0)} / 예약 {counts.get(CATEGORIES[0],0)} / 잔여 {rem.get(CATEGORIES[0],0)}\n"
                   f"{CATEGORIES[1]}: 정원 {caps.get(CATEGORIES[1],0)} / 예약 {counts.get(CATEGORIES[1],0)} / 잔여 {rem.get(CATEGORIES[1],0)}")
            self.var_status.set(msg)
            self.refresh_availability()
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"현황 정보를 새로고침하지 못했습니다.\n{e}")

    def on_apply_caps(self):
        a = int(self.var_cap[CATEGORIES[0]].get()); b = int(self.var_cap[CATEGORIES[1]].get())
        try:
            self.helper.set_capacities(a, b)
            self.refresh_status()
            UI.info("설정 저장", "정원이 저장되었습니다.")
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"정원을 저장하지 못했습니다.\n{e}")

    def validate_inputs(self) -> Optional[Tuple[str, str, str]]:
        name = self.ent_name.get().strip()
        last4 = self.ent_last4.get().strip()
        cat = self.var_cat.get().strip()
        if not name:
            UI.warn("검증", "이름을 입력하세요."); return None
        if not (last4.isdigit() and len(last4) == 4):
            UI.warn("검증", "전화번호 뒷 4자리를 숫자 4자리로 입력하세요."); return None
        if cat not in CATEGORIES:
            UI.warn("검증", "체험을 선택하세요."); return None
        
        try:
            rem = self.helper.remaining_by_category()
            if rem.get(cat, 0) <= 0:
                UI.warn("정원 초과", f"{cat} 잔여가 0입니다. 다른 체험을 선택하세요.")
                self.refresh_availability(); return None
        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"잔여 인원을 확인할 수 없습니다.\n{e}")
            return None
            
        return name, last4, cat

    def on_save(self):
        v = self.validate_inputs()
        if v is None: return
        name, last4, cat = v
        
        try:
            rows = self.helper.read_rows()
            dup = any((r.get("이름") == name and r.get("전화뒷4자리") == last4) for r in rows)
            if dup and not UI.ask_yesno("중복 확인", "같은 이름과 전화번호 뒷자리의 예약이 이미 있습니다. 그래도 저장하시겠습니까?"):
                return
            
            row_id = self.helper.next_id()
            row = {"ID": row_id, "시간": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "이름": name, "전화뒷4자리": last4, "체험": cat, "참여": str(False), "참여시각": ""}
            
            self.helper.append_row(row)
            
            UI.info("저장 완료", f"예약이 저장되었습니다. (ID: {row['ID']})")
            self.ent_name.delete(0, tk.END); self.ent_last4.delete(0, tk.END)
            self.refresh_status()
            
            rem_after = self.helper.remaining_by_category()
            after = rem_after.get(cat, None)
            if after in THRESHOLDS: UI.info("정원 알림", f"{cat} 잔여가 {after}명 남았습니다.")
            self.refresh_availability()

        except gspread.exceptions.APIError as e:
            UI.error("API 오류", f"예약을 저장하지 못했습니다.\n{e}")

    def open_list_window(self):
        top = self.winfo_toplevel()
        if hasattr(self, "_list_win") and self._list_win and self._list_win.winfo_exists():
            self._list_win.lift(); return
        self._list_win = ListWindow(top, self.helper, self.refresh_status)

