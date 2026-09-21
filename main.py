# 박스오피스 조회 — KOBIS 일별 박스오피스 API
import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="박스오피스 조회", page_icon="🎬", layout="wide")

URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 오늘 건 아직 집계 전이므로, 달력에서 고를 수 있는 가장 늦은 날짜는 '어제(한국 시간 기준)'까지다.
# 배포 서버의 시계는 한국 시간이 아닐 수 있으므로 KST를 직접 계산한다.
KST = datetime.timezone(datetime.timedelta(hours=9))
max_selectable_date = datetime.datetime.now(KST).date() - datetime.timedelta(days=1)


@st.cache_data(ttl=3600)  # 같은 날짜는 한 시간 동안 기억해 두고 API를 다시 부르지 않는다
def fetch_boxoffice(date_str, api_key):
    """KOBIS API에서 해당 날짜의 일별 박스오피스를 받아 온다."""
    params = {"key": api_key, "targetDt": date_str}
    res = requests.get(URL, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


def rank_change_html(value):
    """
    rankInten(전날 대비 순위 증감)을 화살표 HTML로 바꾼다.
    문서 기준: 양수면 순위가 오른 것(빨간 위 화살표), 음수면 내린 것(파란 아래 화살표).
    """
    if value > 0:
        return '<span style="color:#e03131; font-weight:bold;">▲</span>'
    elif value < 0:
        return '<span style="color:#1971c2; font-weight:bold;">▼</span>'
    else:
        return '<span style="color:#868e96;">－</span>'


st.title("🎬 박스오피스 조회")

# ── 날짜 선택(달력) ──────────────────────────────────────────
# value: 처음 열었을 때 기본으로 보여줄 날짜 (어제)
# max_value: 이 날짜보다 늦은 날짜는 달력에서 아예 고를 수 없게 막는다
selected_date = st.date_input(
    "조회할 날짜를 고르세요",
    value=max_selectable_date,
    max_value=max_selectable_date,
)
target_dt = selected_date.strftime("%Y%m%d")
st.caption(f"선택한 날짜: {selected_date} · 고를 수 있는 가장 늦은 날짜: {max_selectable_date} (어제, 한국 시간 기준)")

# 인증키는 비밀 금고(secrets)에서 불러온다 — 코드에 직접 쓰지 않는다
# secrets에 KOBIS_KEY가 없으면 여기서 바로 안내하고 멈춘다 (빨간 트레이스백 대신 친절한 메시지)
try:
    API_KEY = st.secrets["KOBIS_KEY"]
except KeyError:
    st.error("secrets에 KOBIS_KEY가 없습니다.")
    st.info("스트림릿 클라우드 앱의 Settings > Secrets에 KOBIS_KEY = \"발급받은키\" 형식으로 등록해 주세요.")
    st.stop()

try:
    data = fetch_boxoffice(target_dt, API_KEY)
except requests.RequestException:
    st.error("서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 새로고침해 주세요.")
    st.stop()

# 인증키가 틀리면 상태코드는 200이지만 faultInfo 상자가 온다
if "faultInfo" in data:
    st.error(f"API가 오류를 돌려주었습니다: {data['faultInfo'].get('message', '')}")
    st.info("비밀 금고(secrets)의 KOBIS_KEY 값이 올바른지 확인해 주세요.")
    st.stop()

movies = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 선택한 날짜에 영화 목록이 비어서 오면 — 그날은 아직 집계 전이다
if not movies:
    st.warning("그날은 아직 집계 전입니다.")
    st.stop()

df = pd.DataFrame(movies)

# 숫자가 글자로 오므로 숫자로 바꿔야 정렬과 그래프에 쓸 수 있다 (rankInten도 함께)
for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col])

df = df.sort_values("rank").reset_index(drop=True)

# ── 1위 영화는 지표 카드 세 장으로 크게 ─────────────────────
top = df.iloc[0]
st.subheader(f"🥇 1위 — {top['movieNm']}")
c1, c2, c3 = st.columns(3)
c1.metric("관객수", f"{top['audiCnt']:,}명")
c2.metric("누적 관객수", f"{top['audiAcc']:,}명")
c3.metric("스크린수", f"{top['scrnCnt']:,}개")

# ── 전체 순위표 ────────────────────────────────────────────
st.subheader("📋 순위표")

# 영화명 옆에 붙일 표시를 미리 만들어 둔다.
# - 전일 대비 순위가 오르면 빨간 ▲, 내리면 파란 ▼, 그대로면 회색 －
# - 누적관객이 100만 명을 넘으면 영화명 앞에 🏆(트로피)를 붙인다
display = pd.DataFrame({
    "순위": df["rank"],
    "전일대비": df["rankInten"].apply(rank_change_html),
    "영화명": df.apply(
        lambda row: ("🏆 " if row["audiAcc"] >= 1_000_000 else "") + row["movieNm"],
        axis=1,
    ),
    "개봉일": df["openDt"],
    "관객수": df["audiCnt"].map("{:,}".format),
    "누적관객": df["audiAcc"].map("{:,}".format),
    "스크린수": df["scrnCnt"].map("{:,}".format),
})

# 화살표 색깔은 HTML(span style)로 넣어야 하므로, st.dataframe 대신
# HTML 표로 직접 그린다(escape=False로 넣은 HTML 태그가 그대로 렌더링되게 한다).
table_html = display.to_html(escape=False, index=False)
st.markdown(
    """
    <style>
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 6px 10px; text-align: center; border-bottom: 1px solid #e9ecef; }
    th { background-color: #f1f3f5; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(table_html, unsafe_allow_html=True)

# ── 관객수 상위 5편은 막대그래프로 ───────────────────────────
st.subheader("📊 관객수 상위 5편")
top5 = df.sort_values("audiCnt", ascending=False).head(5)
fig = px.bar(top5, x="movieNm", y="audiCnt", labels={"movieNm": "영화명", "audiCnt": "관객수"})
st.plotly_chart(fig, width="stretch")
