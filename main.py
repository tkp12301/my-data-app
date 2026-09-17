# -*- coding: utf-8 -*-
"""
어제의 박스오피스(KOBIS) 스트림릿 앱
-----------------------------------
- KOBIS(영화진흥위원회) 일별 박스오피스 API를 사용합니다.
- 초보자를 위해 각 단계마다 한국어 주석을 달았습니다.
"""

# ── 1. 필요한 라이브러리 불러오기 ────────────────────────────────
import streamlit as st          # 화면(웹앱)을 그려주는 라이브러리
import requests                 # 외부 API에 요청을 보내는 라이브러리
import pandas as pd             # 표(데이터프레임)와 숫자 데이터를 다루는 라이브러리
from datetime import datetime, timedelta, timezone  # 날짜/시간 계산용


# ── 2. '어제(한국 시간 기준)' 날짜를 계산하는 함수 ───────────────
def get_yesterday_kst_str():
    """
    배포 서버의 시계가 한국 시간이 아닐 수 있으므로,
    UTC 기준 현재 시각을 구한 뒤 '+9시간'을 더해 한국 시간으로 직접 변환합니다.
    그런 다음 하루를 빼서 '어제' 날짜를 만듭니다.
    반환값 예시: "20250917" (yyyymmdd, 8자리 문자열)
    """
    kst = timezone(timedelta(hours=9))          # 한국 표준시(KST) = UTC+9
    now_kst = datetime.now(kst)                 # 지금 이 순간의 한국 시간
    yesterday_kst = now_kst - timedelta(days=1) # 하루 전 = 어제
    return yesterday_kst.strftime("%Y%m%d")     # yyyymmdd 형식의 문자열로 변환


# ── 3. KOBIS API를 호출하는 함수 (1시간 동안 결과를 기억: 캐시) ───
# @st.cache_data(ttl=3600) 를 붙이면, 같은 target_dt로 다시 호출할 때
# 1시간(3600초) 이내라면 실제 API를 또 부르지 않고 저장해둔 결과를 그대로 돌려줍니다.
@st.cache_data(ttl=3600)
def fetch_box_office(target_dt: str):
    """
    target_dt: 조회할 날짜 (yyyymmdd, 8자리 문자열)
    반환값: (성공여부: bool, 데이터 또는 에러메시지)
    """
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

    # 비밀 금고(secrets)에 KOBIS_KEY가 등록되어 있는지 먼저 확인합니다.
    # (스트림릿 클라우드의 'Secrets' 설정에 KOBIS_KEY = "발급받은키" 형식으로 넣어야 합니다.)
    if "KOBIS_KEY" not in st.secrets:
        return False, "secrets에 KOBIS_KEY가 없습니다. 스트림릿 클라우드의 Settings > Secrets에 KOBIS_KEY를 등록했는지 확인해 주세요."

    api_key = st.secrets["KOBIS_KEY"]

    params = {
        "key": api_key,
        "targetDt": target_dt,
    }

    # 네트워크 요청은 실패할 수 있으므로 try/except로 감싸줍니다.
    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return False, f"KOBIS 서버에 접속하지 못했습니다. 인터넷 연결 상태를 확인해 주세요. (오류: {e})"

    # 상태 코드가 200이 아니면 서버 자체에 문제가 있는 것입니다.
    if response.status_code != 200:
        return False, f"KOBIS 서버가 오류를 반환했습니다. (HTTP 상태코드: {response.status_code}) 잠시 후 다시 시도해 주세요."

    # 응답이 JSON 형식이 아닐 수도 있으므로 파싱도 try/except로 감쌉니다.
    try:
        data = response.json()
    except ValueError:
        return False, "KOBIS 서버 응답을 해석할 수 없습니다(JSON 형식이 아님). 요청 주소나 파라미터를 확인해 주세요."

    # 문서에 따르면 인증키가 틀려도 상태코드는 200이고,
    # 대신 응답 안에 faultInfo 상자가 들어옵니다. 이를 먼저 확인합니다.
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 오류")
        return False, (
            f"KOBIS API가 오류를 반환했습니다: {message}\n"
            "→ 인증키(KOBIS_KEY)가 올바른지, 발급 상태가 '승인'인지 확인해 주세요."
        )

    # 정상적인 경우 boxOfficeResult > dailyBoxOfficeList 안에 목록이 들어있습니다.
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except KeyError:
        return False, "응답 구조가 예상과 다릅니다(boxOfficeResult를 찾을 수 없음). KOBIS API 문서가 변경되었는지 확인해 주세요."

    # 영화 목록 자체가 비어서 오는 경우 (예: 너무 이른 날짜, 데이터 미집계 등)
    if not movie_list:
        return False, "해당 날짜의 박스오피스 데이터가 비어 있습니다. 날짜가 너무 최근이라 아직 집계되지 않았을 수 있습니다."

    return True, movie_list


# ── 4. 문자열로 온 숫자를 진짜 숫자(int)로 바꾸는 함수 ────────────
def to_int(value):
    """
    API에서 오는 숫자들은 전부 문자열("12345")로 옵니다.
    정렬이나 그래프에 쓰려면 정수(int)로 바꿔야 합니다.
    혹시 빈 문자열이거나 이상한 값이 오면 0으로 처리해 앱이 죽지 않게 합니다.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


# ── 5. 화면(페이지) 기본 설정 ─────────────────────────────────
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")
st.title("🎬 어제의 박스오피스")

target_dt = get_yesterday_kst_str()
# 화면에 보여줄 때는 보기 좋게 yyyy-mm-dd 형태로 바꿔줍니다.
target_dt_display = f"{target_dt[0:4]}-{target_dt[4:6]}-{target_dt[6:8]}"
st.caption(f"조회 기준일(한국 시간 어제): {target_dt_display}")


# ── 6. API 호출 & 결과 처리 ───────────────────────────────────
ok, result = fetch_box_office(target_dt)

if not ok:
    # 실패했을 때는 빈 화면 대신, 무엇을 확인해야 하는지 안내 메시지를 보여줍니다.
    st.error("박스오피스 데이터를 가져오지 못했습니다.")
    st.warning(result)
    st.stop()  # 여기서 실행을 멈춰서 아래 코드가 실행되지 않게 합니다.

movie_list = result

# ── 7. 문자열 숫자를 정수로 변환하여 데이터프레임 만들기 ──────────
rows = []
for movie in movie_list:
    rows.append({
        "순위": to_int(movie.get("rank")),
        "영화명": movie.get("movieNm", ""),
        "개봉일": movie.get("openDt", ""),
        "관객수": to_int(movie.get("audiCnt")),
        "누적관객": to_int(movie.get("audiAcc")),
        "스크린수": to_int(movie.get("scrnCnt")),
    })

df = pd.DataFrame(rows)
df = df.sort_values("순위").reset_index(drop=True)  # 순위 기준으로 정렬(숫자 기준이라 정확함)


# ── 8. 1위 영화 지표 카드 3장 ─────────────────────────────────
st.subheader("🏆 1위 영화")

top_movie = df.iloc[0]  # 순위 정렬 후 첫 번째 행 = 1위

col1, col2, col3 = st.columns(3)
col1.metric(label=f"{top_movie['영화명']} - 어제 관객수", value=f"{top_movie['관객수']:,} 명")
col2.metric(label="누적 관객수", value=f"{top_movie['누적관객']:,} 명")
col3.metric(label="스크린수", value=f"{top_movie['스크린수']:,} 개")


# ── 9. 관객수 상위 5편 막대그래프 ─────────────────────────────
st.subheader("📊 관객수 상위 5편")

top5 = df.sort_values("관객수", ascending=False).head(5)
# st.bar_chart는 인덱스를 x축(가로축)으로 사용하므로 영화명을 인덱스로 지정합니다.
chart_data = top5.set_index("영화명")[["관객수"]]
st.bar_chart(chart_data)


# ── 10. 전체 순위 표 ──────────────────────────────────────────
st.subheader("📋 전체 순위")

st.dataframe(
    df,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d"),
        "누적관객": st.column_config.NumberColumn(format="%d"),
        "스크린수": st.column_config.NumberColumn(format="%d"),
    },
    hide_index=True,
    use_container_width=True,
)# -*- coding: utf-8 -*-
"""
어제의 박스오피스(KOBIS) 스트림릿 앱
-----------------------------------
- KOBIS(영화진흥위원회) 일별 박스오피스 API를 사용합니다.
- 초보자를 위해 각 단계마다 한국어 주석을 달았습니다.
"""

# ── 1. 필요한 라이브러리 불러오기 ────────────────────────────────
import streamlit as st          # 화면(웹앱)을 그려주는 라이브러리
import requests                 # 외부 API에 요청을 보내는 라이브러리
import pandas as pd             # 표(데이터프레임)와 숫자 데이터를 다루는 라이브러리
from datetime import datetime, timedelta, timezone  # 날짜/시간 계산용


# ── 2. '어제(한국 시간 기준)' 날짜를 계산하는 함수 ───────────────
def get_yesterday_kst_str():
    """
    배포 서버의 시계가 한국 시간이 아닐 수 있으므로,
    UTC 기준 현재 시각을 구한 뒤 '+9시간'을 더해 한국 시간으로 직접 변환합니다.
    그런 다음 하루를 빼서 '어제' 날짜를 만듭니다.
    반환값 예시: "20250917" (yyyymmdd, 8자리 문자열)
    """
    kst = timezone(timedelta(hours=9))          # 한국 표준시(KST) = UTC+9
    now_kst = datetime.now(kst)                 # 지금 이 순간의 한국 시간
    yesterday_kst = now_kst - timedelta(days=1) # 하루 전 = 어제
    return yesterday_kst.strftime("%Y%m%d")     # yyyymmdd 형식의 문자열로 변환


# ── 3. KOBIS API를 호출하는 함수 (1시간 동안 결과를 기억: 캐시) ───
# @st.cache_data(ttl=3600) 를 붙이면, 같은 target_dt로 다시 호출할 때
# 1시간(3600초) 이내라면 실제 API를 또 부르지 않고 저장해둔 결과를 그대로 돌려줍니다.
@st.cache_data(ttl=3600)
def fetch_box_office(target_dt: str):
    """
    target_dt: 조회할 날짜 (yyyymmdd, 8자리 문자열)
    반환값: (성공여부: bool, 데이터 또는 에러메시지)
    """
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

    # 비밀 금고(secrets)에 KOBIS_KEY가 등록되어 있는지 먼저 확인합니다.
    # (스트림릿 클라우드의 'Secrets' 설정에 KOBIS_KEY = "발급받은키" 형식으로 넣어야 합니다.)
    if "KOBIS_KEY" not in st.secrets:
        return False, "secrets에 KOBIS_KEY가 없습니다. 스트림릿 클라우드의 Settings > Secrets에 KOBIS_KEY를 등록했는지 확인해 주세요."

    api_key = st.secrets["KOBIS_KEY"]

    params = {
        "key": api_key,
        "targetDt": target_dt,
    }

    # 네트워크 요청은 실패할 수 있으므로 try/except로 감싸줍니다.
    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return False, f"KOBIS 서버에 접속하지 못했습니다. 인터넷 연결 상태를 확인해 주세요. (오류: {e})"

    # 상태 코드가 200이 아니면 서버 자체에 문제가 있는 것입니다.
    if response.status_code != 200:
        return False, f"KOBIS 서버가 오류를 반환했습니다. (HTTP 상태코드: {response.status_code}) 잠시 후 다시 시도해 주세요."

    # 응답이 JSON 형식이 아닐 수도 있으므로 파싱도 try/except로 감쌉니다.
    try:
        data = response.json()
    except ValueError:
        return False, "KOBIS 서버 응답을 해석할 수 없습니다(JSON 형식이 아님). 요청 주소나 파라미터를 확인해 주세요."

    # 문서에 따르면 인증키가 틀려도 상태코드는 200이고,
    # 대신 응답 안에 faultInfo 상자가 들어옵니다. 이를 먼저 확인합니다.
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 오류")
        return False, (
            f"KOBIS API가 오류를 반환했습니다: {message}\n"
            "→ 인증키(KOBIS_KEY)가 올바른지, 발급 상태가 '승인'인지 확인해 주세요."
        )

    # 정상적인 경우 boxOfficeResult > dailyBoxOfficeList 안에 목록이 들어있습니다.
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except KeyError:
        return False, "응답 구조가 예상과 다릅니다(boxOfficeResult를 찾을 수 없음). KOBIS API 문서가 변경되었는지 확인해 주세요."

    # 영화 목록 자체가 비어서 오는 경우 (예: 너무 이른 날짜, 데이터 미집계 등)
    if not movie_list:
        return False, "해당 날짜의 박스오피스 데이터가 비어 있습니다. 날짜가 너무 최근이라 아직 집계되지 않았을 수 있습니다."

    return True, movie_list


# ── 4. 문자열로 온 숫자를 진짜 숫자(int)로 바꾸는 함수 ────────────
def to_int(value):
    """
    API에서 오는 숫자들은 전부 문자열("12345")로 옵니다.
    정렬이나 그래프에 쓰려면 정수(int)로 바꿔야 합니다.
    혹시 빈 문자열이거나 이상한 값이 오면 0으로 처리해 앱이 죽지 않게 합니다.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


# ── 5. 화면(페이지) 기본 설정 ─────────────────────────────────
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")
st.title("🎬 어제의 박스오피스")

target_dt = get_yesterday_kst_str()
# 화면에 보여줄 때는 보기 좋게 yyyy-mm-dd 형태로 바꿔줍니다.
target_dt_display = f"{target_dt[0:4]}-{target_dt[4:6]}-{target_dt[6:8]}"
st.caption(f"조회 기준일(한국 시간 어제): {target_dt_display}")


# ── 6. API 호출 & 결과 처리 ───────────────────────────────────
ok, result = fetch_box_office(target_dt)

if not ok:
    # 실패했을 때는 빈 화면 대신, 무엇을 확인해야 하는지 안내 메시지를 보여줍니다.
    st.error("박스오피스 데이터를 가져오지 못했습니다.")
    st.warning(result)
    st.stop()  # 여기서 실행을 멈춰서 아래 코드가 실행되지 않게 합니다.

movie_list = result

# ── 7. 문자열 숫자를 정수로 변환하여 데이터프레임 만들기 ──────────
rows = []
for movie in movie_list:
    rows.append({
        "순위": to_int(movie.get("rank")),
        "영화명": movie.get("movieNm", ""),
        "개봉일": movie.get("openDt", ""),
        "관객수": to_int(movie.get("audiCnt")),
        "누적관객": to_int(movie.get("audiAcc")),
        "스크린수": to_int(movie.get("scrnCnt")),
    })

df = pd.DataFrame(rows)
df = df.sort_values("순위").reset_index(drop=True)  # 순위 기준으로 정렬(숫자 기준이라 정확함)


# ── 8. 1위 영화 지표 카드 3장 ─────────────────────────────────
st.subheader("🏆 1위 영화")

top_movie = df.iloc[0]  # 순위 정렬 후 첫 번째 행 = 1위

col1, col2, col3 = st.columns(3)
col1.metric(label=f"{top_movie['영화명']} - 어제 관객수", value=f"{top_movie['관객수']:,} 명")
col2.metric(label="누적 관객수", value=f"{top_movie['누적관객']:,} 명")
col3.metric(label="스크린수", value=f"{top_movie['스크린수']:,} 개")


# ── 9. 관객수 상위 5편 막대그래프 ─────────────────────────────
st.subheader("📊 관객수 상위 5편")

top5 = df.sort_values("관객수", ascending=False).head(5)
# st.bar_chart는 인덱스를 x축(가로축)으로 사용하므로 영화명을 인덱스로 지정합니다.
chart_data = top5.set_index("영화명")[["관객수"]]
st.bar_chart(chart_data)


# ── 10. 전체 순위 표 ──────────────────────────────────────────
st.subheader("📋 전체 순위")

st.dataframe(
    df,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d"),
        "누적관객": st.column_config.NumberColumn(format="%d"),
        "스크린수": st.column_config.NumberColumn(format="%d"),
    },
    hide_index=True,
    use_container_width=True,
)
