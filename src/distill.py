"""蒸馏引擎：清洗 → 热词/梗检测 → 情感分析 → 主题聚类 → up主观点提炼 → 摘要。"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .common import clean_text, log

# ---------- 停用词与词典 ----------

STOPWORDS = {
    "一个", "两个", "很多", "多少", "所有", "每个", "部分", "什么", "怎么", "为什么",
    "我们", "你们", "他们", "自己", "别人", "大家", "这个", "那个", "这些", "那些",
    "这里", "那里", "这样", "那样", "这么", "那么", "可以", "应该", "需要", "没有",
    "不是", "就是", "还是", "只是", "但是", "因为", "所以", "如果", "虽然", "而且",
    "并且", "或者", "然后", "然而", "因此", "同时", "目前", "现在", "今天", "昨天",
    "明天", "上午", "下午", "晚上", "早上", "盘中", "收盘", "开盘", "时候", "情况",
    "结果", "问题", "事情", "东西", "地方", "内容", "信息", "数据", "可能", "已经",
    "一直", "真的", "非常", "开始", "感觉", "觉得", "知道", "应该", "有些", "有点",
    "一下", "一样", "以上", "以下", "以来", "之前", "之后", "之间", "方面", "对于",
    "关于", "根据", "由于", "通过", "进行", "出现", "影响", "相关", "以及", "还有",
    "而且", "其中", "主要", "重要", "一定", "一般", "特别", "比较", "越来越", "不少",
    "基本上", "实际上", "的时候", "的话", "还是", "是不是", "有没有", "能不能",
}

STOP_CHARS = set("的了是我你他她它们都在和有与或但并且很不太也会就来去看把被让给对从向为着过")
MEME_STOP_TAIL = ("的", "了", "呢", "吗", "吧", "啊", "呀", "哦", "嘛")

FIN_TERMS = [
    "涨停", "跌停", "大涨", "大跌", "暴涨", "暴跌", "拉升", "跳水", "反弹", "回调",
    "突破", "破位", "新高", "新低", "利好", "利空", "牛市", "熊市", "主力", "散户",
    "机构", "游资", "北向资金", "外资", "内资", "加仓", "减仓", "买入", "卖出",
    "抄底", "割肉", "梭哈", "满仓", "清仓", "空仓", "半仓", "融资", "融券", "分红",
    "回购", "增持", "减持", "重组", "并购", "定增", "解禁", "质押", "爆雷", "暴雷",
    "退市", "st", "ST", "板块", "赛道", "龙头", "妖股", "白马", "蓝筹", "题材",
    "概念", "热点", "情绪", "量能", "放量", "缩量", "换手", "成交量", "市值", "估值",
    "市盈率", "业绩", "财报", "年报", "季报", "中报", "一季报", "营收", "净利润",
    "毛利率", "净利率", "现金流", "负债率", "ipo", "IPO", "注册制", "t+0", "印花税",
    "降息", "降准", "加息", "通胀", "通缩", "汇率", "人民币", "美元", "美联储",
    "加息", "缩表", "扩表", "国债", "美债", "中概", "港股", "A股", "美股", "科创",
    "创业板", "科创板", "北交所", "新三板", "ai", "AI", "芯片", "半导体", "算力",
    "大模型", "人工智能", "机器人", "新能源", "光伏", "锂电", "储能", "风电", "氢能",
    "军工", "消费", "白酒", "医药", "医疗", "银行", "保险", "券商", "地产", "基建",
    "有色", "煤炭", "石油", "天然气", "黄金", "稀土", "汽车", "整车", "零部件",
    "游戏", "传媒", "教育", "旅游", "航空", "免税", "快递", "物流", "电商", "零售",
    "家电", "食品", "饮料", "农业", "养殖", "猪", "粮", "棉花", "白糖", "茅台",
    "五粮液", "宁德", "比亚迪", "平安", "腾讯", "阿里", "百度", "美团", "京东",
]

FIN_POS = [
    "涨", "大涨", "涨停", "暴涨", "拉升", "反弹", "突破", "新高", "利好", "看好",
    "买入", "加仓", "增持", "抄底", "起飞", "走牛", "牛市", "赚钱", "盈利", "分红",
    "回购", "反转", "企稳", "放量上涨", "资金流入", "主力流入", "护盘", "强", "牛",
    "赚", "梭哈", "满仓", "冲", "干", "回血", "吃肉", "真香", "机会", "潜力", "低估",
    "便宜", "布局", "持有", "坚定", "乐观", "信心", "希望", "期待", "稳了", "起飞",
]

FIN_NEG = [
    "跌", "大跌", "跌停", "暴跌", "跳水", "回调", "破位", "新低", "利空", "看空",
    "卖出", "减仓", "减持", "割肉", "崩盘", "熊市", "亏钱", "亏损", "套牢", "阴跌",
    "缩量", "资金流出", "主力流出", "出货", "弱", "差", "亏", "崩", "跑路", "清仓",
    "退市", "暴雷", "爆雷", "雷", "腰斩", "雪崩", "骗子", "割韭菜", "接盘", "骗局",
    "风险", "警惕", "危险", "恐慌", "悲观", "失望", "崩了", "完了", "凉了", "没了",
    "割", "套", "站岗", "吃面", "护盘失败",
]

GENERIC_MEME = {
    "市场", "中国", "银行", "科技", "板块", "大涨", "大跌", "反弹", "回调", "上涨", "下跌",
    "今天", "目前", "现在", "应该", "可以", "一个", "什么", "这个", "那个", "时候", "情况",
    "已经", "没有", "就是", "还是", "真的", "觉得", "知道", "问题", "结果", "可能", "需要",
    "相关", "同时", "以及", "等等", "平安", "茅台", "比亚迪", "贵州", "股票", "股市", "基金",
    "投资", "资金", "主力", "散户", "机构", "大家", "走势", "行情", "概念", "热点", "关注",
    "涨停", "跌停", "上市", "公司", "行业", "业绩", "增长", "新高", "新低", "压力", "支撑",
    "昨天", "今日", "明日", "周", "月", "日", "点", "万", "亿", "元", "股", "只", "个",
    "整体", "明显", "持续", "进一步", "同比", "环比", "据悉", "表示", "认为", "其中",
    "交易日", "个交易日", "上市公司", "个股", "基金", "必须上涨", "股必须上",
    "上证指数", "深证成指", "创业板指", "科创", "北向", "净买入", "净卖出",
    "大家好", "制作", "约束", "上次", "评价", "代表", "罚万元", "给大家", "本期",
    "这一期", "这期", "欢迎", "收看", "订阅", "点赞", "三连", "关注我",
}

# 高频模板/机器生成内容的子串黑名单（命中即剔除，避免“雪球热门股票”“财联社月日电”这类碎片）
MEME_BLOCK_SUB = (
    "雪球热门股票", "雪球热门", "热门股票", "雪球热股", "财联社月日电", "月日电",
    "日电", "联社月日", "财联社", "联社", "板块领涨", "板块领跌", "领涨股",
    "涨跌幅上", "跌幅上", "上涨家", "下跌家", "领涨家", "家上涨", "家下跌",
    "热度", "点击", "阅读", "分享", "回复", "B站热搜", "站热搜", "站热",
    "热搜", "财联", "社月日", "月日",
)
_MEME_BLOCK_RE = re.compile("|".join(re.escape(b) for b in MEME_BLOCK_SUB))


# ---------- 分词与特征 ----------

def _clean_for_ngram(text: str) -> str:
    s = clean_text(text, 300)
    # 只保留 CJK 字符，其余（英文/数字/标点/表情）替换为空格，便于做中文 n-gram
    s = re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbf]+", " ", s)
    return s.replace(" ", "")


def ngrams(text: str, n: int) -> List[str]:
    s = _clean_for_ngram(text)
    if len(s) < n:
        return []
    return [s[i : i + n] for i in range(len(s) - n + 1)]


def _valid_gram(g: str) -> bool:
    if not g or g in STOPWORDS:
        return False
    if any(c in STOP_CHARS for c in g):
        return False
    if g[-1] in MEME_STOP_TAIL:
        return False
    if all(c in "0123456789 " for c in g):
        return False
    if len(set(g)) == 1:
        return False  # 支支支支 / 哈哈 这类重复单字无信息量
    return True


def _post_text(p: Dict[str, Any]) -> str:
    parts = [p.get("title", ""), p.get("content", "")]
    return " ".join(clean_text(x, 200) for x in parts if x)


def _is_machine_post(p: Dict[str, Any]) -> bool:
    """板块行情、热股榜等机器生成的摘要不参与热词/梗统计（避免模板碎片）。"""
    return (
        p.get("source") == "sector"
        or p.get("kind") in ("sector", "hot_stock", "em_hot_stock", "em_hot_concept", "em_hot_keyword")
    )


def _heat(p: Dict[str, Any]) -> float:
    def _n(v: Any) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    likes = _n(p.get("likes"))
    views = _n(p.get("views"))
    comments = _n(p.get("comments"))
    return math.log1p(likes) + math.log1p(views) * 0.5 + math.log1p(comments) * 0.8


def _token_candidates(posts: List[Dict[str, Any]], protected: Optional[Iterable[str]] = None) -> Counter:
    counter: Counter = Counter()
    prot = [p for p in (protected or []) if p]
    for p in posts:
        text = _post_text(p)
        for term in prot:
            if term and term in text:
                counter[term] += 1
        for term in FIN_TERMS:
            if term and term in text:
                counter[term] += 1
        for g in ngrams(text, 2):
            if _valid_gram(g):
                counter[g] += 1
    return counter


# ---------- 关键词 ----------

_DATE_FRAG_RE = re.compile(r"^[年月日时分周]+$")


def _dedupe_terms(
    scored: List[Dict[str, Any]], protected: Optional[set] = None
) -> List[Dict[str, Any]]:
    """按长度从长到短去重：短碎片若被更长的高频词覆盖则剔除（自选股等受保护词除外）。"""
    prot = set(protected or [])
    kept: List[Dict[str, Any]] = []
    for m in sorted(scored, key=lambda x: (-len(x["text"]), -x["score"], -x["freq"])):
        if m["text"] in prot:
            kept.append(m)
            continue
        # 只有长词频次达到碎片的一半以上才认为碎片是它的切分噪声，否则两者独立保留
        if any(m["text"] in k["text"] and k["freq"] >= 2 and k["freq"] * 2 >= m["freq"] for k in kept):
            continue
        kept.append(m)
    return kept


def _lcs_len(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    dp = [[0] * (lb + 1) for _ in range(la + 1)]
    best = 0
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                best = max(best, dp[i][j])
    return best


def _drop_overlapping(scored: List[Dict[str, Any]], min_len: int = 5) -> List[Dict[str, Any]]:
    """去掉同一长句的不同滑窗碎片（5 字以上、公共子串极长的只保留一个）。"""
    out: List[Dict[str, Any]] = []
    for m in sorted(scored, key=lambda x: (-x["score"], -x["freq"])):
        drop = False
        for k in out:
            la, lb = len(m["text"]), len(k["text"])
            mlen = min(la, lb)
            if mlen < min_len:
                continue
            if m["text"] in k["text"] or k["text"] in m["text"]:
                drop = True
                break
            if abs(la - lb) <= 1 and _lcs_len(m["text"], k["text"]) >= mlen - 2:
                drop = True
                break
        if not drop:
            out.append(m)
    return out


def extract_keywords(
    posts: List[Dict[str, Any]], top_k: int = 24, protected: Optional[Iterable[str]] = None
) -> List[Dict[str, Any]]:
    """热词：自选股/金融词按全文出现次数统计，n-gram 按窗口出现次数统计，再做碎片去重。"""
    if not posts:
        return []
    counter: Counter = Counter()
    sources: Dict[str, set] = {}
    examples: Dict[str, str] = {}
    ex_heat: Dict[str, float] = {}
    prot = list(protected or [])
    for p in posts:
        if _is_machine_post(p):
            continue
        text = _post_text(p)
        src = p.get("source", "")
        example = (p.get("title") or p.get("content", ""))[:60]
        heat = _heat(p)
        for term in prot:
            if term and term in text:
                counter[term] += text.count(term)
                sources.setdefault(term, set()).add(src)
                if heat > ex_heat.get(term, 0):
                    ex_heat[term] = heat
                    examples[term] = example
        for term in FIN_TERMS:
            if term and term in text:
                counter[term] += text.count(term)
                sources.setdefault(term, set()).add(src)
                if heat > ex_heat.get(term, 0):
                    ex_heat[term] = heat
                    examples[term] = example
        for n in (2, 3, 4):
            for g in ngrams(text, n):
                if not _valid_gram(g) or _DATE_FRAG_RE.match(g):
                    continue
                if _MEME_BLOCK_RE.search(g):
                    continue
                counter[g] += 1
                sources.setdefault(g, set()).add(src)
                if heat > ex_heat.get(g, 0):
                    ex_heat[g] = heat
                    examples[g] = example
    scored = []
    for gram, freq in counter.items():
        if freq < 2:
            continue
        div = len(sources.get(gram, set()))
        score = freq * (1 + div * 0.5) * (1 + math.log1p(freq) * 0.3)
        scored.append({
            "text": gram,
            "freq": freq,
            "sources": sorted(sources.get(gram, set())),
            "score": round(score, 2),
            "example": examples.get(gram, "")[:80],
        })
    scored.sort(key=lambda x: (x["score"], x["freq"]), reverse=True)
    scored = _dedupe_terms(scored, set(prot))
    scored = _drop_overlapping(scored, min_len=4)
    return scored[:top_k]


# ---------- 梗检测 ----------

def detect_memes(
    posts: List[Dict[str, Any]],
    top_k: int = 16,
    min_freq: int = 2,
    protected: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """高频短语/梗：统计 2~8 字中文短语出现次数，合并重复、剔除通用词与日期碎片。"""
    if not posts:
        return []
    prot_set = set(p or "" for p in (protected or []))
    counter: Counter = Counter()
    sources: Dict[str, set] = {}
    heat: Dict[str, float] = {}
    examples: Dict[str, str] = {}
    ex_heat: Dict[str, float] = {}
    for p in posts:
        if _is_machine_post(p):
            continue
        text = _post_text(p)
        h = _heat(p)
        src = p.get("source", "")
        example = (p.get("title") or p.get("content", ""))[:80]
        for n in (3, 4, 5, 6, 7, 8):
            for g in ngrams(text, n):
                if not _valid_gram(g):
                    continue
                if g in GENERIC_MEME or g.strip() in GENERIC_MEME:
                    continue
                if _DATE_FRAG_RE.match(g):
                    continue
                if _MEME_BLOCK_RE.search(g):
                    continue
                counter[g] += 1
                sources.setdefault(g, set()).add(src)
                heat[g] = heat.get(g, 0.0) + h
                if h > ex_heat.get(g, 0):
                    ex_heat[g] = h
                    examples[g] = example
    scored = []
    for gram, freq in counter.items():
        if freq < min_freq:
            continue
        div = len(sources.get(gram, set()))
        len_bonus = 1.1 if len(gram) == 3 else (1.0 if len(gram) == 4 else 0.9)
        score = (freq ** 1.05) * (1 + div * 0.4) * (1 + math.log1p(heat.get(gram, 0))) * len_bonus
        scored.append({
            "text": gram,
            "freq": freq,
            "sources": sorted(sources.get(gram, set())),
            "heat": round(heat.get(gram, 0), 1),
            "score": round(score, 2),
            "example": examples.get(gram, "")[:120],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    deduped = _dedupe_terms(scored, prot_set)
    deduped = _drop_overlapping(deduped)
    return deduped[:top_k]


# ---------- 情感 ----------

def sentiment(text: str) -> Dict[str, Any]:
    s = clean_text(text, 400)
    pos = 0
    neg = 0
    hit_pos: List[str] = []
    hit_neg: List[str] = []
    for w in FIN_POS:
        if w and w in s:
            c = s.count(w)
            pos += c
            hit_pos.append(w)
    for w in FIN_NEG:
        if w and w in s:
            c = s.count(w)
            neg += c
            hit_neg.append(w)
    if pos == 0 and neg == 0:
        return {"score": 0.0, "label": "中性", "pos": 0, "neg": 0}
    raw = (pos - neg) / (pos + neg)
    score = round(max(-1.0, min(1.0, raw * (1 + math.log1p(pos + neg) * 0.25))), 3)
    label = "看多" if score >= 0.15 else ("看空" if score <= -0.15 else "中性")
    return {"score": score, "label": label, "pos": pos, "neg": neg}


def aggregate_sentiment(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not posts:
        return {"score": 0.0, "label": "中性", "pos_posts": 0, "neg_posts": 0, "neutral_posts": 0, "by_source": {}}
    by_source: Dict[str, Dict[str, Any]] = {}
    pos_posts = neg_posts = neutral_posts = 0
    total = 0.0
    for p in posts:
        if p.get("kind") == "comment":
            continue
        s = sentiment(_post_text(p))
        src = p.get("source", "?")
        b = by_source.setdefault(src, {"score": 0.0, "n": 0, "pos_posts": 0, "neg_posts": 0})
        b["n"] += 1
        b["score"] += s["score"]
        if s["label"] == "看多":
            b["pos_posts"] += 1
            pos_posts += 1
        elif s["label"] == "看空":
            b["neg_posts"] += 1
            neg_posts += 1
        else:
            neutral_posts += 1
        total += s["score"]
    n = pos_posts + neg_posts + neutral_posts
    avg = round(total / n, 3) if n else 0.0
    label = "看多" if avg >= 0.15 else ("看空" if avg <= -0.15 else "中性")
    for src, b in by_source.items():
        b["score"] = round(b["score"] / b["n"], 3) if b["n"] else 0.0
    return {
        "score": avg,
        "label": label,
        "pos_posts": pos_posts,
        "neg_posts": neg_posts,
        "neutral_posts": neutral_posts,
        "by_source": by_source,
    }


# ---------- 主题聚类 ----------

def _top_terms(text: str, prot: List[str], k: int = 6) -> List[str]:
    hits = [t for t in prot if t and t in text]
    grams: Counter = Counter()
    for g in ngrams(text, 2):
        if _valid_gram(g):
            grams[g] += 1
    top = [g for g, _ in grams.most_common(k)]
    return (hits + top)[:k]


def cluster_topics(
    posts: List[Dict[str, Any]],
    watchlist: Iterable[Dict[str, Any]],
    top_k: int = 8,
    excluded_authors: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    # 模板化内容（热搜/排行/热股榜/评论）不参与话题聚类，避免“雪球/热搜”这类源名成为主题
    posts = [
        p for p in posts
        if p.get("kind") not in (
            "hot_search", "ranking", "comment", "hot_stock",
            "em_hot_stock", "em_hot_concept", "em_hot_keyword",
        )
    ]
    excluded = set(a or "" for a in (excluded_authors or []))
    if excluded:
        posts = [p for p in posts if (p.get("author") or "") not in excluded]
    if not posts:
        return []
    stocks = [(str(s.get("name", "")), str(s.get("code", ""))) for s in watchlist if s.get("name")]
    prot = [n for n, _ in stocks] + [c for _, c in stocks] + FIN_TERMS
    clusters: List[Dict[str, Any]] = []
    seen = set()
    for p in posts:
        text = _post_text(p)
        stock = next((n for n, c in stocks if (n and n in text) or (c and c in text)), None)
        if stock:
            clusters.append({"label": f"{stock}", "posts": [p]})
            seen.add(id(p))
    # 剩余帖子按关键词重叠贪心聚类
    rest = [p for p in posts if id(p) not in seen]
    term_sets = [(p, set(_top_terms(_post_text(p), prot))) for p in rest]
    used = set()
    for p, terms in term_sets:
        if id(p) in used:
            continue
        cluster = [p]
        used.add(id(p))
        for q, qterms in term_sets:
            if id(q) in used:
                continue
            if terms & qterms:
                cluster.append(q)
                used.add(id(q))
        if len(cluster) >= 2:
            label = _cluster_label(cluster, prot)
            clusters.append({"label": label, "posts": cluster})
    out = []
    for cl in clusters:
        cposts = cl["posts"]
        s = aggregate_sentiment(cposts)
        phrases = extract_keywords(cposts, top_k=5, protected=prot)
        sorted_posts = sorted(cposts, key=_heat, reverse=True)
        out.append({
            "label": cl["label"],
            "count": len(cposts),
            "sentiment": s["label"],
            "score": s["score"],
            "phrases": [x["text"] for x in phrases[:5]],
            "top_posts": [
                {
                    "source": x.get("source", ""),
                    "title": (x.get("title") or "")[:70],
                    "url": x.get("url", ""),
                    "likes": x.get("likes", 0),
                    "views": x.get("views", 0),
                }
                for x in sorted_posts[:4]
            ],
        })
    out.sort(key=lambda x: x["count"], reverse=True)
    return out[:top_k]


def _cluster_label(posts: List[Dict[str, Any]], prot: List[str]) -> str:
    blocked = {"雪球", "股吧", "同花顺", "金十", "财联社", "B站", "热搜", "排行", "热帖", "热股", "板块"}
    counter: Counter = Counter()
    for p in posts:
        text = _post_text(p)
        for t in prot:
            if t and t in text:
                counter[t] += 1
        for g in ngrams(text, 2):
            if _valid_gram(g):
                counter[g] += 1
    for g, _ in counter.most_common():
        if g not in blocked:
            return g
    return "其他"


# ---------- up主分析 ----------

def analyze_upmasters(upmasters: List[Dict[str, Any]], top_comments: int = 8) -> List[Dict[str, Any]]:
    out = []
    for up in upmasters:
        name = up.get("name", "")
        videos = up.get("videos", []) or []
        dynamics = up.get("dynamics", []) or []
        analyzed = []
        dyn_analyzed = []
        stance_scores = []
        quotes = []
        all_texts: List[str] = []
        total_views = 0
        all_comments: List[Dict[str, Any]] = []
        for v in videos:
            title = v.get("title", "")
            desc = v.get("content", "") or ""
            views = int(v.get("views", 0) or 0)
            total_views += views
            comments = v.get("comments_list") or v.get("top_comments") or []
            if not isinstance(comments, list):
                comments = []
            all_comments += comments
            text_all = title + " " + desc + " " + " ".join(c.get("content", "") for c in comments[:20])
            all_texts.append(text_all)
            s = sentiment(text_all)
            stance_scores.append(s["score"])
            top_cs = sorted(
                comments, key=lambda c: int(c.get("likes", 0) or 0), reverse=True
            )[:top_comments]
            for c in top_cs:
                ct = c.get("content", "")
                if not ct:
                    continue
                likes = int(c.get("likes", 0) or 0)
                if (
                    any(w in ct for w in FIN_TERMS + ["涨", "跌", "买", "卖", "赚", "亏", "股", "钱", "牛", "烂", "笑"])
                    or likes >= 20
                ):
                    quotes.append({"text": ct[:120], "likes": likes, "video": title[:40]})
            analyzed.append({
                "title": title[:100],
                "url": v.get("url", ""),
                "views": views,
                "comments": int(v.get("comments_count", 0) or v.get("extra", {}).get("stat", {}).get("reply", 0) or len(comments)),
                "pubdate": v.get("time", ""),
                "stance": s["label"],
                "score": s["score"],
                "keywords": [x["text"] for x in extract_keywords(comments + [v], top_k=5)[:5]],
                "top_comments": [
                    {"content": c.get("content", "")[:150], "likes": c.get("likes", 0), "author": c.get("author", "")}
                    for c in top_cs[:5]
                ],
            })
        for d in sorted(dynamics, key=lambda x: int(x.get("ts", 0) or 0), reverse=True)[:12]:
            text = d.get("title", "") + " " + d.get("content", "")
            all_texts.append(text)
            s = sentiment(text)
            stance_scores.append(s["score"] * 0.7)  # 动态权重略低于视频
            dyn_analyzed.append({
                "title": d.get("title", "")[:80],
                "content": d.get("content", "")[:180],
                "url": d.get("url", ""),
                "time": d.get("time", ""),
                "likes": d.get("likes", 0),
                "comments": d.get("comments", 0),
                "stance": s["label"],
                "score": s["score"],
                "extra": d.get("extra"),
            })
        overall = round(sum(stance_scores) / len(stance_scores), 3) if stance_scores else 0.0
        label = "看多" if overall >= 0.15 else ("看空" if overall <= -0.15 else "中性")
        comment_analysis = _comment_analysis(all_comments)
        kw = extract_keywords(
            [{"title": "", "content": t} for t in all_texts],
            top_k=10,
            protected=FIN_TERMS,
        )
        out.append({
            "name": name,
            "mid": up.get("mid", ""),
            "uid": up.get("uid", up.get("mid", "")),
            "url": up.get("url", ""),
            "charging": up.get("charging"),
            "cookie_configured": bool(up.get("cookie") or up.get("cookie_configured")),
            "avatar": up.get("avatar", ""),
            "avatar_local": up.get("avatar_local", ""),
            "avatar_remote": up.get("avatar_remote", ""),
            "sign": up.get("sign", ""),
            "fans": up.get("fans", 0),
            "tags": up.get("tags", []),
            "notes": up.get("notes", ""),
            "enabled": up.get("enabled", True),
            "stance": label,
            "stance_score": overall,
            "total_views": total_views,
            "total_dynamics": len(dyn_analyzed),
            "dynamics_ok": bool(up.get("dynamics_ok", True)),
            "dynamics_error": up.get("dynamics_error", ""),
            "charge_dyn_count": int(up.get("charge_dyn_count", 0) or 0),
            "videos": analyzed,
            "dynamics": dyn_analyzed,
            "comment_analysis": comment_analysis,
            "quotes": quotes[:6],
            "style_keywords": [x["text"] for x in kw[:8]],
        })
    return out


def _comment_analysis(comments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """评论汇总：情绪分布、热点词、活跃评论用户及其态度。"""
    empty = {
        "n": 0,
        "sentiment": {"label": "中性", "score": 0.0, "pos": 0, "neutral": 0, "neg": 0},
        "keywords": [],
        "top_commenters": [],
    }
    if not comments:
        return empty
    scores: List[float] = []
    labels: Counter = Counter()
    for c in comments:
        s = sentiment((c.get("content") or "") or (c.get("title") or ""))
        scores.append(s["score"])
        labels[s["label"]] += 1
    n = len(scores)
    avg = round(sum(scores) / n, 3) if n else 0.0
    label = "看多" if avg >= 0.15 else ("看空" if avg <= -0.15 else "中性")
    kws = extract_keywords(comments, top_k=8, protected=FIN_TERMS)
    by_user: Dict[str, Dict[str, Any]] = {}
    for c in comments:
        a = str(c.get("author", "") or "").strip() or "匿名"
        likes = int(c.get("likes", 0) or 0)
        e = by_user.setdefault(a, {"author": a, "n": 0, "likes": 0, "top": None, "stance": 0.0})
        e["n"] += 1
        e["likes"] += likes
        if e["top"] is None or likes > int((e["top"] or {}).get("likes", 0) or 0):
            e["top"] = {"content": (c.get("content") or "")[:120], "likes": likes}
        e["stance"] += sentiment(c.get("content") or "")["score"]
    top_users = []
    for a, e in by_user.items():
        if not e.get("top"):
            continue
        e["stance"] = round(e["stance"] / e["n"], 3) if e["n"] else 0.0
        e["stance_label"] = "看多" if e["stance"] >= 0.15 else ("看空" if e["stance"] <= -0.15 else "中性")
        top_users.append(e)
    top_users.sort(key=lambda x: (x["n"] * 2 + x["likes"] * 0.1), reverse=True)
    return {
        "n": n,
        "sentiment": {
            "label": label,
            "score": avg,
            "pos": labels.get("看多", 0),
            "neutral": labels.get("中性", 0),
            "neg": labels.get("看空", 0),
        },
        "keywords": [x["text"] for x in kws[:8]],
        "top_commenters": [
            {
                "author": e["author"],
                "n": e["n"],
                "likes": e["likes"],
                "stance": e["stance_label"],
                "top_comment": (e.get("top") or {}).get("content", ""),
            }
            for e in top_users[:5]
        ],
    }


# ---------- 摘要 ----------

_SOURCE_LABELS = {
    "bilibili": "B站",
    "guba": "股吧",
    "xueqiu": "雪球",
    "ths": "同花顺",
    "sector": "板块",
    "jin10": "金十",
    "cls": "财联社",
}


def build_summary(data: Dict[str, Any]) -> str:
    senti = data.get("sentiment", {})
    memes = data.get("memes", [])[:3]
    topics = data.get("topics", [])[:3]
    lines: List[str] = []
    lines.append(f"今日市场整体情绪：{senti.get('label', '中性')}（情绪指数 {senti.get('score', 0):+.2f}，"
                 f"看多 {senti.get('pos_posts', 0)} / 中性 {senti.get('neutral_posts', 0)} / "
                 f"看空 {senti.get('neg_posts', 0)}）。")
    if topics:
        lines.append("热点主题：" + "；".join(
            f"{t['label']}（{t['count']}条，{t['sentiment']}）" for t in topics
        ) + "。")
    if memes:
        lines.append("高频热词/梗：" + "、".join(
            f"{m['text']}（{m['freq']}次）" for m in memes
        ) + "。")
    upmasters = data.get("upmasters", [])
    if upmasters:
        lines.append("up主动态：" + "；".join(
            f"{u['name']} 观点{u['stance']}（{u['stance_score']:+.2f}）" for u in upmasters
        ) + "。")
    return "".join(lines)


# ---------- 主入口 ----------

def _keep_for_date(p: Dict[str, Any], date_str: str) -> bool:
    """只保留日报统计日期内的内容；无时间的帖子视为当日采集内容。"""
    if not date_str:
        return True
    t = str(p.get("time") or "").strip()
    if not t:
        return True
    if date_str in t:
        return True
    md = date_str[5:]
    if md and md in t:
        return True
    return False


def _filter_window(
    posts: List[Dict[str, Any]],
    date_str: str = "",
    since_ts: Optional[int] = None,
    until_ts: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """窗口过滤：有时间戳的严格按 [since_ts, until_ts] 截断（杜绝历史混入）；
    无时间戳的帖子按“当日采集”语义放行（日期字符串命中当天或仅有 HH:MM 等）。"""
    if not since_ts and not date_str:
        return posts
    out = []
    for p in posts:
        ts = int(p.get("ts", 0) or 0)
        if ts:
            if since_ts and ts < since_ts:
                continue
            if until_ts and ts > until_ts:
                continue
            out.append(p)
            continue
        t = str(p.get("time") or "").strip()
        if not t:
            out.append(p)
            continue
        if date_str and (date_str in t or date_str[5:] in t):
            out.append(p)
            continue
        if "-" not in t:
            # 仅有 HH:MM / HH:MM:SS 之类的时间，视为当日采集内容
            out.append(p)
            continue
    return out


def distill_day(
    posts: List[Dict[str, Any]],
    upmasters: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    date_str: str = "",
    since_ts: Optional[int] = None,
    until_ts: Optional[int] = None,
) -> Dict[str, Any]:
    if date_str or since_ts:
        before = len(posts)
        posts = _filter_window(posts, date_str, since_ts, until_ts)
        log.info("按统计窗口过滤内容：%d -> %d 条（since=%s）", before, len(posts), since_ts)
    posts = _dedupe(posts)
    d = cfg.get("distill", {})
    watchlist = cfg.get("watchlist", [])
    prot_names = [str(s.get("name", "")) for s in watchlist if s.get("name")]
    prot = prot_names + [str(s.get("code", "")) for s in watchlist if s.get("code")]
    log.info("蒸馏开始：%d 条内容", len(posts))
    source_counts = Counter(p.get("source", "?") for p in posts)
    keywords = extract_keywords(posts, d.get("top_keywords", 24), protected=prot_names)
    meme_sources = {"xueqiu", "ths", "jin10", "cls", "em"}
    meme_posts = [p for p in posts if p.get("source") in meme_sources]
    memes = detect_memes(meme_posts, d.get("top_memes", 16), d.get("min_meme_freq", 2), protected=prot_names)
    sentiment_all = aggregate_sentiment(posts)
    excluded = [a for a in (cfg.get("distill", {}) or {}).get("exclude_authors_from_topics", []) or [] if a]
    topics = cluster_topics(posts, watchlist, top_k=8, excluded_authors=excluded)
    up_analysis = analyze_upmasters(upmasters, d.get("top_comments_per_video", 8))
    data = {
        "keywords": keywords,
        "memes": memes,
        "sentiment": sentiment_all,
        "topics": topics,
        "upmasters": up_analysis,
        "source_counts": dict(source_counts),
    }
    data["summary"] = build_summary(data)
    return data


def _dedupe(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for p in posts:
        key = p.get("url") or f"{p.get('source')}|{p.get('title')}|{(p.get('content') or '')[:40]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
