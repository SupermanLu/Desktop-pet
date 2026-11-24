# -*- coding: utf-8 -*-
"""网易云歌词：歌曲搜索 / 歌词拉取 / LRC 解析 / 本地缓存。

纯函数模块（不依赖 Qt），网络模式沿用 core/weather.py 惯例：
urllib + timeout=5 + 异常返回 None，绝不抛穿到调用方。

接口（公开网页接口，2026-11 实测可用，需 Referer 头）：
- 搜索: /api/search/get/web?s=<关键词>&type=1&limit=5
- 歌词: /api/song/lyric?id=<song_id>&lv=-1&kv=-1&tv=-1
  返回 lrc.lyric（时间轴原文）与 tlyric.lyric（翻译）。

缓存（避免切歌重复请求与接口限频）：
- lyric_cache/<song_id>.json      歌词本体
- lyric_cache/_index.json        "歌名|歌手" → song_id 映射
"""
import json
import os
import re
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

from core.config import PROJECT_DIR

CACHE_DIR = os.path.join(PROJECT_DIR, "lyric_cache")
_INDEX_PATH = os.path.join(CACHE_DIR, "_index.json")
_TIMEOUT = 5
_HEADERS = {
    "Referer": "http://music.163.com",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
}


def _http_get_json(url: str):
    """GET 请求并解析 JSON；任何异常返回 None（照 weather.py 惯例）。"""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _norm(s: str) -> str:
    """归一化歌名/歌手：小写、去空白与常见后缀括号，提升匹配率。"""
    s = (s or "").lower().strip()
    s = re.sub(r"[（(][^（()）]*[)）]", "", s)   # 去 (Live)、(原唱 xxx) 等
    s = re.sub(r"\s+", "", s)
    return s


def _match_score(title: str, artist: str, cand: dict) -> float:
    """候选歌曲与目标的匹配分（0~1.5）：歌名相似度为主，歌手必须对得上。

    歌手对不上（翻唱/蹭名版本）直接 0 分——错版本歌词的时间轴和
    实际播放的歌对不齐，会出现"歌词速度不一致"。
    """
    ct = _norm(cand.get("name", ""))
    score = SequenceMatcher(None, _norm(title), ct).ratio()
    if score < 0.6:                 # 歌名都不像：淘汰
        return 0.0
    ta = _norm(artist)
    cand_artists = _norm(" ".join(a.get("name", "")
                                  for a in (cand.get("artists") or [])))
    if ta and cand_artists:
        # 按分隔符拆开逐个歌手比对，避免"田馥甄的小迷妹"蹭名包含
        parts = [x for x in re.split(r"[、,，/&;和+×x\s]", cand_artists) if x]
        if ta == cand_artists or ta in parts:
            score += 0.5            # 歌手完全命中
        else:
            sim = SequenceMatcher(None, ta, cand_artists).ratio()
            if sim < 0.34:
                return 0.0          # 歌手不是这个人：宁缺毋滥
            score += 0.3 * sim
    return score


def search_song(title: str, artist: str = "") -> dict | None:
    """按歌名(+歌手)搜索，返回最佳匹配 {id, name, artist} 或 None。"""
    kw = urllib.parse.quote(f"{title} {artist}".strip())
    data = _http_get_json(
        "https://music.163.com/api/search/get/web?csrf_token="
        f"&hlpretag=&hlposttag=&s={kw}&type=1&offset=0&total=true&limit=20")
    songs = ((data or {}).get("result") or {}).get("songs") or []
    best, best_score = None, 0.0
    for cand in songs:
        s = _match_score(title, artist, cand)
        if s > best_score:
            best, best_score = cand, s
    if best is None or best_score < 0.6:        # 匹配太差宁缺毋滥
        return None
    return {
        "id": best.get("id"),
        "name": best.get("name", ""),
        "artist": ", ".join(a.get("name", "")
                            for a in (best.get("artists") or [])),
    }


def fetch_lyric(song_id: int) -> tuple[str, str] | None:
    """拉取歌词，返回 (lrc, tlyric)；失败返回 None。两者都空也算失败。"""
    data = _http_get_json(
        f"https://music.163.com/api/song/lyric?id={song_id}"
        "&lv=-1&kv=-1&tv=-1")
    if not data or data.get("code") != 200:
        return None
    lrc = (data.get("lrc") or {}).get("lyric") or ""
    tlyric = (data.get("tlyric") or {}).get("lyric") or ""
    if not lrc.strip():
        return None
    return lrc, tlyric


# ---------- LRC 解析 ----------

_LRC_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(lrc: str, tlyric: str = "") -> list[dict]:
    """解析 LRC 为按时间排序的行列表 [{t, text, trans}]。

    - 一行多个时间标签 [01:00][02:00]xx 展开为多条
    - [offset:±ms] 整体平移（正=歌词提前）；offset 取自主歌词，
      同样作用于翻译时间轴（tlyric 通常不带 offset 标签，不平移会错位）
    - tlyric 按时间点合并进 trans
    - 空歌词行丢弃
    """
    def _find_offset(raw: str) -> int:
        m = re.search(r"\[offset:([+-]?\d+)\]", raw or "")
        return -int(m.group(1)) if m else 0   # LRC 规范：正 offset 歌词提前出现

    offset = _find_offset(lrc) or _find_offset(tlyric)

    def _parse(raw: str) -> list[tuple[int, str]]:
        out = []
        for ln in (raw or "").splitlines():
            if re.match(r"\s*\[offset:", ln):
                continue
            times = []
            rest = ln
            while True:
                m = _LRC_RE.match(rest)
                if not m:
                    break
                ms = (int(m.group(1)) * 60 + float(m.group(2))) * 1000
                times.append(int(ms))
                rest = m.group(3)
            text = rest.strip()
            for t in times:
                out.append((t + offset, text))
        out.sort(key=lambda x: x[0])
        return out

    base = _parse(lrc)
    trans_map = {}
    for t, text in _parse(tlyric):
        if text:
            trans_map[t] = text
    lines = [{"t": t, "text": text,
              "trans": trans_map.get(t, "")} for t, text in base]
    return lines


# ---------- 缓存 ----------

def _index_load() -> dict:
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _index_save(idx: dict):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False)
    except Exception:
        pass


def cache_get(title: str, artist: str) -> list[dict] | None:
    """查缓存：歌名|歌手 → song_id → 已存歌词行。未命中返回 None。"""
    idx = _index_load()
    sid = idx.get(f"{title}|{artist}")
    if not sid:
        return None
    try:
        with open(os.path.join(CACHE_DIR, f"{sid}.json"),
                  "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lines")
    except Exception:
        return None


def cache_put(title: str, artist: str, song_id: int, lines: list[dict]):
    """写缓存：歌词本体 + 映射。静默失败（缓存只是优化，不该影响功能）。"""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(os.path.join(CACHE_DIR, f"{song_id}.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"title": title, "artist": artist, "lines": lines},
                      f, ensure_ascii=False)
        idx = _index_load()
        idx[f"{title}|{artist}"] = song_id
        _index_save(idx)
    except Exception:
        pass


def get_lyrics(title: str, artist: str = "") -> list[dict] | None:
    """一站式：缓存优先，否则 搜索→拉词→解析→存缓存。失败返回 None。"""
    lines = cache_get(title, artist)
    if lines:
        return lines
    song = search_song(title, artist)
    if not song:
        return None
    fetched = fetch_lyric(song["id"])
    if not fetched:
        return None
    lrc, tlyric = fetched
    lines = parse_lrc(lrc, tlyric)
    if not lines:
        return None
    cache_put(title, artist, song["id"], lines)
    return lines
