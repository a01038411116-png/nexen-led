import streamlit as st
import json
import os
import io
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="넥센 LED 설치관리",
    page_icon="😸",
    layout="wide",
)

# ========== 비밀번호 로그인 (관리자/방문자) ==========
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_role = None
    if st.session_state.authenticated:
        return True

    st.title("🔒 넥센타이어 LED 설치관리")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("로그인", type="primary"):
        try:
            admin_pw = st.secrets["admin_password"]
            viewer_pw = st.secrets["viewer_password"]
        except Exception:
            admin_pw = "4572"
            viewer_pw = "1116"
        if password == admin_pw:
            st.session_state.authenticated = True
            st.session_state.user_role = "admin"
            st.rerun()
        elif password == viewer_pw:
            st.session_state.authenticated = True
            st.session_state.user_role = "viewer"
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

if not check_password():
    st.stop()

is_admin = st.session_state.get("user_role") == "admin"

# ========== Google Sheets 연결 ==========
SHEET_ID = "1yoDDNRkQGbFvdGA-gDXoqHC6Y84VRlx6jmai6-Y8Ojo"

@st.cache_resource
def get_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    except Exception:
        creds = Credentials.from_service_account_file(
            str(Path(__file__).parent / "nyahaha-504603-9a81864164e2.json"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_worksheet():
    sh = get_gsheet()
    try:
        ws = sh.worksheet("install_data")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="install_data", rows=10000, cols=4)
        ws.update(values=[["날짜", "구역", "조명", "수량"]], range_name="A1")
    return ws

def load_all_data() -> dict:
    ws = get_worksheet()
    rows = ws.get_all_records()
    all_data = {}
    for row in rows:
        dt = str(row.get("날짜", ""))
        area = str(row.get("구역", ""))
        light = str(row.get("조명", ""))
        qty = int(row.get("수량", 0))
        if dt and area and light and qty > 0:
            if dt not in all_data:
                all_data[dt] = {}
            if area not in all_data[dt]:
                all_data[dt][area] = {}
            all_data[dt][area][light] = qty
    return all_data

def save_daily(dt, area, lights):
    ws = get_worksheet()
    dt_str = dt.isoformat()
    all_rows = ws.get_all_values()
    rows_to_delete = []
    for i, row in enumerate(all_rows):
        if i == 0: continue
        if len(row) >= 2 and row[0] == dt_str and row[1] == area:
            rows_to_delete.append(i + 1)
    for row_idx in reversed(rows_to_delete):
        ws.delete_rows(row_idx)
    new_rows = [[dt_str, area, light, qty] for light, qty in lights.items() if qty > 0]
    if new_rows:
        ws.append_rows(new_rows)

# ========== 마스터 데이터 ==========
MASTER_FILE = Path(__file__).parent / "area_light_data.json"

def load_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def calc_cumulative(all_data):
    cumul = {}
    for dt_str, daily in sorted(all_data.items()):
        for area, lights in daily.items():
            if area not in cumul:
                cumul[area] = {}
            for light, qty in lights.items():
                cumul[area][light] = cumul[area].get(light, 0) + qty
    return cumul

# ========== 메인 ==========
master = load_master()
areas = master["areas"]
buildings = sorted(set(a["building"] for a in areas))
contract_by_building = master.get("contract_by_building", {})

st.sidebar.title("넥센 LED 설치관리")
if is_admin:
    st.sidebar.caption("🔑 관리자 모드")
else:
    st.sidebar.caption("👁 열람 모드")

if is_admin:
    menu = st.sidebar.radio("메뉴", ["조명별 현황", "구역별 현황", "일별 리포트", "설치 입력"])
else:
    menu = st.sidebar.radio("메뉴", ["조명별 현황", "구역별 현황", "일별 리포트"])

import pandas as pd

# ==========================================
# 조명별 현황 (첫 화면)
# ==========================================
if menu == "조명별 현황":
    st.title("조명 종류별 설치현황")

    all_data = load_all_data()

    light_planned = defaultdict(int)
    light_contract = defaultdict(int)
    light_installed = defaultdict(int)

    for a in areas:
        for light, qty in a["lights"].items():
            light_planned[light] += qty

    for dt_str, daily in all_data.items():
        for area_name, lights in daily.items():
            for light, qty in lights.items():
                light_installed[light] += qty

    total_p = sum(light_planned.values())
    total_i = sum(light_installed.values())
    total_contract = sum(a.get("building_contract", 0) for a in areas)

    # 요약
    total_contract_all = 15559  # 계약 총수량
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("계약수량", f"{total_contract_all:,}")
    col2.metric("설치예정", f"{total_p:,}")
    col3.metric("설치완료", f"{total_i:,}")
    col4.metric("계약대비 진행률", f"{total_i/total_contract_all*100:.1f}%" if total_contract_all > 0 else "0%")
    col5.metric("계약대비 증감", f"{total_i - total_contract_all:+,}")

    st.progress(total_i / total_contract_all if total_contract_all > 0 else 0)
    st.divider()

    contract_lights = master.get("contract_lights", {})
    rows = []
    for light in master["light_types"]:
        c = contract_lights.get(light, 0)
        p = light_planned.get(light, 0)
        i = light_installed.get(light, 0)
        remain = c - i if c > 0 else p - i
        diff = i - c if c > 0 else 0
        rows.append({
            "조명 종류": light,
            "계약수량": c if c > 0 else "-",
            "설치예정": p,
            "설치완료": i,
            "잔여(계약)": remain if c > 0 else "-",
            "계약대비": f"{diff:+}" if c > 0 and i > 0 else "-",
            "진행률": f"{i/c*100:.0f}%" if c > 0 else f"{i/p*100:.0f}%" if p > 0 else "-",
        })
    df_light = pd.DataFrame(rows)
    st.dataframe(df_light, use_container_width=True, hide_index=True, height=800)

    buf = io.BytesIO()
    df_light.to_excel(buf, index=False, sheet_name="조명별현황")
    st.download_button("📥 엑셀 다운로드", buf.getvalue(), file_name="조명별현황.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# 구역별 현황
# ==========================================
elif menu == "구역별 현황":
    st.title("구역별 설치현황")

    all_data = load_all_data()
    cumul = calc_cumulative(all_data)

    filter_building = st.selectbox("건물 필터", ["전체"] + buildings)
    filtered = areas if filter_building == "전체" else [a for a in areas if a["building"] == filter_building]

    total_planned = sum(a["total"] for a in filtered)
    total_installed = sum(sum(cumul.get(a["area"], {}).values()) for a in filtered)

    col1, col2, col3 = st.columns(3)
    col1.metric("설치예정", f"{total_planned:,}")
    col2.metric("설치완료", f"{total_installed:,}")
    col3.metric("진행률", f"{total_installed/total_planned*100:.1f}%" if total_planned > 0 else "0%")

    st.progress(total_installed / total_planned if total_planned > 0 else 0)

    # 구역별 엑셀 다운로드
    area_export_rows = []
    for a in filtered:
        an = a["area"]
        inst = sum(cumul.get(an, {}).values())
        area_export_rows.append({
            "건물": a["building"],
            "구역": an,
            "설치예정": a["total"],
            "설치완료": inst,
            "잔여": a["total"] - inst,
            "진행률": f"{inst/a['total']*100:.0f}%" if a["total"] > 0 else "-",
        })
    df_area = pd.DataFrame(area_export_rows)
    buf2 = io.BytesIO()
    df_area.to_excel(buf2, index=False, sheet_name="구역별현황")
    st.download_button("📥 엑셀 다운로드", buf2.getvalue(), file_name="구역별현황.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()

    for a in filtered:
        area_name = a["area"]
        planned = a["total"]
        installed = sum(cumul.get(area_name, {}).values())
        pct = installed / planned * 100 if planned > 0 else 0

        if pct >= 100:
            icon = "✅"
        elif pct > 0:
            icon = "🔧"
        else:
            icon = "⬜"

        label = f"{icon} {a['building']} | {area_name} — {installed}/{planned} ({pct:.0f}%)"

        with st.expander(label):
            st.progress(min(pct / 100, 1.0))

            light_rows = []
            for light, light_planned_qty in a["lights"].items():
                light_installed = cumul.get(area_name, {}).get(light, 0)
                light_rows.append({
                    "조명": light,
                    "예정": light_planned_qty,
                    "설치": light_installed,
                    "잔여": light_planned_qty - light_installed,
                    "진행률": f"{light_installed/light_planned_qty*100:.0f}%" if light_planned_qty > 0 else "-",
                })
            if light_rows:
                st.dataframe(pd.DataFrame(light_rows), use_container_width=True, hide_index=True)

# ==========================================
# 일별 리포트
# ==========================================
elif menu == "일별 리포트":
    st.title("일별 설치 리포트")

    all_data = load_all_data()

    if not all_data:
        st.info("아직 입력된 데이터가 없습니다.")
    else:
        cumul_total = 0
        total_planned = sum(a["total"] for a in areas)
        total_contract_all = 15559

        col1, col2, col3 = st.columns(3)
        col1.metric("계약수량", f"{total_contract_all:,}")
        col2.metric("설치예정", f"{total_planned:,}")
        all_installed = sum(sum(lights.values()) for daily in all_data.values() for lights in daily.values())
        col3.metric("계약대비 진행률", f"{all_installed/total_contract_all*100:.1f}%" if total_contract_all > 0 else "0%")
        st.divider()

        rows = []
        for dt_str in sorted(all_data.keys()):
            daily = all_data[dt_str]
            day_total = sum(sum(lights.values()) for lights in daily.values())
            cumul_total += day_total
            rows.append({
                "날짜": dt_str,
                "작업구역수": len(daily),
                "당일설치": day_total,
                "누적설치": cumul_total,
                "계약대비": f"{cumul_total/total_contract_all*100:.1f}%",
                "잔여(계약)": total_contract_all - cumul_total,
            })

        df_daily = pd.DataFrame(rows)
        st.dataframe(df_daily, use_container_width=True, hide_index=True)

        buf3 = io.BytesIO()
        df_daily.to_excel(buf3, index=False, sheet_name="일별리포트")
        st.download_button("📥 엑셀 다운로드", buf3.getvalue(), file_name="일별리포트.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if len(rows) > 1:
            chart_df = pd.DataFrame(rows)
            chart_df["날짜"] = pd.to_datetime(chart_df["날짜"])
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("일별 설치수량")
                st.bar_chart(chart_df.set_index("날짜")["당일설치"])
            with col2:
                st.subheader("누적 설치수량")
                st.line_chart(chart_df.set_index("날짜")["누적설치"])

        st.divider()
        sel_date = st.selectbox("날짜 선택", sorted(all_data.keys(), reverse=True))
        if sel_date:
            daily = all_data[sel_date]
            st.subheader(f"{sel_date} 상세")
            for area_name, lights in daily.items():
                area_total = sum(lights.values())
                with st.expander(f"{area_name} - {area_total}개"):
                    for light, qty in lights.items():
                        st.write(f"  {light}: {qty}개")

# ==========================================
# 설치 입력 (관리자만)
# ==========================================
elif menu == "설치 입력":
    st.title("설치 수량 입력")

    col1, col2 = st.columns(2)
    with col1:
        input_date = st.date_input("날짜", value=date.today())
    with col2:
        sel_building = st.selectbox("건물", buildings)

    building_areas = [a for a in areas if a["building"] == sel_building]
    area_names = [a["area"] for a in building_areas]

    col3, col4 = st.columns(2)
    with col3:
        sel_area = st.selectbox("구역", area_names)

    area_data = next((a for a in areas if a["area"] == sel_area), None)
    if area_data:
        sub_locs = area_data.get("sub_locations", [])
        with col4:
            if sub_locs:
                sub_names = ["전체 (구역 단위)"] + [s['name'] for s in sub_locs]
                sel_sub = st.selectbox("세부장소", sub_names)
            else:
                sel_sub = "전체 (구역 단위)"
                st.selectbox("세부장소", ["세부장소 없음"], disabled=True)

        # 선택된 세부장소 정보 표시
        if sel_sub != "전체 (구역 단위)" and sub_locs:
            idx = sub_names.index(sel_sub) - 1
            sub_data = sub_locs[idx]
            display_lights = sub_data["lights"]
            st.markdown(f"**{sel_area} > {sel_sub}** | 예정: {sub_data['total']}개 | 조명 {len(display_lights)}종류")
        else:
            display_lights = area_data["lights"]
            st.markdown(f"**{sel_area}** | 예정: {area_data['total']}개 | 조명 {len(display_lights)}종류")

        # 계약 정보
        contract = area_data.get("building_contract", 0)
        if contract > 0:
            st.caption(f"건물 계약수량: {contract:,}")

        st.divider()

        # 기존 입력값
        all_data = load_all_data()
        dt_str = input_date.isoformat()
        existing = all_data.get(dt_str, {}).get(sel_area, {})

        with st.form("install_form"):
            st.subheader(f"{sel_area} - {input_date.strftime('%m/%d')} 설치수량")

            inputs = {}
            n_cols = min(3, max(1, len(display_lights)))
            cols = st.columns(n_cols)
            for i, (light, planned) in enumerate(display_lights.items()):
                with cols[i % n_cols]:
                    prev_val = existing.get(light, 0)
                    inputs[light] = st.number_input(
                        f"{light}\n(예정: {planned})",
                        min_value=0,
                        value=prev_val,
                        step=1,
                        key=f"input_{light}",
                    )

            submitted = st.form_submit_button("저장", use_container_width=True, type="primary")
            if submitted:
                # 기존 데이터에 병합 (세부장소 선택 시 기존 다른 조명 유지)
                merged = dict(existing)
                for k, v in inputs.items():
                    if v > 0:
                        merged[k] = v
                    elif k in merged:
                        del merged[k]
                save_daily(input_date, sel_area, merged)
                st.success(f"저장 완료! {sel_area} - {sum(v for v in merged.values())}개")
                st.cache_resource.clear()
                st.rerun()

        # 당일 입력 현황
        today_data = all_data.get(dt_str, {})
        if today_data:
            st.divider()
            st.subheader(f"{input_date.strftime('%m/%d')} 입력 현황")
            total_today = 0
            for area_name, lights in today_data.items():
                area_total = sum(lights.values())
                total_today += area_total
                with st.expander(f"{area_name} - {area_total}개"):
                    for light, qty in lights.items():
                        st.write(f"  {light}: {qty}개")
            st.metric("오늘 총 설치", f"{total_today}개")
