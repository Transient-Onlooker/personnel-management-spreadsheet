# data_models.py
from typing import Dict, List

class Person:
    def __init__(self, name, phone, role, sessions):
        self.name = name.strip()
        self.phone = phone.strip()
        self.role = role
        self.sessions = set(sessions)

    def to_dict(self):
        return {"name": self.name, "phone": self.phone, "role": self.role, "sessions": sorted(list(self.sessions))}

    @staticmethod
    def from_dict(d):
        return Person(d["name"], d.get("phone", ""), d["role"], d.get("sessions", []))

class Roster:
    def __init__(self):
        self.people: List[Person] = []
        self.targets = {
            "1부": {"부스": 6, "홍보": 3, "상주": 5},
            "2부": {"부스": 6, "홍보": 3, "상주": 5},
        }
        self.current_session = "1부"

        self.inside_slots = [None] * 8
        self.outside_slots = [None] * 3
        self.rest_slots = [None] * 3

        self.inside_types = ["상주"] * 4 + ["부스"] * 4
        self.outside_types = ["홍보", "홍보", "상주"]
        self.rest_types = ["부스", "부스", "홍보"]

    def to_dict(self):
        return {"people": [p.to_dict() for p in self.people], "targets": self.targets}

    def from_dict(self, data: Dict):
        self.people = [Person.from_dict(x) for x in data.get("people", [])]
        tg = data.get("targets")
        if isinstance(tg, dict):
            self.targets.update(tg)
        self.reset_layout()

    def people_for_session_and_role(self, session, role):
        sess_key = "1부" if session.startswith("1부") else "2부"
        return [p for p in self.people if sess_key in p.sessions and p.role == role]

    def reset_layout(self):
        self.inside_slots = [None] * 8
        self.outside_slots = [None] * 3
        self.rest_slots = [None] * 3

    def auto_assign(self):
        sess_key = "1부" if self.current_session.startswith("1부") else "2부"
        targets = self.targets[sess_key]
        booths = self.people_for_session_and_role(sess_key, "부스")[:targets["부스"]]
        promos = self.people_for_session_and_role(sess_key, "홍보")[:targets["홍보"]]
        residents = self.people_for_session_and_role(sess_key, "상주")[:targets["상주"]]

        self.reset_layout()

        outside_res = residents[:1]
        inside_res = residents[1:5]
        inside_booth = booths[:4]
        rest_booth = booths[4:6]
        outside_promo = promos[:2]
        rest_promo = promos[2:3]

        i = 0
        for p in inside_res:
            self.inside_slots[i] = p; i += 1
        for p in inside_booth:
            self.inside_slots[i] = p; i += 1

        i = 0
        for p in outside_promo:
            self.outside_slots[i] = p; i += 1
        if outside_res:
            self.outside_slots[2] = outside_res[0]

        i = 0
        for p in rest_booth:
            self.rest_slots[i] = p; i += 1
        if rest_promo:
            self.rest_slots[2] = rest_promo[0]

        warnings = []
        if len(residents) < 5:
            warnings.append(f"[{sess_key}] 상주 인원 부족: 필요 5명, 현재 {len(residents)}명")
        if len(booths) < 6:
            warnings.append(f"[{sess_key}] 부스 도우미 부족: 필요 6명, 현재 {len(booths)}명")
        if len(promos) < 3:
            warnings.append(f"[{sess_key}] 홍보 도우미 부족: 필요 3명, 현재 {len(promos)}명")
        return warnings

    def swap_with_rest(self, area, index, rest_person):
        if area == "inside":
            slot_role = self.inside_types[index]
            if slot_role == "상주":
                return False, "상주 교대는 '부스 내 ↔ 부스 외'로 진행하세요."
        else:
            slot_role = self.outside_types[index]
            if slot_role == "상주":
                return False, "상주 교대는 '부스 내 ↔ 부스 외'로 진행하세요."

        if rest_person is None:
            return False, "휴식 중 인원을 선택해 주세요."
        if rest_person.role != slot_role:
            return False, f"이 칸은 '{slot_role}' 전용입니다. 동일 역할과만 교대할 수 있어요."

        rest_idx = None
        for i, p in enumerate(self.rest_slots):
            if p and p.name == rest_person.name and p.phone == rest_person.phone:
                rest_idx = i; break
        if rest_idx is None:
            return False, "선택한 인원이 휴식 중이 아닙니다."

        if area == "inside":
            self.inside_slots[index], self.rest_slots[rest_idx] = self.rest_slots[rest_idx], self.inside_slots[index]
        else:
            self.outside_slots[index], self.rest_slots[rest_idx] = self.rest_slots[rest_idx], self.outside_slots[index]
        return True, "교대 완료"

    def swap_resident_inside_outside(self, inside_index, outside_index=2):
        if self.inside_types[inside_index] != "상주" or self.outside_types[outside_index] != "상주":
            return False, "상주 전용 슬롯에서만 교대할 수 있습니다."
        self.inside_slots[inside_index], self.outside_slots[outside_index] = (
            self.outside_slots[outside_index], self.inside_slots[inside_index]
        )
        return True, "상주 교대 완료"
