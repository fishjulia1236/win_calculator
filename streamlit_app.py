import streamlit as st
import pandas as pd
from datetime import datetime

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="算牌計算器", layout="wide")

CARDS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
FACE_CARDS = {"10","J","Q","K"}

# 讓按鈕更像鍵盤：矮一點、字大一點
st.markdown("""
<style>
.stButton > button {
    padding: 0.35rem 0.2rem !important;
    height: 2.15rem !important;
    font-size: 1.05rem !important;
}
</style>
""", unsafe_allow_html=True)

def card_value_baccarat(card: str) -> int:
    """百家樂點數：A=1, 2-9=本身, 10/J/Q/K=0"""
    if card is None:
        return 0
    if card == "A":
        return 1
    if card in ["10","J","Q","K"]:
        return 0
    return int(card)

def hand_total(cards) -> int:
    """cards: list[str|None], 回傳 (sum % 10)"""
    s = 0
    for c in cards:
        if c is None:
            continue
        s += card_value_baccarat(c)
    return s % 10

def flip_side(side: str) -> str:
    if side == "莊":
        return "閒"
    if side == "閒":
        return "莊"
    return "-"

# =========================
# ✅ 手機友善選牌：expander + 按鈕鍵盤
# =========================
def card_picker(key: str, label: str, allow_none: bool = False):
    # 初始化預設值（避免 KeyError）
    if key not in st.session_state:
        st.session_state[key] = "A" if not allow_none else None

    cur = st.session_state.get(key, None)
    cur_show = "None" if cur is None else cur

    # 收合狀態只顯示目前選到的值；點開才看到鍵盤
    with st.expander(f"{label}（目前：{cur_show}）", expanded=False):
        row1 = ["A","2","3","4","5","6"]
        row2 = ["7","8","9","10","J","Q","K"]

        cols = st.columns(len(row1))
        for i, c in enumerate(row1):
            if cols[i].button(c, key=f"{key}__btn__{c}"):
                st.session_state[key] = c

        cols = st.columns(len(row2))
        for i, c in enumerate(row2):
            if cols[i].button(c, key=f"{key}__btn__{c}"):
                st.session_state[key] = c

        if allow_none:
            if st.button("None（無補牌）", key=f"{key}__btn__None"):
                st.session_state[key] = None

    return st.session_state.get(key, None)

# =========================
# 方法1：跑牌值A（含翻邊規則）
# =========================
def method1_run_value(p_cards, b_cards, p_total, b_total):
    run_value = p_total + b_total

    # 原始判定
    if run_value == 0:
        base = "-"
    elif 1 <= run_value <= 9:
        base = "閒"
    else:
        base = "莊"

    # 翻邊規則判定
    has_draw = (p_cards[2] is not None) or (b_cards[2] is not None)

    first4 = [p_cards[0], p_cards[1], b_cards[0], b_cards[1]]
    no_face_first4 = all((c not in FACE_CARDS) for c in first4 if c is not None)

    is_natural = (not has_draw) and ( (p_total in [8,9]) or (b_total in [8,9]) )

    flip_flag = False
    reason = []
    if has_draw:
        flip_flag = True
        reason.append("有補牌")
    if is_natural and no_face_first4:
        flip_flag = True
        reason.append("例牌勝出(前四張無公牌)")

    final_pred = flip_side(base) if (flip_flag and base in ["莊","閒"]) else base

    info = {
        "run_value": run_value,
        "base": base,
        "flip": flip_flag,
        "flip_reason": "、".join(reason) if reason else "否"
    }
    return final_pred, info

# =========================
# 方法2：矩陣算牌
# =========================
def method2_matrix(p_cards, b_cards, p_total, b_total):
    all_cards = [c for c in (p_cards + b_cards) if c is not None]
    face_count = sum(1 for c in all_cards if c in FACE_CARDS)

    diff = p_total - b_total
    sign = -1 if (face_count % 2 == 1) else 1
    score = diff * sign

    if score > 0:
        pred = "閒"
    elif score < 0:
        pred = "莊"
    else:
        pred = "-"

    info = {"diff": diff, "face_count": face_count, "sign": sign, "score": score}
    return pred, info

# =========================
# 方法3：計數公式（只算本局）
# =========================
COUNT_W = {
    "A": 1, "2": 1, "3": 1,
    "4": 2,
    "5": 1, "6": 1, "7": 1,
    "8": 0,
    "9": -1, "10": -1, "J": -1, "Q": -1, "K": -1
}

def method3_count(p_cards, b_cards):
    all_cards = [c for c in (p_cards + b_cards) if c is not None]
    s = sum(COUNT_W.get(c, 0) for c in all_cards)

    if s > 2:
        pred = "莊"
    elif s < 2:
        pred = "閒"
    else:
        pred = "-"

    return pred, {"count": s}

# =========================
# Session state
# =========================
if "records" not in st.session_state:
    st.session_state.records = pd.DataFrame(columns=[
        "ts",
        "P1","P2","P3","B1","B2","B3",
        "P_total","B_total","actual",
        "m1_pred","m2_pred","m3_pred",
        "m1_run","m1_flip","m1_flip_reason",
        "m2_diff","m2_face","m2_sign","m2_score",
        "m3_count",
    ])

def compute_actual(p_total, b_total) -> str:
    if p_total > b_total:
        return "閒贏"
    if b_total > p_total:
        return "莊贏"
    return "和"

# =========================
# 統計計算（含最高連贏/最高連輸）
# =========================
def calc_method_stats(df: pd.DataFrame, pred_col: str):
    actual_side = df["actual"].map({"閒贏":"閒","莊贏":"莊"}).fillna("-")
    pred = df[pred_col].fillna("-")

    effective_mask = pred.isin(["莊","閒"]) & actual_side.isin(["莊","閒"])
    eff_df = df.loc[effective_mask].copy()
    if eff_df.empty:
        return {"effective": 0, "hits": 0, "winrate": None, "max_win": 0, "max_loss": 0}

    eff_actual = eff_df["actual"].map({"閒贏":"閒","莊贏":"莊"})
    eff_pred = eff_df[pred_col]
    hits_series = (eff_pred == eff_actual)

    effective = int(len(eff_df))
    hits = int(hits_series.sum())
    winrate = hits / effective if effective > 0 else None

    max_win = 0
    max_loss = 0
    cur_win = 0
    cur_loss = 0
    for ok in hits_series.tolist():
        if ok:
            cur_win += 1
            cur_loss = 0
            max_win = max(max_win, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            max_loss = max(max_loss, cur_loss)

    return {"effective": effective, "hits": hits, "winrate": winrate, "max_win": max_win, "max_loss": max_loss}

# =========================
# UI Tabs
# =========================
tab1, tab2 = st.tabs(["🧮 算牌介面", "📝 歷史紀錄 / 勝率統計"])

# =========================
# Tab 1：算牌介面
# =========================
with tab1:
    st.title("🧮算牌工具（下局預測 / 不套房態）")

    colL, colR = st.columns(2)

    with colL:
        st.subheader("輸入本局牌局（閒 P）")
        P1 = card_picker("P1", "P1")
        P2 = card_picker("P2", "P2")
        P3 = card_picker("P3", "P3（無補牌選 None）", allow_none=True)

    with colR:
        st.subheader("輸入本局牌局（莊 B）")
        B1 = card_picker("B1", "B1")
        B2 = card_picker("B2", "B2")
        B3 = card_picker("B3", "B3（無補牌選 None）", allow_none=True)

    # ✅ 按鍵放在「輸入下面」：更快記錄
    st.markdown("---")
    colA, colB, colC = st.columns([1,1,2])
    with colA:
        add_btn = st.button("➕ 加入本局紀錄", use_container_width=True)
    with colB:
        clear_btn = st.button("🗑️ 清空全部紀錄", use_container_width=True)
    with colC:
        st.caption("提示：和局會被記錄，但不列入各方法命中率/連勝連敗。")

    if clear_btn:
        st.session_state.records = st.session_state.records.iloc[0:0].copy()
        st.success("已清空全部紀錄。")

    p_cards = [P1, P2, P3]
    b_cards = [B1, B2, B3]
    p_total = hand_total(p_cards)
    b_total = hand_total(b_cards)
    auto_actual = compute_actual(p_total, b_total)

    st.header("本局點數")
    st.write(f"閒點數：**{p_total}**   |   莊點數：**{b_total}**   |   本局結果：**{auto_actual}**")

    actual_choice = st.radio(
        "本局『實際結果』以哪個為準？（可覆蓋自動判定）",
        ["自動判定", "閒贏", "莊贏", "和"],
        horizontal=True,
        index=0
    )
    actual = auto_actual if actual_choice == "自動判定" else actual_choice

    # 三方法計算
    m1_pred, m1_info = method1_run_value(p_cards, b_cards, p_total, b_total)
    m2_pred, m2_info = method2_matrix(p_cards, b_cards, p_total, b_total)
    m3_pred, m3_info = method3_count(p_cards, b_cards)

    st.markdown("---")
    st.header("🎯 下局預測（由本局牌計算，不套房態）")

    st.write(
        f"方法1（跑牌值A）：跑牌值=**{m1_info['run_value']}**（閒{p_total}+莊{b_total}）"
        f" | 原始=**{m1_info['base']}**"
        f" | 翻邊=**{'是' if m1_info['flip'] else '否'}**（{m1_info['flip_reason']}）"
        f" | 最終預測=**{m1_pred if m1_pred!='-' else '觀望'}**"
    )

    st.write(
        f"方法2（矩陣算牌）：最終預測=**{m2_pred if m2_pred!='-' else '觀望'}**"
        f" | (diff={m2_info['diff']}, 公牌數={m2_info['face_count']}, sign={m2_info['sign']}, score={m2_info['score']})"
    )

    st.write(
        f"方法3（計數公式）：計數結果=**{m3_info['count']}**"
        f" | 最終預測=**{m3_pred if m3_pred!='-' else '觀望'}**"
    )

    # 一致性提示框
    consensus_123 = (m1_pred in ["莊","閒"]) and (m1_pred == m2_pred == m3_pred)
    consensus_12  = (m1_pred in ["莊","閒"]) and (m1_pred == m2_pred) and (m3_pred != m1_pred)
    consensus_13  = (m1_pred in ["莊","閒"]) and (m1_pred == m3_pred) and (m2_pred != m1_pred)
    consensus_23  = (m2_pred in ["莊","閒"]) and (m2_pred == m3_pred) and (m1_pred != m2_pred)

    if actual == "和":
        st.warning("本局開『和』：觀望（不下注）")
        st.write("上局預測（供你回看）：")
        st.write(f"- 方法1（跑牌值A）：{m1_pred if m1_pred!='-' else '觀望'}")
        st.write(f"- 方法2（矩陣算牌）：{m2_pred if m2_pred!='-' else '觀望'}")
        st.write(f"- 方法3（計數公式）：{m3_pred if m3_pred!='-' else '觀望'}")
    else:
        if consensus_123:
            st.success(f"✅ 三方法一致：**{m1_pred}**")
        elif consensus_12:
            st.info(f"ℹ️ 方法1 & 方法2 一致：**{m1_pred}**（方法3不同）")
        elif consensus_13:
            st.info(f"ℹ️ 方法1 & 方法3 一致：**{m1_pred}**（方法2不同）")
        elif consensus_23:
            st.info(f"ℹ️ 方法2 & 方法3 一致：**{m2_pred}**（方法1不同）")
        else:
            st.warning("⚠️ 尚未一致")

    # ⭐ 高勝率建議下注：勝率>50才顯示；多個方法就比對同向/分歧
    st.markdown("---")
    st.subheader("⭐ 高勝率建議下注（勝率 > 50% 才顯示）")

    df_records = st.session_state.records.copy()
    if df_records.empty:
        st.write("目前還沒有歷史紀錄，所以暫時無法計算勝率。")
    else:
        s1 = calc_method_stats(df_records, "m1_pred")
        s2 = calc_method_stats(df_records, "m2_pred")
        s3 = calc_method_stats(df_records, "m3_pred")

        items = []
        for name, stat, pred_now in [
            ("方法1（跑牌值A）", s1, m1_pred),
            ("方法2（矩陣算牌）", s2, m2_pred),
            ("方法3（計數公式）", s3, m3_pred),
        ]:
            if stat["winrate"] is not None and stat["winrate"] > 0.5:
                suggestion = pred_now if pred_now in ["莊","閒"] else "觀望"
                items.append((name, stat["winrate"], suggestion))

        if not items:
            st.write("目前沒有任何方法的歷史命中率 > 50%，所以先不顯示下注建議。")
        else:
            items_sorted = sorted(items, key=lambda x: x[1], reverse=True)
            for name, wr, sug in items_sorted:
                st.write(f"- **{name}**｜勝率 **{wr*100:.1f}%**｜本局建議：**{sug}**")

            # ✅ 同向/分歧只針對「高勝率框」判斷
            sug_list = [x[2] for x in items_sorted if x[2] in ["莊","閒"]]
            if len(sug_list) >= 2:
                if len(set(sug_list)) == 1:
                    st.success(f"同向：建議 **{sug_list[0]}**")
                else:
                    st.warning("分歧：先觀望")
            # 和局優先：直接觀望
            if actual == "和":
                st.warning("本局結果為『和』：建議先觀望，不下注。")

    # ====== 加入紀錄（真的寫入） ======
    if add_btn:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = {
            "ts": ts,
            "P1": P1, "P2": P2, "P3": ("None" if P3 is None else P3),
            "B1": B1, "B2": B2, "B3": ("None" if B3 is None else B3),
            "P_total": p_total, "B_total": b_total, "actual": actual,
            "m1_pred": m1_pred, "m2_pred": m2_pred, "m3_pred": m3_pred,
            "m1_run": m1_info["run_value"],
            "m1_flip": "是" if m1_info["flip"] else "否",
            "m1_flip_reason": m1_info["flip_reason"],
            "m2_diff": m2_info["diff"], "m2_face": m2_info["face_count"],
            "m2_sign": m2_info["sign"], "m2_score": m2_info["score"],
            "m3_count": m3_info["count"],
        }
        st.session_state.records = pd.concat(
            [st.session_state.records, pd.DataFrame([new_row])],
            ignore_index=True
        )
        st.success("已加入本局紀錄。")

# =========================
# Tab 2：歷史紀錄 / 勝率統計
# =========================
with tab2:
    st.title("📝 歷史紀錄 / 勝率統計")

    df = st.session_state.records.copy()

    if df.empty:
        st.info("目前沒有任何歷史紀錄。")
    else:
        st.subheader("累積統計（所有已記錄牌局）")
        total_n = len(df)
        pwin = int((df["actual"] == "閒贏").sum())
        bwin = int((df["actual"] == "莊贏").sum())
        tie = int((df["actual"] == "和").sum())
        st.write(f"總局數：**{total_n}**  |  閒贏：**{pwin}**  |  莊贏：**{bwin}**  |  和：**{tie}**")

        s1 = calc_method_stats(df, "m1_pred")
        s2 = calc_method_stats(df, "m2_pred")
        s3 = calc_method_stats(df, "m3_pred")

        c1, c2, c3 = st.columns(3)

        def show_method_card(col, title, stat):
            with col:
                st.markdown(f"### {title}")
                st.metric("有效局數", stat["effective"])
                st.metric("命中", stat["hits"])
                st.metric("命中率", "-" if stat["winrate"] is None else f"{stat['winrate']*100:.1f}%")
                st.metric("最高連贏", stat["max_win"])
                st.metric("最高連輸", stat["max_loss"])

        show_method_card(c1, "方法1（跑牌值A）", s1)
        show_method_card(c2, "方法2（矩陣算牌）", s2)
        show_method_card(c3, "方法3（計數公式）", s3)

        st.markdown("---")
        st.subheader("所有紀錄（可檢視）")
        st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("下載 CSV（保存你的紀錄）")
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ 下載 CSV",
        data=csv_bytes,
        file_name="baccarat_records.csv",
        mime="text/csv",
        use_container_width=True
    )
