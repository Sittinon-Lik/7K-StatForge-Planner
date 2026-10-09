# -*- coding: utf-8 -*-
"""
Character Stat Upgrade Planner (Streamlit - Fast & Optimized Version)
รันด้วย: streamlit run app.py
"""
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────
# 0) ค่าคงที่ / ชื่อสเตตัสมาตรฐาน
# ─────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
DATA_DIRS = [APP_DIR / "data", APP_DIR]

FLAT_STATS = ["ATK", "DEF", "HP"]
PCT_KEYS = ["ATK%", "DEF%", "HP%"]
CAPPED_STATS = ["Crit", "Weakness", "Block", "Effect Hit", "Effect RES"]
OTHER_STATS = ["Speed", "Crit DMG", "DMG Red"] + CAPPED_STATS
ALL_STATS = FLAT_STATS + OTHER_STATS
ACC_KEYS = FLAT_STATS + PCT_KEYS + OTHER_STATS
K = len(ACC_KEYS)
KIDX = {k: i for i, k in enumerate(ACC_KEYS)}

ALIASES = {
    "Critical": "Crit", "Crit Rate": "Crit", "Critical Rate": "Crit",
    "Critical DMG": "Crit DMG", "DMG Crit": "Crit DMG", "Crit Damage": "Crit DMG",
}

BUFF_CHOICES = {
    "ATK (หน่วย)": "ATK", "ATK (%)": "ATK%",
    "DEF (หน่วย)": "DEF", "DEF (%)": "DEF%",
    "HP (หน่วย)": "HP", "HP (%)": "HP%",
    "Weakness (%)": "Weakness",
    "Critical / Crit Rate (%)": "Crit",
    "Effect Hit (%)": "Effect Hit"
}

AUTO_SET = "อัตโนมัติ (ให้ระบบจัดหาเซตที่ดีที่สุด)"
AUTO_MAIN = "อัตโนมัติ (ให้ระบบจัดการ)"
WEAPON, ARMOR = "อาวุธ", "เกราะ"
LEVELS = range(6)


def canon(name: str) -> str:
    name = str(name).strip()
    return ALIASES.get(name, name)


def fmt(stat: str, v: float) -> str:
    if stat in FLAT_STATS:
        return f"{v:,.0f}"
    if stat == "Speed":
        return f"{v:,.1f}"
    return f"{v:,.1f}%"


def fmt_sub(key: str, v: float) -> str:
    if key in FLAT_STATS or key == "Speed":
        return f"+{v:,.0f}"
    return f"+{v:,.1f}%"


# ─────────────────────────────────────────────────────────────
# 1) โหลดข้อมูล JSON
# ─────────────────────────────────────────────────────────────
def find_file(name: str) -> Path:
    for d in DATA_DIRS:
        p = d / name
        if p.exists():
            return p
    raise FileNotFoundError(f"ไม่พบไฟล์ {name}")


def read_json(name: str):
    with open(find_file(name), encoding="utf-8-sig") as f:
        return json.load(f)


def parse_num(x) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").replace("%", "").strip()
    return float(s) if s else 0.0


def norm_set_value(v: float) -> float:
    return v * 100.0 if abs(v) <= 1.0 else v


@st.cache_data(show_spinner=False)
def load_all():
    chars_raw = read_json("characters.json")
    sets_raw = read_json("equipment_sets.json")
    gear_raw = read_json("gear_stats.json")
    sub_raw = read_json("substat_upgrades.json")

    chars = []
    for c in chars_raw:
        base = {"ATK": parse_num(c.get("Base ATK", 0)),
                "DEF": parse_num(c.get("Base DEF", 0)),
                "HP": parse_num(c.get("Base HP", 0))}
        pct = {"ATK%": parse_num(c.get("ATK%", 0)),
               "DEF%": parse_num(c.get("DEF%", 0)),
               "HP%": parse_num(c.get("HP%", 0))}
        for k, v in c.items():
            if k in ("Rank", "Name", "Element") or k.startswith("Base ") or k in PCT_KEYS:
                continue
            ck = canon(k)
            if ck in OTHER_STATS:
                base[ck] = parse_num(v)
        for s in OTHER_STATS:
            base.setdefault(s, 0.0)
        chars.append({"rank": c.get("Rank", ""), "name": c["Name"],
                      "element": c.get("Element", "-"), "base": base, "pct": pct})

    sets = {}
    for s in sets_raw:
        bonus = {}
        for k, v in s.get("BonusStats", {}).items():
            bonus[canon(k)] = norm_set_value(float(v))
        sets[s["SetName"]] = bonus

    gear = {slot: {canon(k): float(v) for k, v in d.items()} for slot, d in gear_raw.items()}

    subs, sub_raw_name = {}, {}
    for k, tbl in sub_raw.items():
        ck = canon(k)
        subs[ck] = [float(tbl[f"+{i}"]) for i in LEVELS]
        sub_raw_name[ck] = k
    return chars, sets, gear, subs, sub_raw_name


# ─────────────────────────────────────────────────────────────
# 2) สูตรคำนวณ
# ─────────────────────────────────────────────────────────────
def compute_totals(acc: np.ndarray, base: dict, stats: list) -> np.ndarray:
    out = []
    for s in stats:
        if s in FLAT_STATS:
            out.append(base[s] * (1 + acc[..., KIDX[s + "%"]] / 100.0) + acc[..., KIDX[s]])
        else:
            base_val = base.get(s, 0.0)
            out.append(base_val + acc[..., KIDX[s]])
    return np.stack(out, axis=-1)


def build_fixed(char, set_bonus, mains, buffs) -> np.ndarray:
    F = np.zeros(K)
    for k, v in char["pct"].items():
        F[KIDX[k]] += v
    for k, v in set_bonus.items():
        if k in KIDX:
            F[KIDX[k]] += v
    for k, v in mains:
        if k and k in KIDX:
            F[KIDX[k]] += v
    for b in buffs:
        if b["stat"] in KIDX:
            F[KIDX[b["stat"]]] += b["value"]
    return F


# ─────────────────────────────────────────────────────────────
# 3) Fast Search Engine (Fast Pruning + Optimization)
# ─────────────────────────────────────────────────────────────
def search_piece_substats(F, base, target_list, cand_keys, mains, priority, subs, set_name, piece_user_subs):
    max_level_per_stat = 3 if priority == "minsum" else 5
    ordered_stats = [t['stat'] for t in target_list]
    target_dict = {t['stat']: t['value'] for t in target_list}

    piece_cands = []
    fixed_levels = []

    for p in range(4):
        p_user = piece_user_subs[p]
        slot_options = []
        p_lvl_opt = []
        for slot_idx in range(4):
            user_sel, user_lvl = p_user[slot_idx]
            if user_sel != "อัตโนมัติ":
                slot_options.append([user_sel])
            else:
                opts = list(cand_keys) + [None]
                slot_options.append(opts)
            p_lvl_opt.append(user_lvl)
        piece_cands.append(slot_options)
        fixed_levels.append(p_lvl_opt)

    valid_piece_configs = []
    for p in range(4):
        valid_configs = []
        for combo in itertools.product(*piece_cands[p]):
            non_none = [x for x in combo if x is not None]
            if len(non_none) == len(set(non_none)):
                # Normalization เพื่อตัดตำแหน่งสลับช่องหลอกล่วงหน้า
                sorted_non_none = tuple(sorted(non_none))
                if sorted_non_none not in valid_configs:
                    valid_configs.append(sorted_non_none)
        if not valid_configs:
            valid_configs = [()]
        valid_piece_configs.append(valid_configs)

    all_generated_cands = []
    seen_signatures = set()

    for p0 in valid_piece_configs[0]:
        for p1 in valid_piece_configs[1]:
            for p2 in valid_piece_configs[2]:
                for p3 in valid_piece_configs[3]:
                    norm_combo = [
                        p0 + (None,) * (4 - len(p0)),
                        p1 + (None,) * (4 - len(p1)),
                        p2 + (None,) * (4 - len(p2)),
                        p3 + (None,) * (4 - len(p3)),
                    ]

                    acc = F.copy()
                    for p in range(4):
                        for sub_stat in norm_combo[p]:
                            if sub_stat:
                                acc[KIDX[sub_stat]] += subs[sub_stat][0]

                    levels_matrix = []
                    for p in range(4):
                        p_levels = [0, 0, 0, 0]
                        rem_budget = 5
                        for s_idx, sub_stat in enumerate(norm_combo[p]):
                            if sub_stat:
                                user_defined_lvl = fixed_levels[p][s_idx] if s_idx < len(fixed_levels[p]) else "อัตโนมัติ"
                                if user_defined_lvl != "อัตโนมัติ":
                                    forced_l = int(user_defined_lvl.replace("+", ""))
                                    p_levels[s_idx] = forced_l
                                    added_val = subs[sub_stat][forced_l] - subs[sub_stat][0]
                                    acc[KIDX[sub_stat]] += added_val
                                    continue

                                if rem_budget > 0:
                                    current_tot = compute_totals(acc[np.newaxis, :], base, [sub_stat])[0][0]
                                    if sub_stat in CAPPED_STATS and current_tot >= 99.0 - 1e-6:
                                        p_levels[s_idx] = 0
                                        continue

                                    max_allowed = min(rem_budget, max_level_per_stat)
                                    best_l = 0
                                    for l in range(1, max_allowed + 1):
                                        added_val = subs[sub_stat][l] - subs[sub_stat][0]
                                        if sub_stat in CAPPED_STATS:
                                            if current_tot + added_val > 100.0 + 1e-6:
                                                break
                                            best_l = l
                                            if current_tot + added_val >= 99.0 - 1e-6:
                                                break
                                        else:
                                            best_l = l

                                    p_levels[s_idx] = best_l
                                    rem_budget -= best_l
                                    if best_l > 0:
                                        added_val = subs[sub_stat][best_l] - subs[sub_stat][0]
                                        acc[KIDX[sub_stat]] += added_val

                        levels_matrix.append(p_levels)

                    sig_pieces = tuple((norm_combo[p], tuple(levels_matrix[p])) for p in range(4))
                    full_sig = (set_name, tuple(mains), sig_pieces)
                    if full_sig in seen_signatures:
                        continue
                    seen_signatures.add(full_sig)

                    tot_res = compute_totals(acc[np.newaxis, :], base, ordered_stats)[0]
                    shortfalls = []
                    for idx, s in enumerate(ordered_stats):
                        req = target_dict[s]
                        curr = tot_res[idx]
                        if s in CAPPED_STATS and req >= 99.0 and curr >= 99.0 - 1e-6:
                            diff = 0.0
                        else:
                            diff = max(0.0, req - curr)
                        shortfalls.append(diff)

                    all_generated_cands.append({
                        "set": set_name,
                        "F": F,
                        "mains": mains,
                        "subs": norm_combo,
                        "levels": levels_matrix,
                        "feasible": all(s <= 1e-6 for s in shortfalls),
                        "shortfalls": shortfalls,
                        "minsum": sum(sum(l) for l in levels_matrix)
                    })

    return all_generated_cands


def run_engine(char, set_names, sets, main_selections, gear, buffs, target_list, unwanted,
               priority, subs, piece_user_subs):
    base = char["base"]
    targets = {t["stat"]: t["value"] for t in target_list}
    relevant = set()
    for s in targets:
        relevant.add(s)
        if s in FLAT_STATS:
            relevant.add(s + "%")
    cand_keys = [k for k in subs if k in relevant and k not in unwanted]

    possible_mains = []
    for slot_idx, (slot_type, sel_val) in enumerate([
        (WEAPON, main_selections[0]), (WEAPON, main_selections[1]),
        (ARMOR, main_selections[2]), (ARMOR, main_selections[3])
    ]):
        if sel_val == AUTO_MAIN:
            possible_mains.append([(k, gear[slot_type][k]) for k in gear[slot_type]])
        else:
            possible_mains.append([(sel_val, gear[slot_type][sel_val])])

    all_c = []
    for sn in set_names:
        for mains in itertools.product(*possible_mains):
            F = build_fixed(char, sets[sn], mains, buffs)
            cands = search_piece_substats(F, base, target_list, cand_keys, mains, priority, subs, sn, piece_user_subs)
            all_c.extend(cands)

    all_c.sort(key=lambda c: (not c["feasible"], c["shortfalls"], c["minsum"], c["set"]))
    return all_c[:15], cand_keys  # จำกัดคืนเฉพาะ 15 ตัวเลือกแรกที่เหมาะสมที่สุดเพื่อความรวดเร็วในการแสดงผล


# ─────────────────────────────────────────────────────────────
# 4) Dynamic input helper
# ─────────────────────────────────────────────────────────────
def _add_row(key, with_value):
    row = {"stat": st.session_state[f"{key}_sel"]}
    if with_value:
        row["value"] = float(st.session_state[f"{key}_val"])
    st.session_state[key].append(row)


def _del_row(key, i):
    st.session_state[key].pop(i)


def dynamic_input(key, options, with_value=True, fmt_option=str, unit_of=None):
    st.session_state.setdefault(key, [])
    for i, row in enumerate(st.session_state[key]):
        c1, c2, c3 = st.columns([4, 3, 1], vertical_alignment="center")
        priority_prefix = f"[{i+1}] " if with_value and key == "targets" else ""
        c1.write(f"{priority_prefix}{fmt_option(row['stat'])}")
        if with_value:
            u = unit_of(row["stat"]) if unit_of else ""
            c2.write(f"{row['value']:,.1f}{u}")
        c3.button("✕", key=f"{key}_del_{i}", on_click=_del_row, args=(key, i))
    if with_value:
        c1, c2, c3 = st.columns([4, 3, 1], vertical_alignment="bottom")
        c1.selectbox("ประเภท", options, key=f"{key}_sel", format_func=fmt_option)
        c2.number_input("ค่า", min_value=0.0, step=1.0, key=f"{key}_val")
        c3.button("➕", key=f"{key}_add", on_click=_add_row, args=(key, True))
    else:
        c1, c3 = st.columns([7, 1], vertical_alignment="bottom")
        c1.selectbox("ประเภท", options, key=f"{key}_sel", format_func=fmt_option)
        c3.button("➕", key=f"{key}_add", on_click=_add_row, args=(key, False))


# ─────────────────────────────────────────────────────────────
# 5) หน้าจอ GUI
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Stat Upgrade Planner", page_icon="🛠️", layout="wide")
st.title("🛠️ วางแผนอัปเกรดสเตตัสตัวละคร")

try:
    CHARS, SETS, GEAR, SUBS, SUB_RAW = load_all()
except Exception as e:
    st.error(f"โหลดไฟล์ JSON ไม่สำเร็จ: {e}")
    st.stop()

with st.sidebar:
    st.header("ตั้งค่าการคำนวณ")
    priority = st.radio(
        "ลำดับความสำคัญในการเลือกแผน",
        ["robust", "minsum"],
        format_func=lambda x: {"robust": "ทนต่อการสุ่มได้ระดับต่ำ (แนะนำ)",
                               "minsum": "ใช้ระดับการบวกรวมน้อยที่สุด (Max +3)"}[x],
    )

st.subheader("1) เลือกตัวละคร")
elements = sorted({c["element"] for c in CHARS})
sel_el = st.multiselect("กรองตามธาตุ", elements)
pool = [c for c in CHARS if not sel_el or c["element"] in sel_el]
if not pool:
    st.warning("ไม่มีตัวละครในธาตุที่เลือก")
    st.stop()
char = st.selectbox("ตัวละคร", pool, format_func=lambda c: f"{c['name']}  ·  {c['element']}  ·  {c['rank']}")

st.subheader("2) เลือกเซตอุปกรณ์")
set_choice = st.selectbox("เซต", [AUTO_SET] + list(SETS.keys()))

st.subheader("3) เลือกออฟหลัก")
cw, ca = st.columns(2)
main_opts_w = [AUTO_MAIN] + list(GEAR[WEAPON])
main_opts_a = [AUTO_MAIN] + list(GEAR[ARMOR])
main_fmt = lambda slot: (lambda k: AUTO_MAIN if k == AUTO_MAIN else f"{k} (+{GEAR[slot][k]:g}{'' if k == 'Speed' else '%'})")

with cw:
    w1 = st.selectbox("อาวุธ 1", main_opts_w, key="w1", format_func=main_fmt(WEAPON))
    w2 = st.selectbox("อาวุธ 2", main_opts_w, key="w2", format_func=main_fmt(WEAPON))
with ca:
    a1 = st.selectbox("เกราะ 1", main_opts_a, key="a1", format_func=main_fmt(ARMOR))
    a2 = st.selectbox("เกราะ 2", main_opts_a, key="a2", format_func=main_fmt(ARMOR))

MAIN_SELECTIONS = [w1, w2, a1, a2]
PIECE_NAMES = ["อาวุธ 1", "อาวุธ 2", "เกราะ 1", "เกราะ 2"]

st.subheader("4) เลือกออฟรอง และ ระดับการตีบวก (+0 ถึง +5)")
sub_choices = ["อัตโนมัติ"] + list(SUBS.keys())
level_choices = ["อัตโนมัติ", "+0", "+1", "+2", "+3", "+4", "+5"]
piece_user_subs = []

tabs = st.tabs(PIECE_NAMES)
dup_error_pieces = []

for idx, tab in enumerate(tabs):
    with tab:
        cols = st.columns(4)
        p_subs = []
        selected_in_piece = []
        
        for s_idx in range(4):
            with cols[s_idx]:
                st.markdown(f"**ออฟรองช่องที่ {s_idx+1}**")
                sub_sel = st.selectbox("ชนิดออฟรอง", sub_choices, key=f"sub_{idx}_{s_idx}", format_func=lambda k: "อัตโนมัติ" if k == "อัตโนมัติ" else SUB_RAW.get(k, k))
                lvl_sel = st.selectbox("ระดับขั้นตีบวก", level_choices, key=f"lvl_{idx}_{s_idx}")
                p_subs.append((sub_sel, lvl_sel))
                if sub_sel != "อัตโนมัติ":
                    selected_in_piece.append(sub_sel)

        if len(selected_in_piece) != len(set(selected_in_piece)):
            dup_error_pieces.append(PIECE_NAMES[idx])
            st.error(f"⚠️ ใน **{PIECE_NAMES[idx]}** คุณเลือกออฟรองประเภทเดียวกันซ้ำกัน! กรุณาเลือกออฟรองแต่ละช่องไม่ให้ซ้ำกัน")

        piece_user_subs.append(p_subs)

st.subheader("5) บัฟเสริม")
dynamic_input("buffs", list(BUFF_CHOICES.values()), True, fmt_option=lambda c: next((k for k, v in BUFF_CHOICES.items() if v == c), c), unit_of=lambda s: "" if s in FLAT_STATS else "%")

st.subheader("6) สเตตัสเป้าหมาย")
dynamic_input("targets", ALL_STATS, True, unit_of=lambda s: "" if s in FLAT_STATS + ["Speed"] else "%")

st.subheader("7) สเตตัสที่ไม่ต้องการ")
dynamic_input("unwanted", list(SUBS), False, fmt_option=lambda k: SUB_RAW.get(k, k))

st.divider()

if dup_error_pieces:
    st.warning(f"⛔ ไม่สามารถคำนวณได้เนื่องจากมีการเลือกออฟรองซ้ำกันใน {', '.join(dup_error_pieces)}")

if st.button("🔍 คำนวณรูปแบบออฟรองที่ดีที่สุด", type="primary", width="stretch", disabled=bool(dup_error_pieces)):
    target_list = st.session_state["targets"]
    if not target_list:
        st.session_state.pop("result", None)
        st.warning("กรุณาเพิ่มสเตตัสเป้าหมายอย่างน้อย 1 รายการ")
    else:
        unw = {r["stat"] for r in st.session_state["unwanted"]}
        names = list(SETS) if set_choice == AUTO_SET else [set_choice]
        with st.spinner("กำลังคำนวณแบบรวดเร็ว..."):
            cands, cand_keys = run_engine(char, names, SETS, MAIN_SELECTIONS, GEAR, st.session_state["buffs"],
                                          target_list, unw, priority, SUBS, piece_user_subs)
        st.session_state["result"] = {
            "cands": cands, "target_list": target_list, "unwanted": unw, "cand_keys": cand_keys,
            "char": char, "auto": set_choice == AUTO_SET,
        }

res = st.session_state.get("result")
if res:
    cands, target_list, rchar = res["cands"], res["target_list"], res["char"]
    st.header("ผลการคำนวณ")

    if not cands:
        st.error("ไม่พบคอมบิเนชันที่เหมาะสม กรุณาปรับเงื่อนไขเป้าหมายหรือการเลือกออฟหลัก/รอง")
    else:
        pick = st.selectbox(
            "เลือกดูอันดับของตัวเลือกที่แนะนำ",
            range(len(cands)),
            format_func=lambda i: f"อันดับ {i + 1}: {cands[i]['set']} ({'✅ บรรลุเป้าหมาย' if cands[i]['feasible'] else '❌ ไม่ถึงเป้าหมาย'})"
        )
        c = cands[pick]

        # 1. ตารางแสดงการกระจายออฟรอง
        st.subheader("การกระจายออฟรองแต่ละชิ้น")
        prow = []
        for p, n in enumerate(PIECE_NAMES):
            mk, mv = c["mains"][p]
            r = {
                "ชิ้น": n,
                "ออฟหลัก": f"{mk} +{mv:g}%" if mk in GEAR[ARMOR] or mk in GEAR[WEAPON] else f"{mk}"
            }
            for s_idx in range(4):
                sub_stat = c["subs"][p][s_idx]
                sub_lv = c["levels"][p][s_idx]
                if sub_stat:
                    val = SUBS[sub_stat][sub_lv]
                    val_str = fmt_sub(sub_stat, val)
                    r[f"ออฟรอง {s_idx+1}"] = f"{SUB_RAW.get(sub_stat, sub_stat)} {val_str} (+{sub_lv})"
                else:
                    r[f"ออฟรอง {s_idx+1}"] = "-"
            prow.append(r)

        st.dataframe(pd.DataFrame(prow), hide_index=True, width="stretch")

        # 2. ตารางสเตตัสทั้งหมดของตัวละคร (Base ➔ Final)
        st.subheader("📊 ตารางสเตตัสทั้งหมดของตัวละคร (สเตตัสเดิม ➔ สเตตัสใหม่)")
        
        base_pure_acc = np.zeros(K)
        for k, v in rchar["pct"].items():
            base_pure_acc[KIDX[k]] += v
        base_pure_totals = dict(zip(ALL_STATS, compute_totals(base_pure_acc[np.newaxis, :], rchar["base"], ALL_STATS)[0]))

        final_acc = c["F"].copy()
        for p in range(4):
            for s_idx in range(4):
                sub_stat = c["subs"][p][s_idx]
                sub_lv = c["levels"][p][s_idx]
                if sub_stat:
                    final_acc[KIDX[sub_stat]] += SUBS[sub_stat][sub_lv]
        
        final_totals = dict(zip(ALL_STATS, compute_totals(final_acc[np.newaxis, :], rchar["base"], ALL_STATS)[0]))
        
        target_dict = {t["stat"]: t["value"] for t in target_list}
        target_priority = {t["stat"]: idx + 1 for idx, t in enumerate(target_list)}

        out_all_table = []
        for s in ALL_STATS:
            base_v = base_pure_totals[s]
            final_v = final_totals[s]
            
            req = target_dict.get(s)
            target_str = fmt(s, req) if req is not None else "-"
            prio = f"อันดับ {target_priority[s]}" if s in target_priority else "-"
            
            status_mark = ""
            if req is not None:
                if s in CAPPED_STATS and req >= 99.0:
                    is_pass = final_v >= 99.0 - 1e-6
                else:
                    is_pass = final_v >= req - 1e-6
                status_mark = " ✅" if is_pass else " ❌"

            out_all_table.append({
                "ความสำคัญ": prio,
                "สเตตัส": s,
                "สเตตัสเดิม (Base)": fmt(s, base_v),
                "เป้าหมาย (Target)": target_str,
                "สเตตัสใหม่ (Final)": fmt(s, final_v) + status_mark
            })
        
        st.dataframe(pd.DataFrame(out_all_table), hide_index=True, width="stretch")