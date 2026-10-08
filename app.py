import streamlit as st
import json
import itertools
import pandas as pd

# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="Character Stat Upgrade Planner",
    page_icon="⚔️",
    layout="wide"
)

# ---------------------------------------------------------
# Load Data Functions
# ---------------------------------------------------------
@st.cache_data
def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดไฟล์ {filepath}: {e}")
        return None

characters_data = load_json("characters.json")
equip_sets_data = load_json("equipment_sets.json")
gear_stats_data = load_json("gear_stats.json")
substat_data = load_json("substat_upgrades.json")

if not (characters_data and equip_sets_data and gear_stats_data and substat_data):
    st.stop()

# ---------------------------------------------------------
# Helper & Formula Calculations
# ---------------------------------------------------------
def calculate_character_stats(char, equip_set, main_stats, buffs, substat_values):
    """
    คำนวณ Stat รวมตามสูตร:
    - ATK, DEF, HP: Total = Base Stat * (1 + Sum of Stat %) + Sum of Flat Stat
    - อื่นๆ: Total = Base Stat + Sum of Stat
    """
    # 1. รวบรวมค่า Percent และ Flat จากทุกแหล่ง
    sum_pct = {"ATK": char.get("ATK%", 0.0), "DEF": char.get("DEF%", 0.0), "HP": char.get("HP%", 0.0)}
    sum_flat = {"ATK": 0.0, "DEF": 0.0, "HP": 0.0}
    other_stats = {
        "Speed": char.get("Speed", 0.0),
        "Crit Rate": char.get("Crit Rate", 0.0),
        "Crit DMG": char.get("Crit DMG", 0.0),
        "Weakness": char.get("Weakness", 0.0),
        "Block": char.get("Block", 0.0),
        "Effect Hit": char.get("Effect Hit", 0.0),
        "Effect RES": char.get("Effect RES", 0.0)
    }

    # เพิ่ม Set Bonus
    if equip_set:
        for stat_name, val in equip_set.get("BonusStats", {}).items():
            if stat_name == "ATK%": sum_pct["ATK"] += val
            elif stat_name == "DEF%": sum_pct["DEF"] += val
            elif stat_name == "HP%": sum_pct["HP"] += val
            elif stat_name in other_stats: other_stats[stat_name] += val

    # เพิ่ม Main Stats จากอุปกรณ์
    for main_stat in main_stats:
        s_name = main_stat["Stat"]
        val = main_stat["Value"]
        if s_name == "ATK%": sum_pct["ATK"] += val
        elif s_name == "DEF%": sum_pct["DEF"] += val
        elif s_name == "HP%": sum_pct["HP"] += val
        elif s_name == "ATK Flat": sum_flat["ATK"] += val
        elif s_name == "DEF Flat": sum_flat["DEF"] += val
        elif s_name == "HP Flat": sum_flat["HP"] += val
        elif s_name in other_stats: other_stats[s_name] += val

    # เพิ่ม Buffs
    for b_type, b_val in buffs.items():
        if b_type == "Critical (Crit)":
            other_stats["Crit Rate"] += b_val
        elif b_type in other_stats:
            other_stats[b_type] += b_val

    # เพิ่ม Substats
    for s_name, val in substat_values.items():
        if s_name == "ATK%": sum_pct["ATK"] += val
        elif s_name == "DEF%": sum_pct["DEF"] += val
        elif s_name == "HP%": sum_pct["HP"] += val
        elif s_name == "ATK": sum_flat["ATK"] += val
        elif s_name == "DEF": sum_flat["DEF"] += val
        elif s_name == "HP": sum_flat["HP"] += val
        elif s_name in other_stats: other_stats[s_name] += val

    # 2. คำนวณผลลัพธ์สุดท้าย
    total_stats = {
        "ATK": char["Base ATK"] * (1 + sum_pct["ATK"]) + sum_flat["ATK"],
        "DEF": char["Base DEF"] * (1 + sum_pct["DEF"]) + sum_flat["DEF"],
        "HP": char["Base HP"] * (1 + sum_pct["HP"]) + sum_flat["HP"],
    }
    total_stats.update(other_stats)
    return total_stats

# ---------------------------------------------------------
# Application UI Logic
# ---------------------------------------------------------
st.title("⚔️ โปรแกรมวางแผนและคำนวณการอัปเกรดสเตตัสตัวละคร")

# Session State Initialization for Dynamic Inputs
for key in ['buffs', 'targets', 'unwanted']:
    if key not in st.session_state:
        st.session_state[key] = []

# --- 1. Character Selection & Element Filter ---
st.header("1. เลือกตัวละคร (Character Selection)")
col1, col2 = st.columns(2)

elements = list(set(c["Element"] for c in characters_data))
with col1:
    selected_elements = st.multiselect("กรองตามธาตุ (Element Filter):", elements)

filtered_chars = characters_data
if selected_elements:
    filtered_chars = [c for c in characters_data if c["Element"] in selected_elements]

char_names = [c["Name"] for c in filtered_chars]
with col2:
    selected_char_name = st.selectbox("เลือกตัวละคร:", char_names)

selected_char = next(c for c in characters_data if c["Name"] == selected_char_name)

# --- 2. Equipment Set Selection ---
st.header("2. เลือกเซตอุปกรณ์ (Equipment Set Selection)")
set_options = ["อัตโนมัติ (ให้ระบบจัดหาเซตที่ดีที่สุด)"] + [s["SetName"] for s in equip_sets_data]
selected_set_option = st.selectbox("เลือกเซตอุปกรณ์:", set_options)

# --- 3. Main Stats Selection ---
st.header("3. เลือกออฟหลักอุปกรณ์ (Main Stats Selection)")
c_w1, c_w2, c_a1, c_a2 = st.columns(4)

def stat_format(item):
    return f"{item['Stat']} (+{item['Value']})"

with c_w1:
    w1 = st.selectbox("อาวุธ ช่อง 1", gear_stats_data["Weapon Slot 1"], format_func=stat_format)
with c_w2:
    w2 = st.selectbox("อาวุธ ช่อง 2", gear_stats_data["Weapon Slot 2"], format_func=stat_format)
with c_a1:
    a1 = st.selectbox("เกราะ ช่อง 1", gear_stats_data["Armor Slot 1"], format_func=stat_format)
with c_a2:
    a2 = st.selectbox("เกราะ ช่อง 2", gear_stats_data["Armor Slot 2"], format_func=stat_format)

selected_main_stats = [w1, w2, a1, a2]

# --- Helper Functions for Dynamic List UI ---
def render_dynamic_section(title, state_key, allowed_types, value_label="ค่า Value"):
    st.subheader(title)
    col_add1, col_add2, col_add3 = st.columns([3, 3, 1])
    with col_add1:
        st_type = st.selectbox(f"เลือกประเภท ({title})", allowed_types, key=f"sel_{state_key}")
    with col_add2:
        st_val = st.number_input(f"{value_label}", min_value=0.0, step=1.0, key=f"val_{state_key}")
    with col_add3:
        st.write("")
        st.write("")
        if st.button("➕ เพิ่ม", key=f"btn_{state_key}"):
            st.session_state[state_key].append({"type": st_type, "value": st_val})

    # Render Active Items Table/List
    if st.session_state[state_key]:
        for idx, item in enumerate(st.session_state[state_key]):
            rcol1, rcol2, rcol3 = st.columns([4, 4, 1])
            rcol1.write(f"• **{item['type']}**")
            rcol2.write(f"ค่า: {item['value']}")
            if rcol3.button("❌", key=f"del_{state_key}_{idx}"):
                st.session_state[state_key].pop(idx)
                st.rerun()

# --- 4. Specific Buff Selection ---
st.header("4. บัฟเสริม (Specific Buff Selection)")
allowed_buffs = ["Weakness", "Critical (Crit)", "Effect Hit"]
render_dynamic_section("เพิ่มบัฟเสริม", "buffs", allowed_buffs, "ค่าบัฟ (%)")

# --- 5. Target Stats Input ---
st.header("5. กำหนดสเตตัสเป้าหมาย (Target Stats Input)")
all_stat_types = ["ATK", "DEF", "HP", "Speed", "Crit Rate", "Crit DMG", "Weakness", "Block", "Effect Hit", "Effect RES"]
render_dynamic_section("เป้าหมายสเตตัส (Target Stats)", "targets", all_stat_types, "ค่าเป้าหมายสุทธิ")

# --- 6. Unwanted Stats Input ---
st.header("6. สเตตัสที่ไม่ต้องการให้อัปไปลง (Unwanted Stats Input)")
render_dynamic_section("สเตตัสที่ไม่ต้องการ", "unwanted", all_stat_types, "ไม่ส่งผลกับคำนวณ (ใส่ 0 ได้)")

# ---------------------------------------------------------
# Calculation Engine & Output
# ---------------------------------------------------------
st.divider()

if st.button("🚀 คำนวณรูปแบบออฟรอง", type="primary", use_container_width=True):
    # Parse Buffs
    buff_dict = {b["type"]: b["value"] for b in st.session_state['buffs']}
    target_dict = {t["type"]: t["value"] for t in st.session_state['targets']}
    unwanted_list = [u["type"] for u in st.session_state['unwanted']]

    if not target_dict:
        st.warning("⚠️ กรุณากำหนดสเตตัสเป้าหมายอย่างน้อย 1 รายการก่อนคำนวณ")
        st.stop()

    # Determine Sets to Calculate
    sets_to_test = []
    if selected_set_option == "อัตโนมัติ (ให้ระบบจัดหาเซตที่ดีที่สุด)":
        sets_to_test = equip_sets_data
    else:
        sets_to_test = [s for s in equip_sets_data if s["SetName"] == selected_set_option]

    # Available Substats Filter (Exclude Unwanted)
    available_substats = [s for s in substat_data.keys() if s not in unwanted_list]

    # Substat Upgrade Levels to Consider
    levels = ["+0", "+1", "+2", "+3", "+4", "+5"]
    worst_case_levels = ["+2", "+3"]  # For Worst-Case Scenario

    best_result = None
    best_diff = float('inf')

    # Simulation Search Engine (4 Equipment Pieces)
    # Search for combination of substats across 4 pieces
    with st.spinner("กำลังคำนวณและค้นหารูปแบบออฟรองที่เหมาะสมที่สุด..."):
        for equip_set in sets_to_test:
            # Optimize Search: Select top candidate substats present in Targets
            target_substats = [s for s in available_substats if any(t in s for t in target_dict.keys())]
            if not target_substats:
                target_substats = available_substats[:3]

            # Combination Search on Substat allocations across 4 gear pieces
            for combo in itertools.combinations_with_replacement(target_substats, 4):
                # Test Perfect Scenario (+5) and Worst-Case (+2/+3)
                for lvl in ["+5", "+3", "+2"]:
                    substat_totals = {}
                    piece_details = []
                    for piece_idx, s_name in enumerate(combo):
                        val = substat_data[s_name][lvl]
                        substat_totals[s_name] = substat_totals.get(s_name, 0.0) + val
                        piece_details.append({"ชิ้นส่วน": f"ชิ้นที่ {piece_idx+1}", "ออฟรอง": s_name, "ระดับการบวก": lvl, "ค่าพลัง": val})

                    calculated = calculate_character_stats(selected_char, equip_set, selected_main_stats, buff_dict, substat_totals)
                    
                    # Check Target Satisfaction
                    diff = 0
                    all_met = True
                    for t_stat, t_val in target_dict.items():
                        current_val = calculated.get(t_stat, 0)
                        if current_val < t_val:
                            all_met = False
                            diff += (t_val - current_val)

                    if all_met or diff < best_diff:
                        best_diff = diff
                        best_result = {
                            "set": equip_set,
                            "pieces": piece_details,
                            "calculated_stats": calculated,
                            "scenario_level": lvl,
                            "all_met": all_met
                        }
                        if all_met and lvl == "+5":
                            break

    # ---------------------------------------------------------
    # Output Display
    # ---------------------------------------------------------
    st.header("📊 สรุปผลการคำนวณ (Calculation Results)")

    if best_result:
        if best_result["all_met"]:
            st.success("✅ บรรลุเป้าหมาย Target Stats ทั้งหมด!")
        else:
            st.warning("⚠️ ไม่สามารถบรรลุเป้าหมายได้ 100% แต่แสดงผลลัพธ์ที่เข้าใกล้เป้าหมายมากที่สุด")

        # 1. Equipment Set Summary
        st.subheader("1. เซตอุปกรณ์ที่แนะนำ/เลือก")
        st.info(f"**เซตอุปกรณ์:** {best_result['set']['SetName']} | **สถานะการจำลองระดับ:** {best_result['scenario_level']}")

        # 2. Substat Distribution Table
        st.subheader("2. ตารางการกระจายออฟรองของอุปกรณ์แต่ละชิ้น")
        df_pieces = pd.DataFrame(best_result["pieces"])
        st.dataframe(df_pieces, use_container_width=True)

        # 3. Final Stats vs Target Stats Summary
        st.subheader("3. สรุปค่า Stat รวมขั้นสุดท้าย เทียบกับ Target Stats")
        summary_rows = []
        for t_stat, t_val in target_dict.items():
            final_val = best_result["calculated_stats"].get(t_stat, 0.0)
            status = "✅ ผ่านเป้าหมาย" if final_val >= t_val else "❌ ไม่ถึงเป้าหมาย"
            summary_rows.append({
                "Stat": t_stat,
                "ค่าเป้าหมาย (Target)": f"{t_val:,.2f}",
                "ค่าคำนวณสุทธิ (Final)": f"{final_val:,.2f}",
                "ผลลัพธ์": status
            })

        df_summary = pd.DataFrame(summary_rows)
        st.table(df_summary)

    else:
        st.error("ไม่สามารถคำนวณผลลัพธ์ได้ กรุณาตรวจสอบข้อมูลขาเข้า")