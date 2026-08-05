import streamlit as st
import json
import os
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

# 페이지 설정
st.set_page_config(
    page_title="넥센 LED 설치현황",
    page_icon="💡",
    layout="wide",
)

# ========== 비밀번호 로그인 ==========
def check_password():
    """비밀번호 확인. 통과하면 True 반환."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("🔒 넥센 LED 설치관리 시스템")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("로그인", type="primary"):
        # 비밀번호: Streamlit secrets 또는 기본값
        correct = st.secrets.get("password", "nexen2026") if hasattr(st, "secrets") and st.secrets else "nexen2026"
        try:
            correct = st.secrets["password"]
        except Exception:
            correct = "nexen2026"
        if password == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

if not check_password():
    st.stop()

DATA_DIR = Path(__file__).parent / "install_data"
DATA_DIR.mkdir(exist_ok=True)

MASTER_FILE = Path(__file__).parent / "area_light_data.json"


@st.cache_data
def load_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_daily(dt: date) -> dict:
    """날짜별 설치 데이터 로드"""
    path = DATA_DIR / f"{dt.isoformat()}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_daily(dt: date, data: dict):
    """날짜별 설치 데이터 저장"""
    path = DATA_DIR / f"{dt.isoformat()}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_daily_data() -> dict:
    """전체 일별 데이터 로드"""
    all_data = {}
    for f in sorted(DATA_DIR.glob("*.json")):
        dt_str = f.stem
        with open(f, "r", encoding="utf-8") as fp:
            all_data[dt_str] = json.load(fp)
    return all_data


def calc_cumulative(all_data: dict, master: dict) -> dict:
    """구역별/조명별 누적 설치수량 계산"""
    cumul = {}  # area -> light_type -> total
    for dt_str, daily in sorted(all_data.items()):
        for area, lights in daily.items():
            if area not in cumul:
                cumul[area] = {}
            for light, qty in lights.items():
                cumul[area][light] = cumul[area].get(light, 0) + qty
    return cumul


# ========== 메인 앱 ==========
master = load_master()
areas = master["areas"]
buildings = sorted(set(a["building"] for a in areas))

# 사이드바
st.sidebar.title("넥센 LED 설치관리")
menu = st.sidebar.radio("메뉴", ["설치 입력", "구역별 현황", "조명별 현황", "일별 리포트"])

# ==========================================
# 1. 설치 입력
# ==========================================
if menu == "설치 입력":
    st.title("설치 수량 입력")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        input_date = st.date_input("날짜", value=date.today())
    with col2:
        sel_building = st.selectbox("건물", buildings)

    # 해당 건물의 구역 필터
    building_areas = [a for a in areas if a["building"] == sel_building]
    area_names = [a["area"] for a in building_areas]

    with col3:
        sel_area = st.selectbox("구역", area_names)

    # 선택된 구역의 조명 종류만 표시
    area_data = next((a for a in areas if a["area"] == sel_area), None)
    if area_data:
        st.markdown(f"**예정수량: {area_data['total']}개** | 조명 {len(area_data['lights'])}종류")
        st.divider()

        # 기존 입력값 로드
        daily = load_daily(input_date)
        existing = daily.get(sel_area, {})

        # 입력 폼
        with st.form("install_form"):
            st.subheader(f"{sel_area} - {input_date.strftime('%m/%d')} 설치수량")

            inputs = {}
            cols = st.columns(min(3, len(area_data["lights"])))
            for i, (light, planned) in enumerate(area_data["lights"].items()):
                with cols[i % len(cols)]:
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
                # 0이 아닌 값만 저장
                non_zero = {k: v for k, v in inputs.items() if v > 0}
                if non_zero:
                    daily[sel_area] = non_zero
                elif sel_area in daily:
                    del daily[sel_area]
                save_daily(input_date, daily)
                st.success(f"저장 완료! {sel_area} - {sum(non_zero.values())}개")
                st.rerun()

        # 오늘 입력한 전체 현황
        daily_all = load_daily(input_date)
        if daily_all:
            st.divider()
            st.subheader(f"{input_date.strftime('%m/%d')} 입력 현황")
            total_today = 0
            for area_name, lights in daily_all.items():
                area_total = sum(lights.values())
                total_today += area_total
                with st.expander(f"{area_name} - {area_total}개"):
                    for light, qty in lights.items():
                        st.write(f"  {light}: {qty}개")
            st.metric("오늘 총 설치", f"{total_today}개")


# ==========================================
# 2. 구역별 현황
# ==========================================
elif menu == "구역별 현황":
    st.title("구역별 설치현황")

    all_data = get_all_daily_data()
    cumul = calc_cumulative(all_data, master)

    # 건물 필터
    filter_building = st.selectbox("건물 필터", ["전체"] + buildings)

    filtered = areas if filter_building == "전체" else [a for a in areas if a["building"] == filter_building]

    # 전체 요약
    total_planned = sum(a["total"] for a in filtered)
    total_installed = 0
    for a in filtered:
        if a["area"] in cumul:
            total_installed += sum(cumul[a["area"]].values())

    col1, col2, col3 = st.columns(3)
    col1.metric("예정수량", f"{total_planned:,}")
    col2.metric("설치완료", f"{total_installed:,}")
    col3.metric("진행률", f"{total_installed/total_planned*100:.1f}%" if total_planned > 0 else "0%")

    st.progress(total_installed / total_planned if total_planned > 0 else 0)
    st.divider()

    # 구역별 테이블
    for a in filtered:
        area_name = a["area"]
        planned = a["total"]
        installed = sum(cumul.get(area_name, {}).values())
        remaining = planned - installed
        pct = installed / planned * 100 if planned > 0 else 0

        if pct >= 100:
            icon = "✅"
        elif pct > 0:
            icon = "🔧"
        else:
            icon = "⬜"

        with st.expander(f"{icon} {a['building']} | {area_name} — {installed}/{planned} ({pct:.0f}%)"):
            # 진행바
            st.progress(min(pct / 100, 1.0))

            # 조명별 상세
            light_rows = []
            for light, light_planned in a["lights"].items():
                light_installed = cumul.get(area_name, {}).get(light, 0)
                light_remaining = light_planned - light_installed
                light_rows.append({
                    "조명": light,
                    "예정": light_planned,
                    "설치": light_installed,
                    "잔여": light_remaining,
                    "진행률": f"{light_installed/light_planned*100:.0f}%" if light_planned > 0 else "-",
                })

            if light_rows:
                import pandas as pd
                df = pd.DataFrame(light_rows)
                st.dataframe(df, use_container_width=True, hide_index=True)


# ==========================================
# 3. 조명별 현황
# ==========================================
elif menu == "조명별 현황":
    st.title("조명 종류별 설치현황")
    st.caption("발주/자재 관리용")

    all_data = get_all_daily_data()

    # 조명별 집계
    light_planned = defaultdict(int)  # light -> planned
    light_installed = defaultdict(int)  # light -> installed

    for a in areas:
        for light, qty in a["lights"].items():
            light_planned[light] += qty

    for dt_str, daily in all_data.items():
        for area_name, lights in daily.items():
            for light, qty in lights.items():
                light_installed[light] += qty

    # 전체 요약
    total_p = sum(light_planned.values())
    total_i = sum(light_installed.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("총 예정", f"{total_p:,}")
    col2.metric("총 설치", f"{total_i:,}")
    col3.metric("진행률", f"{total_i/total_p*100:.1f}%" if total_p > 0 else "0%")

    st.progress(total_i / total_p if total_p > 0 else 0)
    st.divider()

    # 테이블
    import pandas as pd
    rows = []
    for light in master["light_types"]:
        p = light_planned.get(light, 0)
        i = light_installed.get(light, 0)
        r = p - i
        pct = f"{i/p*100:.0f}%" if p > 0 else "-"
        status = "✅ 완료" if r <= 0 and p > 0 else f"잔여 {r}개" if p > 0 else "-"
        rows.append({
            "조명 종류": light,
            "예정": p,
            "설치": i,
            "잔여": r,
            "진행률": pct,
            "상태": status,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=800)


# ==========================================
# 4. 일별 리포트
# ==========================================
elif menu == "일별 리포트":
    st.title("일별 설치 리포트")

    all_data = get_all_daily_data()

    if not all_data:
        st.info("아직 입력된 데이터가 없습니다. '설치 입력'에서 데이터를 입력해주세요.")
    else:
        import pandas as pd

        # 일별 합계
        daily_totals = {}
        cumul_total = 0
        total_planned = sum(a["total"] for a in areas)

        rows = []
        for dt_str in sorted(all_data.keys()):
            daily = all_data[dt_str]
            day_total = sum(sum(lights.values()) for lights in daily.values())
            cumul_total += day_total
            area_count = len(daily)
            rows.append({
                "날짜": dt_str,
                "작업구역수": area_count,
                "당일설치": day_total,
                "누적설치": cumul_total,
                "진행률": f"{cumul_total/total_planned*100:.1f}%",
                "잔여": total_planned - cumul_total,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 차트
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

        # 상세 보기
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
