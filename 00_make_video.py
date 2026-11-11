# ===== CODE BEGIN v3.5-auto =====
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 wataru_fujita
import os, sys, json, math, time, glob, shutil, subprocess, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

TEMPLATE_VERSION = "v3.5-auto"

# ---------- 0. 設定の検証(設定は、信頼できない入力として扱う。許可したものだけを通し、違反したら実行せずに STOP) ----------
# 環境変数 MKV_CONFIG と、設定ブロックの値の両方を検証する。ファイル名・FPS・長さ・文字数・キーは、ここで固定する。
# 手順書の規則(プロンプト)だけに頼らず、コードで強制するための部分。v3.4 で追加。
import re
def _stop(msg):
    print("STOP: 設定が、許可された範囲にありません: " + msg); sys.exit(1)
def _le(a, b): return max(a - b, 0) == 0
def _is_int(x): return isinstance(x, int) and not isinstance(x, bool)
def _is_num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)
def _is_text(x, n): return isinstance(x, str) and _le(len(x), n) and not any(ord(c) in range(0, 32) or ord(c) == 127 for c in x)
_TOP_KEYS = {"SCENES", "APP_NAME", "OUT_NAME", "FPS", "ILLUST_MIN"}
_SCENE_KEYS = {"type", "chip", "title", "illust", "sub", "caption", "sec", "cards", "items", "icons", "focus", "button", "toast"}
_CARD_KEYS = {"head", "body", "icon"}
def _check_scenes(scenes):
    if not (isinstance(scenes, list) and len(scenes) in range(1, 21)): _stop("SCENES は 1〜20 場面のリスト")
    total = 0
    for i, s in enumerate(scenes):
        w = "場面" + str(i + 1) + ": "
        if not (isinstance(s, dict) and all(isinstance(k, str) for k in s) and set(s).issubset(_SCENE_KEYS)): _stop(w + "許可されていないキーがあります")
        if s.get("type") not in ("hero", "cards", "list", "cta"): _stop(w + "type は hero / cards / list / cta のいずれか")
        sec = s.get("sec")
        if not (_is_int(sec) and _le(1, sec) and _le(sec, 60)): _stop(w + "sec は 1〜60 の整数")
        total = total + sec
        for k in ("chip", "title", "illust", "sub", "caption", "button", "toast"):
            if k in s and not _is_text(s[k], 120): _stop(w + k + " は 120 文字以内の文字列")
        if "focus" in s and not (_is_int(s["focus"]) and s["focus"] in range(0, 10)): _stop(w + "focus は 0〜9 の整数")
        if "cards" in s:
            cs = s["cards"]
            if not (isinstance(cs, list) and len(cs) in range(0, 7)): _stop(w + "cards は 6 件まで")
            for c in cs:
                if not (isinstance(c, dict) and set(c).issubset(_CARD_KEYS) and all(_is_text(v, 200) for v in c.values())): _stop(w + "cards の中身が、許可された形ではありません")
        if "items" in s and not (isinstance(s["items"], list) and len(s["items"]) in range(0, 9) and all(_is_text(v, 120) for v in s["items"])): _stop(w + "items は 8 件まで・各 120 文字以内")
        if "icons" in s and not (isinstance(s["icons"], list) and len(s["icons"]) in range(0, 9) and all(_is_text(v, 40) for v in s["icons"])): _stop(w + "icons は 8 件まで・各 40 文字以内")
        if not ("title" in s and "caption" in s): _stop(w + "title と caption が必要です")
        if s["type"] == "cards" and not (isinstance(s.get("cards"), list) and len(s["cards"]) in range(1, 7) and all("head" in c and "body" in c for c in s["cards"])): _stop(w + "cards は 1〜6 件で、各カードに head と body が必要です")
        if s["type"] == "list" and not (isinstance(s.get("items"), list) and len(s["items"]) in range(1, 9)): _stop(w + "items は 1〜8 件が必要です")
        if "focus" in s and s["type"] in ("cards", "list") and s["focus"] not in range(len(s["cards"] if s["type"] == "cards" else s["items"])): _stop(w + "focus は、カード・項目の数の範囲内の番号(0 始まり)")
    if not _le(total, 180): _stop("場面の秒数の合計は 180 秒まで(実行時間の上限のため)")
def _check_settings():
    if not (isinstance(OUT_NAME, str) and re.fullmatch(r"(?!-)[\w\-]{1,60}\.mp4", OUT_NAME)): _stop("OUT_NAME は、文字・数字・- ・_ の 60 文字以内 + .mp4 だけ(フォルダの指定や、途中の . は不可)")
    if not (_is_int(FPS) and FPS in (15, 24)): _stop("FPS は 15 または 24")
    if not (_is_int(ILLUST_MIN) and ILLUST_MIN in range(0, 11)): _stop("ILLUST_MIN は 0〜10 の整数")
    if not _is_text(APP_NAME, 40): _stop("APP_NAME は 40 文字以内の文字列")
    _check_scenes(SCENES)

# ===== 設定(ここだけ書き換える) =====
OUT_NAME = "video.mp4"
W, H, FPS = 1280, 720, 24
APP_NAME = "セキュリティ通信"
BPM = 96
ILLUST_MIN = 3                                        # イラストの最低数。利用者がイラスト不要と言ったときだけ 0 にする
SCENES = [
    {"type": "hero", "chip": "社内向け 啓発", "title": "パスワードを守ろう", "illust": "shield",
     "sub": "今日からできる3つの習慣", "caption": "まずは、パスワードの守り方から始めましょう。", "sec": 7},
    {"type": "cards", "title": "3つの基本ルール",
     "cards": [{"head": "長くする", "body": "12文字以上の文章にする", "icon": "key"},
               {"head": "使い回さない", "body": "サービスごとに別のものにする", "icon": "lock"},
               {"head": "多要素認証", "body": "確認コードを必ず併用する", "icon": "phone"}],
     "focus": 2, "caption": "特に多要素認証は、乗っ取りを大きく減らします。", "sec": 11},
    {"type": "list", "title": "今日やること",
     "items": ["パスワード管理ツールを開く", "使い回しを1つ見つける", "多要素認証を1つ有効にする"],
     "icons": ["laptop", "magnifier", "shield"],
     "focus": 2, "caption": "できることから1つずつ、確認していきましょう。", "sec": 10},
    {"type": "cta", "title": "困ったら相談を", "sub": "情報システム部が対応します", "illust": "chat",
     "button": "相談する", "toast": "相談を受け付けました",
     "caption": "迷ったら、ひとりで抱えずに相談してください。", "sec": 9},
]
# ===== 設定ここまで =====
if os.environ.get("MKV_CONFIG"):                      # .py を添付して使う場合: 設定は環境変数(JSON)で渡す(コード本体は書き換えない)
    _raw = os.environ["MKV_CONFIG"]
    if not _le(len(_raw), 20000): _stop("MKV_CONFIG が大きすぎます(20000 文字まで)")
    try:
        _cfg = json.loads(_raw)
    except ValueError:
        _stop("MKV_CONFIG が JSON として読めません")
    if not (isinstance(_cfg, dict) and set(_cfg).issubset(_TOP_KEYS)): _stop("MKV_CONFIG に、許可されていないキーがあります")
    SCENES = _cfg.get("SCENES", SCENES); APP_NAME = _cfg.get("APP_NAME", APP_NAME)
    OUT_NAME = _cfg.get("OUT_NAME", OUT_NAME); FPS = _cfg.get("FPS", FPS); ILLUST_MIN = _cfg.get("ILLUST_MIN", ILLUST_MIN)
    if isinstance(FPS, str) and FPS.isdigit(): FPS = int(FPS)                  # 数字だけの文字列("24")は受け付ける
    if isinstance(ILLUST_MIN, str) and ILLUST_MIN.isdigit(): ILLUST_MIN = int(ILLUST_MIN)
    print("設定: 環境変数 MKV_CONFIG から読み込み(場面数 " + str(len(SCENES) if isinstance(SCENES, list) else 0) + ")")
_check_settings()

DEMO = os.environ.get("MKV_DEMO") == "1"          # 見本の動画を作るときだけ 1 にする
SAMPLE_MARKERS = ["パスワードを守ろう", "今日からできる3つの習慣", "特に多要素認証は、乗っ取りを大きく減らします。", "セキュリティ通信", "【要入力】"]
def all_strings(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [t for v in x.values() for t in all_strings(v)]
    if isinstance(x, (list, tuple)):
        return [t for v in x for t in all_strings(v)]
    return []
BG_TOP, BG_BOT = (15, 23, 42), (30, 41, 59)
CARD, CARD2, BORDER = (30, 41, 59), (39, 52, 76), (71, 85, 105)
TEXT, MUTED = (241, 245, 249), (148, 163, 184)
ACC, ACC2, GREEN = (45, 212, 191), (129, 140, 248), (74, 222, 128)
SAFE, APP_H, CAP_H = 64, 64, 104
CONTENT_TOP, CONTENT_BOT = APP_H + 28, H - CAP_H - 14
CAP_Y = H - CAP_H
TR = 0.45

def LE(a, b):
    return max(a - b, 0) == 0

def clamp01(x):
    return min(max(x, 0.0), 1.0)

def ease_out(x):
    x = clamp01(x); return 1 - (1 - x) ** 3

def ease_io(x):
    x = clamp01(x); return x * x * (3 - 2 * x)

def ease_back(x):
    x = clamp01(x); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def prog(t, t0, d):
    return clamp01((t - t0) / d)

WORK = tempfile.mkdtemp(prefix="mkvideo_")
LOG = []
LAYOUT_ERRORS = []
EVENTS = []
def log(m):
    LOG.append(m); print(m)

# ---------- 1. ffmpeg・フォント(インストールは試みない) ----------
FF = shutil.which("ffmpeg")
FP = shutil.which("ffprobe")
if FF is None:
    try:
        import imageio_ffmpeg
        FF = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        FF = None
if FF is None:
    print("STOP: ffmpeg が見つかりません。手順書の代替手順(B)へ進んでください。"); sys.exit(1)

FONT_PATH, BOLD_PATH = None, None
for pat in ["/usr/share/fonts/**/NotoSansCJK*", "/usr/share/fonts/**/*CJK*", "/usr/share/fonts/**/*ipa*",
            "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc"]:
    hits = sorted(glob.glob(pat, recursive=True))
    if hits:
        FONT_PATH = hits[0]; break
for pat in ["/usr/share/fonts/**/NotoSansCJK*Bold*", "C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc"]:
    hits = sorted(glob.glob(pat, recursive=True))
    if hits:
        BOLD_PATH = hits[0]; break
if FONT_PATH is None:
    print("STOP: 日本語フォントが見つかりません。手順書の代替手順(B)へ進んでください。"); sys.exit(1)
_fc = {}
def font(size, bold=False):
    key = (size, bold)
    if key in _fc:
        return _fc[key]
    f = ImageFont.truetype(BOLD_PATH if (bold and BOLD_PATH) else FONT_PATH, size)
    if bold and not BOLD_PATH:
        try:
            f.set_variation_by_axes([700])
        except Exception:
            pass
    _fc[key] = f
    return f

# ---------- 2. 描画の部品 ----------
def wrap(text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        if LE(fnt.getlength(cur + ch), max_w):
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines

def put_text(d, x, y, text, size, color, max_w, bold=False, line=1.4):
    fnt = font(size, bold)
    lines = wrap(text, fnt, max_w)
    for i, l in enumerate(lines):
        d.text((x, y + i * int(size * line)), l, font=fnt, fill=color + (255,))
    return y + len(lines) * int(size * line)

_dummy = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
def text_h(text, size, max_w, bold=False, line=1.4):
    return len(wrap(text, font(size, bold), max_w)) * int(size * line)

def L(im):
    a = np.asarray(im.convert("RGBA"))
    return {"im": im, "rgb": a[..., :3].astype(np.float32), "a": a[..., 3].astype(np.float32) / 255.0,
            "w": im.size[0], "h": im.size[1]}

def text_layer(text, size, color, max_w, bold=False, line=1.4):
    fnt = font(size, bold)
    lines = wrap(text, fnt, max_w)
    wmax = max(int(fnt.getlength(l)) for l in lines) + 8
    hh = len(lines) * int(size * line) + 8
    im = Image.new("RGBA", (wmax, hh), (0, 0, 0, 0))
    put_text(ImageDraw.Draw(im), 4, 2, text, size, color, max_w, bold, line)
    return L(im)

def put(f, lay, x, y, scale=1.0, op=1.0):
    if LE(op, 0.003):
        return
    if LE(0.003, abs(scale - 1.0)):
        w, h = max(1, int(lay["w"] * scale)), max(1, int(lay["h"] * scale))
        a = np.asarray(lay["im"].resize((w, h), Image.BILINEAR))
        rgb, al = a[..., :3].astype(np.float32), a[..., 3].astype(np.float32) / 255.0
        x = int(x + (lay["w"] - w) / 2); y = int(y + (lay["h"] - h) / 2)
    else:
        rgb, al, w, h = lay["rgb"], lay["a"], lay["w"], lay["h"]
        x, y = int(x), int(y)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if not LE(x0 + 1, x1) or not LE(y0 + 1, y1):
        return
    m = al[y0 - y:y1 - y, x0 - x:x1 - x, None] * min(op, 1.0)
    reg = f[y0:y1, x0:x1].astype(np.float32)
    f[y0:y1, x0:x1] = (reg * (1 - m) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * m).astype(np.uint8)

def aa_shape(size, fn, k=4):
    big_ = Image.new("RGBA", (size[0] * k, size[1] * k), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big_), k)
    return big_.resize(size, Image.LANCZOS)

def card_img(w, h, r=24, fill=CARD, border=BORDER, bw=2, pad=36, glow=None):
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 12, pad + w, pad + h + 12), r, fill=(0, 0, 0, 160))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(16)))
    if glow:
        gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(gl).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=glow + (150,))
        im = Image.alpha_composite(im, gl.filter(ImageFilter.GaussianBlur(14)))
    shp = aa_shape((w, h), lambda dd, k: dd.rounded_rectangle((0, 0, w * k - 1, h * k - 1), r * k, fill=fill + (255,), outline=border + (255,), width=bw * k))
    im.alpha_composite(shp, (pad, pad))
    return im

# ---------- 2b. イラスト部品(画像ファイルなし。コードで描くベクター風アイコン) ----------
AMB, ROSE, PALE, STEEL = (251, 191, 36), (251, 113, 133), (226, 232, 240), (148, 163, 184)
ILL_STATS = []
ILL_COUNT = [0]
def _dk(c, f=0.78):
    return tuple(int(v * f) for v in c)
def _bez(p0, p1, p2, n=16):
    return [((1 - j / n) ** 2 * p0[0] + 2 * (1 - j / n) * (j / n) * p1[0] + (j / n) ** 2 * p2[0],
             (1 - j / n) ** 2 * p0[1] + 2 * (1 - j / n) * (j / n) * p1[1] + (j / n) ** 2 * p2[1]) for j in range(n + 1)]
def _rr(dd, u, b, r, fill, outline=None, w=0):
    dd.rounded_rectangle([b[0] * u, b[1] * u, b[2] * u, b[3] * u], r * u, fill=(fill + (255,)) if fill else None,
                         outline=(outline + (255,)) if outline else None, width=int(w * u))
def _el(dd, u, cx, cy, r, fill, outline=None, w=0):
    dd.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=(fill + (255,)) if fill else None,
               outline=(outline + (255,)) if outline else None, width=int(w * u))
def _pg(dd, u, pts, fill):
    dd.polygon([(x * u, y * u) for x, y in pts], fill=fill + (255,))
def _ln(dd, u, pts, fill, w):
    dd.line([(x * u, y * u) for x, y in pts], fill=fill + (255,), width=int(w * u), joint="curve")
    for x, y in (pts[0], pts[-1]):
        _el(dd, u, x, y, w / 2.0, fill)

def _i_shield(dd, u):
    right = _bez((87, 47), (84, 78), (50, 96))
    left = [(100 - x, y) for x, y in reversed(right)]
    _pg(dd, u, [(50, 6), (87, 19)] + right + left + [(13, 19)], ACC)
    _pg(dd, u, [(50, 6), (87, 19)] + right, _dk(ACC))
    _ln(dd, u, [(33, 50), (46, 63), (69, 37)], TEXT, 8)
def _i_lock(dd, u):
    _rr(dd, u, (31, 12, 69, 62), 19, None, PALE, 9)
    _rr(dd, u, (18, 44, 82, 93), 11, ACC)
    _el(dd, u, 50, 64, 7, BG_TOP)
    _rr(dd, u, (46.5, 66, 53.5, 80), 2, BG_TOP)
def _i_key(dd, u):
    _el(dd, u, 30, 50, 19, None, AMB, 9)
    _ln(dd, u, [(48, 50), (89, 50)], AMB, 8)
    _ln(dd, u, [(75, 50), (75, 64)], AMB, 7)
    _ln(dd, u, [(85, 50), (85, 60)], AMB, 7)
def _i_mail(dd, u):
    _rr(dd, u, (8, 22, 92, 78), 9, PALE)
    _ln(dd, u, [(12, 28), (50, 56), (88, 28)], ACC2, 5)
    _el(dd, u, 84, 24, 11, ROSE)
def _i_person(dd, u):
    _el(dd, u, 50, 32, 17, ACC)
    dd.pieslice([20 * u, 56 * u, 80 * u, 116 * u], 180, 360, fill=ACC2 + (255,))
def _i_people(dd, u):
    dd.pieslice([50 * u, 54 * u, 92 * u, 108 * u], 180, 360, fill=ACC2 + (255,))
    _el(dd, u, 70, 38, 12, ACC2)
    dd.pieslice([8 * u, 52 * u, 62 * u, 112 * u], 180, 360, fill=ACC + (255,))
    _el(dd, u, 35, 32, 14, ACC)
def _i_cloud(dd, u):
    _el(dd, u, 30, 58, 16, PALE); _el(dd, u, 50, 44, 22, PALE); _el(dd, u, 72, 58, 15, PALE)
    _rr(dd, u, (22, 58, 86, 78), 10, PALE)
    _ln(dd, u, [(50, 74), (50, 52)], ACC, 7)
    _ln(dd, u, [(40, 61), (50, 51), (60, 61)], ACC, 7)
def _i_chart(dd, u):
    _rr(dd, u, (6, 6, 94, 94), 12, CARD2, BORDER, 2)
    _rr(dd, u, (18, 54, 34, 82), 3, ACC2); _rr(dd, u, (42, 34, 58, 82), 3, ACC); _rr(dd, u, (66, 18, 82, 82), 3, GREEN)
    _ln(dd, u, [(14, 85), (86, 85)], STEEL, 3)
def _i_warning(dd, u):
    tri = [(50, 11), (92, 84), (8, 84)]
    _pg(dd, u, tri, AMB)
    _ln(dd, u, tri + [tri[0]], AMB, 8)
    _rr(dd, u, (46, 36, 54, 60), 3, BG_TOP)
    _el(dd, u, 50, 71, 5, BG_TOP)
def _i_bulb(dd, u):
    _el(dd, u, 50, 40, 28, AMB)
    _pg(dd, u, [(36, 60), (64, 60), (60, 72), (40, 72)], AMB)
    _el(dd, u, 40, 30, 7, (255, 236, 170))
    _rr(dd, u, (38, 72, 62, 78), 3, STEEL); _rr(dd, u, (41, 80, 59, 86), 3, STEEL); _rr(dd, u, (45, 88, 55, 93), 2, STEEL)
    _ln(dd, u, [(43, 44), (50, 53), (57, 44)], BG_TOP, 3)
def _i_clock(dd, u):
    _el(dd, u, 50, 50, 40, PALE, ACC2, 8)
    _ln(dd, u, [(50, 50), (50, 26)], BG_TOP, 6)
    _ln(dd, u, [(50, 50), (67, 60)], BG_TOP, 6)
    _el(dd, u, 50, 50, 5, ACC)
def _i_laptop(dd, u):
    _rr(dd, u, (14, 16, 86, 66), 7, PALE)
    _rr(dd, u, (20, 22, 80, 60), 3, BG_TOP)
    _ln(dd, u, [(27, 34), (55, 34)], ACC, 4); _ln(dd, u, [(27, 43), (68, 43)], ACC2, 4); _ln(dd, u, [(27, 52), (46, 52)], GREEN, 4)
    _pg(dd, u, [(4, 72), (96, 72), (88, 83), (12, 83)], STEEL)
def _i_phone(dd, u):
    _rr(dd, u, (30, 6, 70, 94), 9, PALE)
    _rr(dd, u, (34, 14, 66, 80), 3, BG_TOP)
    _rr(dd, u, (38, 20, 62, 34), 4, ACC)
    _ln(dd, u, [(39, 44), (61, 44)], STEEL, 3); _ln(dd, u, [(39, 53), (55, 53)], STEEL, 3)
    _el(dd, u, 50, 87, 3.2, STEEL)
def _i_magnifier(dd, u):
    _el(dd, u, 42, 42, 27, (24, 70, 80), ACC, 10)
    _ln(dd, u, [(63, 63), (87, 87)], PALE, 12)
def _i_chat(dd, u):
    _rr(dd, u, (8, 14, 92, 68), 14, ACC2)
    _pg(dd, u, [(22, 64), (22, 90), (48, 64)], ACC2)
    _el(dd, u, 30, 41, 5.5, TEXT); _el(dd, u, 50, 41, 5.5, TEXT); _el(dd, u, 70, 41, 5.5, TEXT)
def _i_gear(dd, u):
    for a_ in range(8):
        an = a_ * math.pi / 4.0; rc, rs = math.cos(an), math.sin(an)
        cx_, cy_ = 50 + 34 * rc, 50 + 34 * rs
        pts = [(cx_ + sr * 7 * rc - st * 8 * rs, cy_ + sr * 7 * rs + st * 8 * rc) for sr, st in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        _pg(dd, u, pts, STEEL)
    _el(dd, u, 50, 50, 31, STEEL); _el(dd, u, 50, 50, 13, BG_TOP); _el(dd, u, 50, 50, 6, ACC)
def _i_target(dd, u):
    _el(dd, u, 50, 50, 40, ROSE); _el(dd, u, 50, 50, 30, PALE); _el(dd, u, 50, 50, 20, ROSE); _el(dd, u, 50, 50, 10, PALE)
    _ln(dd, u, [(50, 50), (84, 16)], AMB, 5)
    _ln(dd, u, [(84, 16), (92, 16)], AMB, 5); _ln(dd, u, [(84, 16), (84, 8)], AMB, 5)
def _i_book(dd, u):
    _pg(dd, u, [(8, 22), (47, 30), (47, 88), (8, 80)], ACC2)
    _pg(dd, u, [(92, 22), (53, 30), (53, 88), (92, 80)], PALE)
    _pg(dd, u, [(47, 30), (53, 30), (53, 88), (47, 88)], _dk(ACC2))
    _ln(dd, u, [(60, 44), (84, 40)], STEEL, 3); _ln(dd, u, [(60, 56), (84, 52)], STEEL, 3); _ln(dd, u, [(60, 68), (78, 65)], STEEL, 3)
def _i_bell(dd, u):
    _el(dd, u, 50, 10, 5, AMB)
    _el(dd, u, 50, 38, 26, AMB)
    _pg(dd, u, [(24, 38), (76, 38), (86, 74), (14, 74)], AMB)
    _rr(dd, u, (12, 72, 88, 80), 4, _dk(AMB))
    _el(dd, u, 50, 86, 7, _dk(AMB))
def _i_check(dd, u):
    _el(dd, u, 50, 50, 42, GREEN)
    _ln(dd, u, [(30, 52), (44, 66), (70, 36)], BG_TOP, 9)
def _i_star(dd, u):
    pts = []
    for j in range(10):
        rr_ = 44 if j % 2 == 0 else 19
        an = -math.pi / 2 + j * math.pi / 5
        pts.append((50 + rr_ * math.cos(an), 54 + rr_ * math.sin(an)))
    _pg(dd, u, pts, AMB)
def _i_heart(dd, u):
    _el(dd, u, 33, 36, 19, ROSE); _el(dd, u, 67, 36, 19, ROSE)
    _pg(dd, u, [(16, 44), (84, 44), (50, 90)], ROSE)

ICONS = {"shield": _i_shield, "lock": _i_lock, "key": _i_key, "mail": _i_mail, "person": _i_person, "people": _i_people,
         "cloud": _i_cloud, "chart": _i_chart, "warning": _i_warning, "bulb": _i_bulb, "clock": _i_clock, "laptop": _i_laptop,
         "phone": _i_phone, "magnifier": _i_magnifier, "chat": _i_chat, "gear": _i_gear, "target": _i_target, "book": _i_book,
         "bell": _i_bell, "check": _i_check, "star": _i_star, "heart": _i_heart}
_icache = {}
def icon_img(name, size):
    key = (name, size)
    if key in _icache:
        return _icache[key]
    nm = name
    if nm not in ICONS:
        LAYOUT_ERRORS.append("イラスト名が不明: " + str(name) + "(使える名前: " + ", ".join(sorted(ICONS)) + ")")
        nm = "star"
    im = aa_shape((size, size), lambda dd, k_: ICONS[nm](dd, size * k_ / 100.0))
    a_ = np.asarray(im)[..., 3]
    cover = float((a_.astype(np.float32) / 255.0).mean())
    edge = int(max(a_[0].max(), a_[-1].max(), a_[:, 0].max(), a_[:, -1].max()))
    ILL_STATS.append((nm, cover, edge))
    _icache[key] = im
    return im

def badge_pil(size, name, tint=ACC, pad=0, glow=False, ratio=0.62, ring=False):
    im = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    if glow:
        gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(gl).ellipse((pad - 6, pad - 6, pad + size + 6, pad + size + 6), fill=tint + (120,))
        im = Image.alpha_composite(im, gl.filter(ImageFilter.GaussianBlur(max(8, int(size * 0.09)))))
    if ring:
        rg = aa_shape(im.size, lambda dd, k_: dd.ellipse((8 * k_, 8 * k_, (im.size[0] - 8) * k_ - 1, (im.size[1] - 8) * k_ - 1), outline=tint + (90,), width=2 * k_))
        im.alpha_composite(rg)
    disc = aa_shape((size, size), lambda dd, k_: dd.ellipse((0, 0, size * k_ - 1, size * k_ - 1), fill=CARD2 + (255,), outline=tint + (255,), width=max(2, int(size * 0.025)) * k_))
    ic = icon_img(name, int(size * ratio))
    disc.alpha_composite(ic, (int((size - ic.size[0]) / 2), int((size - ic.size[1]) / 2)))
    im.alpha_composite(disc, (pad, pad))
    return im

def check_rect(name, x, y, w, h):
    if not (LE(SAFE, x) and LE(x + w, W - SAFE) and LE(CONTENT_TOP - 20, y) and LE(y + h, CONTENT_BOT)):
        LAYOUT_ERRORS.append(f"{name} はみ出し x={int(x)} y={int(y)} w={int(w)} h={int(h)}")

def need_sec(i, s, need):
    if not LE(need, s["sec"]):
        LAYOUT_ERRORS.append(f"場面{i+1}: 秒数不足(最低 {need:.1f} 秒が必要、設定 {s['sec']} 秒)")

# 背景(紺のグラデーションとゆっくり動く光のにじみ)
BGW, BGH = W + 160, H + 120
big = np.zeros((BGH, BGW, 3), np.float32)
for c in range(3):
    big[:, :, c] = np.linspace(BG_TOP[c], BG_BOT[c], BGH)[:, None]
blob = Image.new("RGBA", (BGW, BGH), (0, 0, 0, 0))
bd = ImageDraw.Draw(blob)
bd.ellipse((60, 40, 560, 540), fill=ACC + (60,))
bd.ellipse((BGW - 620, BGH - 520, BGW - 80, BGH - 20), fill=ACC2 + (60,))
blob = np.asarray(blob.filter(ImageFilter.GaussianBlur(110))).astype(np.float32)
al = blob[..., 3:4] / 255.0
BIG = big * (1 - al) + blob[..., :3] * al
BIG = np.clip(BIG + np.random.RandomState(7).normal(0, 1.1, BIG.shape[:2])[..., None], 0, 255).astype(np.uint8)   # 微細なノイズで色の段差(バンディング)を消す
def background(tabs):
    ox = int(80 + 30 * math.sin(tabs / 5.0)); oy = int(60 + 20 * math.cos(tabs / 6.5))
    return BIG[oy:oy + H, ox:ox + W].copy()

# ---------- 3. 場面の組み立て ----------
def push_cam(sec, z=0.05):
    return lambda t: (1.0 + z * ease_io(t / sec), 0.5, 0.5)

def build_hero(i, s, t0):
    need_sec(i, s, 3.5)
    chip = None
    if s.get("chip"):
        cl = text_layer(s["chip"], 24, ACC, 600, True)
        cwid = cl["w"] + 44
        im = aa_shape((cwid, 52), lambda dd, k_: dd.rounded_rectangle((0, 0, cwid * k_ - 1, 52 * k_ - 1), 26 * k_, fill=ACC + (45,), outline=ACC + (200,), width=2 * k_))
        im.alpha_composite(cl["im"], (22, 8)); chip = L(im)
    ill = s.get("illust")
    tw = W - 2 * SAFE - 40 - (380 if ill else 0)
    title = text_layer(s["title"], 72, TEXT, tw, True, 1.25)
    sub = text_layer(s.get("sub", " "), 34, MUTED, tw)
    bar = L(Image.new("RGBA", (140, 8), ACC + (255,)))
    if ill:
        ISZ, IPAD = 290, 50
        ibadge = L(badge_pil(ISZ, ill, ACC, IPAD, True, 0.62, True))
        icx, icy = W - SAFE - 20 - (ISZ + 2 * IPAD) // 2 + 14, 330
        check_rect("hero.illust", icx - ISZ // 2 - 24, icy - ISZ // 2 - 24, ISZ + 48, ISZ + 48)
        d1 = L(aa_shape((18, 18), lambda dd, k_: dd.ellipse((0, 0, 18 * k_ - 1, 18 * k_ - 1), fill=ACC + (255,))))
        d2 = L(aa_shape((13, 13), lambda dd, k_: dd.ellipse((0, 0, 13 * k_ - 1, 13 * k_ - 1), fill=ACC2 + (255,))))
        ILL_COUNT[0] += 1
        EVENTS.append((t0 + 0.55, "pop"))
    y = 200
    if chip:
        check_rect("hero.chip", SAFE, y, chip["w"], chip["h"]); y += 78
    ty = y; check_rect("hero.title", SAFE, ty, title["w"], title["h"]); y += title["h"] + 14
    by = y; y += 30
    sy = y; check_rect("hero.sub", SAFE, sy, sub["w"], sub["h"])
    EVENTS.append((t0 + 0.25, "pop")); EVENTS.append((t0 + 0.9, "swell"))
    def draw(f, t):
        if chip:
            e = ease_out(prog(t, 0.2, 0.5)); put(f, chip, SAFE, 122 + int(24 * (1 - e)), 1, e)
        e = ease_out(prog(t, 0.4, 0.7)); put(f, title, SAFE, ty + int(46 * (1 - e)), 1, e)
        e = ease_out(prog(t, 0.8, 0.5)); put(f, bar, SAFE + 4, by, 1, e)
        e = ease_out(prog(t, 1.0, 0.6)); put(f, sub, SAFE, sy + int(30 * (1 - e)), 1, e)
        if ill:
            a = prog(t, 0.5, 0.75); bob = 9 * math.sin(t * 1.7)
            put(f, ibadge, icx - ibadge["w"] / 2, icy - ibadge["h"] / 2 + bob, 0.55 + 0.45 * ease_back(a), ease_out(a * 1.5))
            if LE(0.9, t):
                R = ISZ / 2 + 38; o = ease_out(prog(t, 0.9, 0.6))
                for dl, ph in ((d1, 0.0), (d2, 3.3)):
                    an = t * 0.9 + ph
                    put(f, dl, icx + R * math.cos(an) - dl["w"] / 2, icy + bob + R * 0.92 * math.sin(an) - dl["h"] / 2, 1, o)
    return {"draw": draw, "cam": push_cam(s["sec"], 0.07)}

def build_cards(i, s, t0):
    cs = s["cards"]; n = len(cs)
    gap = 28; cw = int((W - 2 * SAFE - gap * (n - 1)) / n); ch = 360; cy = 190
    title = text_layer(s["title"], 46, TEXT, W - 2 * SAFE, True)
    check_rect("cards.title", SAFE, 104, title["w"], title["h"])
    foc = s.get("focus", -1); tf = s["sec"] * 0.55
    need_sec(i, s, 0.5 + 0.4 * n + 3.0)
    lays, laysf, pos = [], [], []
    for k, c in enumerate(cs):
        for focused in (False, True):
            im = card_img(cw, ch, fill=(CARD2 if focused else CARD), border=(ACC if focused else BORDER),
                          bw=(3 if focused else 2), glow=(ACC if focused else None))
            d = ImageDraw.Draw(im)
            tint = ACC if k != 1 else ACC2
            if c.get("icon"):
                im.alpha_composite(badge_pil(92, c["icon"], tint, 0, False, 0.68), (36 + 24, 36 + 20))
                im.alpha_composite(aa_shape((38, 38), lambda dd, k_: dd.ellipse((0, 0, 38 * k_ - 1, 38 * k_ - 1), fill=tint + (255,))), (36 + cw - 24 - 38, 36 + 24))
                nt = text_layer(str(k + 1), 24, BG_TOP, 38, True)
                im.alpha_composite(nt["im"], (36 + cw - 24 - 38 + int((38 - nt["w"]) / 2) + 1, 36 + 24 + 3))
                head_y = 36 + 134
                if not focused:
                    ILL_COUNT[0] += 1
            else:
                im.alpha_composite(aa_shape((60, 60), lambda dd, k_: dd.ellipse((0, 0, 60 * k_ - 1, 60 * k_ - 1), fill=tint + (255,))), (36 + 24, 36 + 26))
                nt = text_layer(str(k + 1), 34, BG_TOP, 60, True)
                im.alpha_composite(nt["im"], (36 + 24 + int((60 - nt["w"]) / 2) + 1, 36 + 26 + 6))
                head_y = 36 + 112
            yy = put_text(d, 36 + 24, head_y, c["head"], 40, TEXT, cw - 48, True, 1.3)
            yy = put_text(d, 36 + 24, yy + 8, c["body"], 28, MUTED, cw - 48, False, 1.45)
            if not LE(yy, 36 + ch - 16):
                LAYOUT_ERRORS.append(f"cards.card{k+1} 文字があふれる")
            (laysf if focused else lays).append(L(im))
        x = SAFE + k * (cw + gap)
        pos.append((x - 36, cy - 36))
        check_rect(f"cards.card{k+1}", x, cy, cw, ch)
        EVENTS.append((t0 + 0.5 + 0.4 * k, "pop"))
    if foc in range(n):
        EVENTS.append((t0 + tf, "ding"))
    def draw(f, t):
        fo = ease_io(prog(t, tf, 0.45)) if foc in range(n) else 0.0
        e = ease_out(prog(t, 0.1, 0.5)); put(f, title, SAFE, 104 + int(20 * (1 - e)), 1, e * (1 - 0.85 * fo))
        for k in range(n):
            a = prog(t, 0.5 + 0.4 * k, 0.55)
            e = ease_back(a); op = ease_out(a * 1.6)
            x, y = pos[k]; y = y + int(40 * (1 - ease_out(a)))
            sc = 0.82 + 0.18 * e
            if k == foc:
                put(f, lays[k], x, y, sc * (1 + 0.03 * fo), op * (1 - fo))
                put(f, laysf[k], x, y, sc * (1 + 0.03 * fo), op * fo)
            else:
                put(f, lays[k], x, y, sc, op * (1 - 0.5 * fo))
    def cam(t):
        if foc in range(n):
            if not LE(tf, t):
                return (1.0 + 0.03 * ease_io(t / tf), 0.5, 0.5)
            p = ease_io((t - tf) / 1.1)
            tx = (pos[foc][0] + 36 + cw / 2) / W; ty = (cy + ch / 2) / H
            return (1.03 + 0.25 * p, 0.5 + (tx - 0.5) * p, 0.5 + (ty - 0.5) * p)
        return (1.0 + 0.05 * ease_io(t / s["sec"]), 0.5, 0.5)
    return {"draw": draw, "cam": cam}

def build_list(i, s, t0):
    items = s["items"]; n = len(items)
    title = text_layer(s["title"], 46, TEXT, W - 2 * SAFE, True)
    check_rect("list.title", SAFE, 104, title["w"], title["h"])
    rg, rw, ry0 = 16, W - 2 * SAFE, 188
    rh = int(min(100, (CONTENT_BOT - ry0 - (n - 1) * rg) / n)); fs = int(rh * 0.42); cdm = int(rh * 0.6)
    foc = s.get("focus", -1)
    icons = s.get("icons", [])
    tf = 0.7 + 0.8 * n + 0.4
    need_sec(i, s, (tf + 2.7) if foc in range(n) else (0.7 + 0.8 * n + 2.6))
    rows, rowsf, checks, ys = [], [], [], []
    for k, tx in enumerate(items):
        for focused in (False, True):
            im = card_img(rw, rh, r=20, pad=30, fill=(CARD2 if focused else CARD), border=(ACC if focused else BORDER),
                          bw=(3 if focused else 2), glow=(ACC if focused else None))
            cyo = int((rh - cdm) / 2)
            icn = icons[k] if LE(k + 1, len(icons)) else None
            bs = min(64, rh - 24)
            tmax = rw - cdm - 100 - ((bs + 22) if icn else 0)
            im.alpha_composite(aa_shape((cdm, cdm), lambda dd, k_: dd.ellipse((1, 1, cdm * k_ - 2, cdm * k_ - 2), outline=BORDER + (255,), width=3 * k_)), (30 + 24, 30 + cyo))
            tx0 = 30 + 24 + cdm + 26
            if icn:                                          # アイコンは左側(注目時にズームで右が切れても見えるように)
                im.alpha_composite(badge_pil(bs, icn, ACC2, 0, False, 0.68), (tx0, 30 + int((rh - bs) / 2)))
                tx0 += bs + 22
                if not focused:
                    ILL_COUNT[0] += 1
            put_text(ImageDraw.Draw(im), tx0, 30 + int((rh - fs * 1.2) / 2) - 2, tx, fs, TEXT, tmax, False, 1.2)
            if not focused and not LE(text_h(tx, fs, tmax, False, 1.2), rh - 8):
                LAYOUT_ERRORS.append(f"list.row{k+1} 文字があふれる(1行におさめる)")
            (rowsf if focused else rows).append(L(im))
        cs_ = cdm + 8; u = cdm / 44.0
        def draw_ck(dd, k_, cdm=cdm, u=u):
            dd.ellipse((4 * k_, 4 * k_, (4 + cdm) * k_, (4 + cdm) * k_), fill=GREEN + (255,))
            dd.line([((4 + 12 * u) * k_, (4 + 23 * u) * k_), ((4 + 20 * u) * k_, (4 + 31 * u) * k_), ((4 + 33 * u) * k_, (4 + 14 * u) * k_)],
                    fill=BG_TOP + (255,), width=int(max(4, 5 * u) * k_), joint="curve")
        checks.append(L(aa_shape((cs_, cs_), draw_ck)))
        y = ry0 + k * (rh + rg); ys.append(y)
        check_rect(f"list.row{k+1}", SAFE, y, rw, rh)
        EVENTS.append((t0 + 0.7 + 0.8 * k, "tick")); EVENTS.append((t0 + 1.15 + 0.8 * k, "ding"))
    if foc in range(n):
        EVENTS.append((t0 + tf, "success"))
    def draw(f, t):
        fo = ease_io(prog(t, tf, 0.45)) if foc in range(n) else 0.0
        e = ease_out(prog(t, 0.1, 0.5)); put(f, title, SAFE, 104 + int(20 * (1 - e)), 1, e * (1 - 0.85 * fo))
        for k in range(n):
            a = prog(t, 0.7 + 0.8 * k, 0.5); e = ease_out(a)
            xx, yy = SAFE - 30 + int(90 * (1 - e)), ys[k] - 30
            if k == foc:
                put(f, rows[k], xx, yy, 1 + 0.02 * fo, e * (1 - fo)); put(f, rowsf[k], xx, yy, 1 + 0.02 * fo, e * fo)
            else:
                put(f, rows[k], xx, yy, 1, e * (1 - 0.55 * fo))
            c = ease_back(prog(t, 1.15 + 0.8 * k, 0.4))
            sc_ = (1 + 0.02 * fo) if k == foc else 1.0
            rcx, rcy = xx + (rw + 60) / 2, yy + (rh + 60) / 2
            ccx = SAFE + 24 - 4 + checks[k]["w"] / 2; ccy = ys[k] + int((rh - cdm) / 2) - 4 + checks[k]["h"] / 2
            ncx, ncy = rcx + (ccx - rcx) * sc_, rcy + (ccy - rcy) * sc_
            put(f, checks[k], ncx - checks[k]["w"] / 2, ncy - checks[k]["h"] / 2, max(c, 0.01) * sc_, clamp01(c * 3) * (1 - (0.55 * fo if k != foc else 0.0)))
    def cam(t):
        if foc in range(n):
            if not LE(tf, t):
                return (1.0 + 0.02 * ease_io(t / tf), 0.5, 0.5)
            p = ease_io((t - tf) / 1.1)
            return (1.02 + 0.28 * p, 0.5 + (0.42 - 0.5) * p, 0.5 + ((ys[foc] + rh / 2) / H - 0.5) * p)
        return (1.0 + 0.05 * ease_io(t / s["sec"]), 0.5, 0.5)
    return {"draw": draw, "cam": cam}

def build_cta(i, s, t0):
    need_sec(i, s, 6.8)
    cw_, ch_ = 900, 380; cx0, cy0 = int((W - cw_) / 2), 176
    im = card_img(cw_, ch_, r=30, fill=CARD2, glow=ACC2)
    d = ImageDraw.Draw(im)
    ill = s.get("illust")
    tw_ = cw_ - 112 - (230 if ill else 0)
    yy = put_text(d, 36 + 56, 36 + 48, s["title"], 50, TEXT, tw_, True, 1.25)
    yy = put_text(d, 36 + 56, yy + 6, s.get("sub", ""), 30, MUTED, tw_, False, 1.4)
    if not LE(yy, 36 + ch_ - 40 - 76 - 12):
        LAYOUT_ERRORS.append("cta.card 文字がボタンに重なる(見出し・サブを短くする)")
    card = L(im); check_rect("cta.card", cx0, cy0, cw_, ch_)
    if ill:
        csz = 190
        cbadge = L(badge_pil(csz, ill, ACC2, 28, True, 0.62))
        ccx, ccy = cx0 + cw_ - 56 - csz // 2, cy0 + 40 + csz // 2 + 6
        ILL_COUNT[0] += 1
    bw_, bh_ = 340, 76; bx, by = int(W / 2 - bw_ / 2), cy0 + ch_ - bh_ - 40
    bi = Image.new("RGBA", (bw_ + 40, bh_ + 40), (0, 0, 0, 0))
    gl = Image.new("RGBA", bi.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle((20, 24, 20 + bw_, 24 + bh_), 38, fill=ACC + (120,))
    bi = Image.alpha_composite(bi, gl.filter(ImageFilter.GaussianBlur(14)))
    bi.alpha_composite(aa_shape((bw_, bh_), lambda dd, k_: dd.rounded_rectangle((0, 0, bw_ * k_ - 1, bh_ * k_ - 1), 38 * k_, fill=ACC + (255,))), (20, 20))
    bt = text_layer(s.get("button", "OK"), 34, BG_TOP, bw_ - 40, True)
    bi.alpha_composite(bt["im"], (20 + int((bw_ - bt["w"]) / 2), 20 + int((bh_ - bt["h"]) / 2) + 2))
    btn = L(bi)
    ring = L(aa_shape((240, 240), lambda dd, k_: dd.ellipse((10 * k_, 10 * k_, 230 * k_, 230 * k_), outline=ACC + (255,), width=8 * k_)))
    pts = [(4, 3), (4, 38), (13, 30), (20, 46), (27, 43), (20, 28), (33, 28)]
    def draw_cur(dd, k_):
        dd.polygon([((a_ + 2) * k_, (b_ + 2) * k_) for a_, b_ in pts], fill=(0, 0, 0, 110))
        dd.polygon([(a_ * k_, b_ * k_) for a_, b_ in pts], fill=(255, 255, 255, 255))
        dd.line([(a_ * k_, b_ * k_) for a_, b_ in pts + [pts[0]]], fill=(20, 20, 20, 255), width=2 * k_, joint="curve")
    cur = L(aa_shape((44, 52), draw_cur))
    tl = text_layer("✓ " + s.get("toast", "完了しました"), 30, TEXT, 700, True)
    twid = tl["w"] + 64
    ti = aa_shape((twid, 70), lambda dd, k_: dd.rounded_rectangle((0, 0, twid * k_ - 1, 70 * k_ - 1), 35 * k_, fill=(22, 101, 52, 255), outline=GREEN + (255,), width=2 * k_))
    ti.alpha_composite(tl["im"], (32, 10)); toast = L(ti)
    tc, tp = 3.4, 3.7
    EVENTS.extend([(t0 + 0.3, "pop"), (t0 + 1.1, "pop"), (t0 + tc, "click"), (t0 + tp, "success")])
    bcx, bcy = bx + bw_ / 2, by + bh_ / 2
    def draw(f, t):
        a = prog(t, 0.3, 0.6); put(f, card, cx0 - 36, cy0 - 36 + int(40 * (1 - ease_out(a))), 0.9 + 0.1 * ease_back(a), ease_out(a * 1.5))
        if ill:
            a = prog(t, 0.8, 0.6)
            put(f, cbadge, ccx - cbadge["w"] / 2, ccy - cbadge["h"] / 2 + 6 * math.sin(t * 1.6), 0.55 + 0.45 * ease_back(a), ease_out(a * 1.5))
        a = prog(t, 1.1, 0.5); press = 1 - 0.07 * (1 if (LE(tc, t) and LE(t, tc + 0.14)) else 0)
        put(f, btn, bx - 20, by - 20, max(0.01, ease_back(a)) * press, ease_out(a * 1.5))
        p = ease_io(prog(t, 1.9, 1.4)); sx, sy = W - 90, H - 130
        px = sx + (bcx + 30 - sx) * p; py = sy + (bcy + 20 - sy) * p
        if LE(1.9, t):
            put(f, cur, px - 4, py - 3, 1.0 - 0.1 * (1 if (LE(tc, t) and LE(t, tc + 0.14)) else 0), 1.0)
        r = prog(t, tc, 0.6)
        if LE(0.001, r) and not LE(1.0, r):
            put(f, ring, bcx - 120, bcy - 120, 0.25 + 1.3 * ease_out(r), 0.8 * (1 - r))
    def ov(f, t):
        a = ease_back(prog(t, tp, 0.5))
        if LE(tp, t):
            put(f, toast, int(W / 2 - toast["w"] / 2), APP_H + 14 + int(-70 * (1 - a)), 1.0, clamp01(a * 2))
    def cam(t):
        if LE(1.6, t) and LE(t, tc + 1.0):
            p = ease_io((t - 1.6) / 1.4) if LE(t, tc) else 1 - ease_io((t - tc) / 1.0)
            return (1.0 + 0.2 * p, 0.5 + (bcx / W - 0.5) * p, 0.5 + (bcy / H - 0.5) * p)
        return (1.0 + 0.02 * ease_io(t / s["sec"]), 0.5, 0.5)
    return {"draw": draw, "cam": cam, "ov": ov}

BUILDERS = {"hero": build_hero, "cards": build_cards, "list": build_list, "cta": build_cta}
TOTAL = sum(s["sec"] for s in SCENES)
NSC = len(SCENES)
starts, acc = [], 0
for s in SCENES:
    starts.append(acc); acc += s["sec"]
scenes = []
for i, s in enumerate(SCENES):
    if s["type"] not in BUILDERS:
        print("STOP: 場面タイプは hero / cards / list / cta のいずれか: " + str(s["type"])); sys.exit(1)
    sc = BUILDERS[s["type"]](i, s, float(starts[i]))
    cap = text_layer(s["caption"], 29, TEXT, W - 2 * SAFE - 30)
    cap_y = CAP_Y + int((CAP_H - cap["h"]) / 2)
    if not LE(cap["h"], CAP_H - 12):
        LAYOUT_ERRORS.append(f"場面{i+1} 字幕が長すぎる(2行以内に)")
    sc["cap"], sc["cap_y"] = cap, cap_y
    if i != 0:
        EVENTS.append((starts[i] - 0.05, "whoosh"))
    scenes.append(sc)
if LAYOUT_ERRORS:
    print("STOP: レイアウト検査に不合格。設定ブロックの文言・秒数を直してください:")
    for e in LAYOUT_ERRORS:
        print(" -", e)
    sys.exit(1)

appbars = []
for i in range(NSC):
    im = Image.new("RGBA", (W, APP_H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, APP_H), fill=(8, 12, 24, 150))
    im.alpha_composite(aa_shape((28, 28), lambda dd, k_: dd.ellipse((0, 0, 28 * k_ - 1, 28 * k_ - 1), fill=ACC + (255,))), (SAFE, 18))
    nm = text_layer(APP_NAME, 24, TEXT, 500, True); im.alpha_composite(nm["im"], (SAFE + 42, 14))
    for k in range(NSC):
        dot = (ACC + (255,)) if k == i else (BORDER + (255,))
        im.alpha_composite(aa_shape((14, 14), lambda dd, k_, dot=dot: dd.ellipse((0, 0, 14 * k_ - 1, 14 * k_ - 1), fill=dot)), (W - SAFE - (NSC - k) * 26 + 6, 26))
    appbars.append(L(im))

# ---------- 3b. 書き出し時間の見積もりと、FPS の自動調整 ----------
# 実行時間の上限(Copilot では 180 秒)に収めるため、本番の前に、全場面から数コマずつを、本番と同じエンコーダーで試して、1 コマの時間を測る。
# 予想が目安(BUDGET_SEC)を超えるときだけ、FPS を 15 に下げる。15fps でも STOP_SEC を超えるなら、実行前に止める。
BUDGET_SEC, STOP_SEC = 125.0, 135.0
def compose(si_, t):
    tabs_ = starts[si_] + t
    sc_ = scenes[si_]
    f = background(tabs_)
    sc_["draw"](f, t)
    z, cx, cy = sc_["cam"](t)
    if LE(0.002, abs(z - 1.0)):
        bw_, bh_ = W / z, H / z
        x0 = min(max(cx * W - bw_ / 2, 0), W - bw_); y0 = min(max(cy * H - bh_ / 2, 0), H - bh_)
        f = np.asarray(Image.fromarray(f).resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw_, y0 + bh_)))
    f = np.array(f)
    if "ov" in sc_:
        sc_["ov"](f, t)
    put(f, appbars[si_], 0, 0)
    f[APP_H - 3:APP_H, :int(W * (tabs_ / TOTAL))] = ACC
    f[CAP_Y:H] = (f[CAP_Y:H].astype(np.float32) * 0.42).astype(np.uint8)
    put(f, sc_["cap"], SAFE, sc_["cap_y"], 1, ease_out(prog(t, 0.5, 0.4)))
    return f
bench_cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "24",
             "-i", "-", "-an", "-c:v", "libx264", "-preset", "faster", "-crf", "16", "-tune", "animation", "-profile:v", "high",
             "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-f", "null", "-"]
BENCH_PER = 12 if LE(NSC, 4) else 8
bproc = subprocess.Popen(bench_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
tb = time.time(); nb = 0
for si_ in range(NSC):
    sec_ = SCENES[si_]["sec"]
    for j_ in range(BENCH_PER):
        bproc.stdin.write(compose(si_, sec_ * 0.5 + j_ / 24.0).tobytes()); nb += 1
bproc.stdin.close(); bproc.stderr.read(); bproc.wait()
MS_FRAME = (time.time() - tb) * 1000.0 / max(nb, 1) * float(os.environ.get("MKV_BENCH_SCALE", "1"))   # MKV_BENCH_SCALE は試験用(通常は使わない)
def est_sec(fps_):
    return MS_FRAME / 1000.0 * TOTAL * fps_
FPS_NOTE = "変更なし(予想 %d 秒 / 目安 %d 秒)" % (int(est_sec(FPS)), int(BUDGET_SEC))
if not LE(FPS, 15) and not LE(est_sec(FPS), BUDGET_SEC):
    FPS_OLD = FPS; FPS = 15
    FPS_NOTE = "%dfps を 15fps に自動で下げた(予想 %d 秒 → %d 秒 / 目安 %d 秒)" % (FPS_OLD, int(est_sec(FPS_OLD)), int(est_sec(15)), int(BUDGET_SEC))
print("書き出しの見積もり: 1 コマ %.0f ms / %s" % (MS_FRAME, FPS_NOTE))
if not LE(est_sec(FPS), STOP_SEC):
    max_len = int(STOP_SEC / (MS_FRAME / 1000.0 * FPS))
    print("STOP: この長さの動画は、この環境では、実行時間の上限内に作れません(予想 %d 秒)。" % int(est_sec(FPS)))
    print("【このままでは動画を作れません】")
    print("理由: この環境では、この長さの動画を、実行時間の上限(180 秒)内に書き出せません(%dfps で予想 %d 秒)。" % (FPS, int(est_sec(FPS))))
    print("次にしていただくこと: 長さを約 %d 秒以内にして、「続けてください」と送信してください。" % max_len)
    sys.exit(1)

# ---------- 4. 映像(ffmpeg へ生フレームをパイプ) ----------
silent = os.path.join(WORK, "silent.mp4")
cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
       "-i", "-", "-an", "-c:v", "libx264", "-preset", "faster", "-crf", "16", "-tune", "animation", "-profile:v", "high",
       "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
       "-color_trc", "bt709", "-movflags", "+faststart", silent]
t_start = time.time()
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
n = 0; lum = []; smalls = []; CAM_MAX = 1.0; CAM_OFF = 0.0; prev_last = None
PSNR_IDX = [int(TOTAL * FPS * q) for q in (0.2, 0.5, 0.8)]; PSNR_SRC = {}
def shift(fr, dx):
    if dx == 0:
        return fr
    if LE(1, dx):
        return np.concatenate([np.repeat(fr[:, :1], dx, axis=1), fr[:, :W - dx]], axis=1)
    return np.concatenate([fr[:, -dx:], np.repeat(fr[:, -1:], -dx, axis=1)], axis=1)
for si, s in enumerate(SCENES):
    sc = scenes[si]
    for k in range(s["sec"] * FPS):
        t = k / FPS; tabs = starts[si] + t
        f = background(tabs)
        sc["draw"](f, t)
        z, cx, cy = sc["cam"](t)
        CAM_MAX = max(CAM_MAX, z)
        if LE(1.15, z):
            CAM_OFF = max(CAM_OFF, abs(cx - 0.5), abs(cy - 0.5))
        if LE(0.002, abs(z - 1.0)):
            bw_, bh_ = W / z, H / z
            x0 = min(max(cx * W - bw_ / 2, 0), W - bw_); y0 = min(max(cy * H - bh_ / 2, 0), H - bh_)
            f = np.asarray(Image.fromarray(f).resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bw_, y0 + bh_)))
        if k == s["sec"] * FPS - 1:
            last = f.copy()
        if si != 0 and LE(t, TR):
            p = ease_io(t / TR)
            f = (shift(prev_last, -int(110 * p)).astype(np.float32) * (1 - p)
                 + shift(f, int(110 * (1 - p))).astype(np.float32) * p).astype(np.uint8)
        f = np.array(f)
        if "ov" in sc:
            sc["ov"](f, t)
        put(f, appbars[si], 0, 0)
        prg = int(W * (tabs / TOTAL)); f[APP_H - 3:APP_H, :prg] = ACC
        f[CAP_Y:H] = (f[CAP_Y:H].astype(np.float32) * 0.42).astype(np.uint8)
        f[CAP_Y + 18:CAP_Y + CAP_H - 18, SAFE - 18:SAFE - 14] = ACC
        put(f, sc["cap"], SAFE, sc["cap_y"], 1, ease_out(prog(t, 0.5, 0.4)))
        if n % FPS == 0:
            lum.append(float(f.mean()))
        if n % 12 == 0:
            smalls.append(f[::8, ::8].astype(np.int16))
        if n in PSNR_IDX:
            PSNR_SRC[n] = f.copy()
        proc.stdin.write(f.tobytes()); n += 1
    prev_last = last
proc.stdin.close()
err = proc.stderr.read().decode(errors="replace")[:300]
rc = proc.wait()
ENC_SEC = time.time() - t_start
log(f"video encode rc={rc} {time.time()-t_start:.1f}s {err}")
if rc != 0:
    print("STOP: 映像の書き出しに失敗。FPS を 15 にして再実行、だめなら代替手順(B)。"); sys.exit(1)
motion = float(np.mean([np.abs(smalls[j] - smalls[j - 1]).mean() for j in range(1, len(smalls))])) if len(smalls) != 1 else 0.0

# ---------- 5. 音(NumPy で BGM と効果音を生成し、映像の出来事に同期させる) ----------
SR = 44100; N = int(SR * TOTAL); beat = 60.0 / BPM; bar = beat * 4
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)
def sine(freq, n_):
    return np.sin(2 * np.pi * freq * np.arange(n_) / SR)
def noise(n_, seed):
    return np.random.RandomState(seed).uniform(-1, 1, n_)
def ma(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")
CH = [[60, 67, 71, 76], [57, 64, 67, 72], [53, 60, 64, 69], [55, 62, 67, 71]]   # Cmaj7 / Am7 / Fmaj7 / G6(中音域)
BASS_ROOT = [48, 45, 53, 55]
MEL = [[(76, 0, 2), (79, 2, 2), (83, 4, 4)], [(81, 0, 2), (79, 2, 2), (76, 4, 2), (72, 6, 2)],
       [(77, 0, 2), (81, 2, 2), (84, 4, 2), (81, 6, 2)], [(79, 0, 3), (74, 3, 1), (76, 4, 4)],
       [(84, 0, 3), (83, 3, 1), (79, 4, 4)], [(81, 0, 2), (84, 2, 2), (81, 4, 2), (79, 6, 2)],
       [(77, 0, 2), (81, 2, 2), (79, 4, 2), (77, 6, 2)], [(74, 0, 2), (79, 2, 2), (83, 4, 4)]]   # 8小節で1周するメロディ
def ep_note(m, dur):                                  # エレピ風(FM合成)
    n_ = int(dur * SR); t = np.arange(n_) / SR; fr = midi(m)
    y = np.sin(2 * np.pi * fr * t + 1.1 * np.exp(-t * 6.0) * np.sin(2 * np.pi * fr * t)) + 0.15 * np.sin(2 * np.pi * fr * 2 * t)
    return y * np.minimum(t / 0.004, 1.0) * np.exp(-t * 3.0)
def bell_note(m, dur):                                # やわらかいマリンバ・ベル風(FM合成)
    n_ = int(dur * SR); t = np.arange(n_) / SR; fr = midi(m)
    y = np.sin(2 * np.pi * fr * t + 1.4 * np.exp(-t * 7.0) * np.sin(2 * np.pi * fr * 2 * t))
    return y * np.minimum(t / 0.006, 1.0) * np.exp(-t * 3.6)
def add_at(arr, a0, w):
    ln = min(len(w), len(arr) - a0)
    if LE(1, ln):
        arr[a0:a0 + ln] += w[:ln]
pad = np.zeros(N); bass = np.zeros(N); epb = np.zeros(N); mel = np.zeros(N)
eighth = beat / 2.0
for b in range(int(math.ceil(TOTAL / bar)) + 1):
    ch = CH[b % 4]; s0 = int(b * bar * SR)
    if not LE(s0 + 1, N):
        break
    ln = min(int((bar + 0.6) * SR), N - s0); seg = np.arange(ln) / SR
    env = np.clip(seg / 0.9, 0, 1) * np.clip((bar + 0.6 - seg) / 0.9, 0, 1)
    for m in ch:
        fr = midi(m)
        pad[s0:s0 + ln] += (np.sin(2 * np.pi * fr * seg) + 0.3 * np.sin(2 * np.pi * fr * 2 * seg)) * env / 4.0   # うなりが出ないよう、ずらした音は重ねない
    bf = midi(BASS_ROOT[b % 4])
    for st in (0, 4):                                                       # 低音は1拍目と3拍目(倍音つきで小型スピーカーでも聞こえる)
        tb = np.arange(int(1.1 * SR)) / SR
        add_at(bass, s0 + int(st * eighth * SR), (np.sin(2 * np.pi * bf * tb) + 0.5 * np.sin(2 * np.pi * bf * 2 * tb) + 0.25 * np.sin(2 * np.pi * bf * 3 * tb)) * np.minimum(tb / 0.01, 1.0) * np.exp(-tb * 2.6))
    if LE(1, b):
        for st, vel in ((0, 1.0), (3, 0.55), (4, 0.8)):                      # エレピのコード(1拍目・2拍目の裏・3拍目)
            for m in ch:
                add_at(epb, s0 + int(st * eighth * SR), ep_note(m, 1.4) * vel / 4.0)
    if LE(2, b):
        for m, st, lg in MEL[b % 8]:                                        # メロディ(3小節目から入る)
            add_at(mel, s0 + int(st * eighth * SR), bell_note(m, lg * eighth + 0.7))
def norm(x, pk):
    return x / max(np.abs(x).max(), 1e-9) * pk
dry = 0.35 * norm(pad, 1) + 0.45 * norm(bass, 1) + 0.70 * norm(epb, 1) + 0.55 * norm(mel, 1)
n_ir = int(1.6 * SR); ir = np.random.RandomState(21).normal(0, 1, n_ir) * np.exp(-np.arange(n_ir) / SR * 3.2)
ir = ma(ir, 16) * np.minimum(np.arange(n_ir) / (0.02 * SR), 1.0)
nfft = 2 ** int(math.ceil(math.log2(N + n_ir)))
wet = np.fft.irfft(np.fft.rfft(dry, nfft) * np.fft.rfft(ir, nfft), nfft)[:N]                 # 残響(部屋の響き)
wet = wet * (float(np.sqrt((dry ** 2).mean())) / max(float(np.sqrt((wet ** 2).mean())), 1e-9)) * 0.5
bgm = ma(dry + wet, 3)                                                                       # 高音のざらつきをならす
BGM_RMS = 10 ** (-25.0 / 20)                                                                 # BGM単体の平均音量は約 -25dBFS(控えめ)
bgm = bgm * (BGM_RMS / max(float(np.sqrt((bgm ** 2).mean())), 1e-9))
# 音楽らしさの数値: スペクトル平坦度(雑音ほど大きい)と、6kHz以上のエネルギー比(ざらつき)
fl = []
for i0 in range(0, N - 4096, 4096):
    seg_ = bgm[i0:i0 + 4096] * np.hanning(4096)
    if not LE(float(np.sqrt((seg_ ** 2).mean())), 0.01):
        pw = np.abs(np.fft.rfft(seg_)) ** 2 + 1e-12
        fl.append(float(np.exp(np.log(pw).mean()) / pw.mean()))
bgm_flat = float(np.mean(fl)) if fl else 1.0
spec = np.abs(np.fft.rfft(bgm)) ** 2
hi_ratio = float(spec[int(6000 * len(bgm) / SR):].sum() / max(float(spec.sum()), 1e-12))

def sfx_wave(kind):
    if kind == "pop":
        n_ = int(0.16 * SR); tt = np.arange(n_) / SR
        ph = 2 * np.pi * np.cumsum(560 - 1500 * tt) / SR
        return np.sin(ph) * np.exp(-tt * 22) * 0.45
    if kind == "tick":
        n_ = int(0.06 * SR); tt = np.arange(n_) / SR
        return (sine(2200, n_) * 0.6 + (noise(n_, 3) - ma(noise(n_, 3), 6)) * 0.4) * np.exp(-tt * 70) * 0.26
    if kind == "ding":
        n_ = int(0.7 * SR); tt = np.arange(n_) / SR
        return (sine(1568, n_) + 0.5 * sine(2352, n_)) * np.exp(-tt * 6.5) * 0.28
    if kind == "click":
        n_ = int(0.05 * SR); tt = np.arange(n_) / SR
        return ((noise(n_, 5) - ma(noise(n_, 5), 10)) * 0.7 + sine(900, n_) * 0.5) * np.exp(-tt * 90) * 0.40
    if kind == "success":
        n_ = int(1.1 * SR); out = np.zeros(n_)
        for j, m in enumerate([72, 76, 79, 84]):
            a0 = int(j * 0.09 * SR); ln2 = n_ - a0
            out[a0:] += (sine(midi(m), ln2) + 0.4 * sine(midi(m) * 2, ln2)) * np.exp(-np.arange(ln2) / SR * 5.5) * 0.26
        return out
    if kind == "swell":
        n_ = int(1.6 * SR); tt = np.arange(n_) / SR
        return (sine(midi(60), n_) + sine(midi(67), n_) + sine(midi(76), n_)) * np.sin(np.pi * tt / 1.6) ** 2 * 0.12
    if kind == "whoosh":
        n_ = int(0.55 * SR); tt = np.arange(n_) / SR; z = noise(n_, 11)
        lo, mid, hi = ma(z, 120), ma(z, 24), z - ma(z, 6)
        w1, w2 = np.clip(1 - tt / 0.3, 0, 1), np.clip(tt / 0.3, 0, 1) * np.clip((0.55 - tt) / 0.25, 0, 1)
        return (lo * 2.2 * w1 + mid * 1.2 * w2 + hi * 0.25 * w2) * np.sin(np.pi * tt / 0.55) * 0.34
    return np.zeros(10)
sfx = np.zeros(N); duck = np.zeros(N)
for ta, kind in EVENTS:
    a0 = int(max(ta, 0) * SR); w = sfx_wave(kind); ln = min(len(w), N - a0)
    if LE(1, ln):
        sfx[a0:a0 + ln] += w[:ln]
        d_ = min(int(0.45 * SR), N - a0); duck[a0:a0 + d_] = np.maximum(duck[a0:a0 + d_], np.linspace(1, 0, d_))
tt_ = np.arange(N) / SR
fade = np.clip(tt_ / 1.0, 0, 1) * np.clip((TOTAL - tt_) / 2.0, 0, 1)
bgm_part = bgm * (1 - 0.35 * duck) * fade
mix = bgm_part + sfx * fade
gain = 1.0                                                                      # BGMは控えめ(-25dBFS)、効果音ははっきり
mix = 0.89 * np.tanh(mix * gain / 0.89)                                         # やわらかいリミッター(割れ防止)
bgm_part = bgm_part * gain
mask = np.zeros(N, dtype=bool)
for ta, kind in EVENTS:
    a0 = int(max(ta, 0) * SR); mask[a0:a0 + int(0.4 * SR)] = True
bgm_db = 20 * math.log10(max(float(np.sqrt((bgm_part ** 2).mean())), 1e-9))
sfx_ratio_db = 20 * math.log10(max(float(np.sqrt((mix[mask] ** 2).mean())), 1e-9) / max(float(np.sqrt((bgm_part[mask] ** 2).mean())), 1e-9))
wavp = os.path.join(WORK, "audio.wav")
with wave.open(wavp, "wb") as wf:                                               # ステレオ(左右同じ音)で書き出す
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((np.stack([mix, mix], axis=1) * 32767).astype(np.int16).tobytes())

# ---------- 6. 合成 ----------
final = os.path.join(WORK, OUT_NAME)
rc = subprocess.run([FF, "-y", "-loglevel", "error", "-i", silent, "-i", wavp, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                     "-shortest", "-movflags", "+faststart", final], capture_output=True, text=True).returncode
log(f"mux rc={rc}")
if rc != 0:
    print("STOP: 音声の合成に失敗。手順書の代替手順(B)へ。"); sys.exit(1)
try:
    shutil.copy(final, os.path.join(os.getcwd(), OUT_NAME))
    shutil.copy(wavp, os.path.join(os.getcwd(), "audio_preview.wav"))
except Exception as e:
    log(f"copy to cwd failed: {e}")

# ---------- 7. 機械検証(合否はここで出た数値だけで判断する) ----------
checks = []
def chk(name, ok, val, rule):
    checks.append((name, "PASS" if ok else "FAIL", val, rule))
info = {"v": None, "a": None, "dur": None}
if FP:
    p = subprocess.run([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", final], capture_output=True, text=True)
    j = json.loads(p.stdout)
    for st in j["streams"]:
        if st["codec_type"] == "video": info["v"] = st
        if st["codec_type"] == "audio": info["a"] = st
    info["dur"] = float(j["format"]["duration"])
else:
    txt = subprocess.run([FF, "-hide_banner", "-i", final], capture_output=True, text=True).stderr
    v = [l for l in txt.splitlines() if "Video:" in l]; a = [l for l in txt.splitlines() if "Audio:" in l]
    if v:
        res = [t.strip(",") for t in v[0].split() if "x" in t and t.strip(",").replace("x", "").isdigit()]
        info["v"] = {"codec_name": "h264" if "h264" in v[0] else v[0], "width": int(res[0].split("x")[0]) if res else 0,
                     "height": int(res[0].split("x")[1]) if res else 0, "pix_fmt": "yuv420p" if "yuv420p" in v[0] else "other"}
    if a:
        info["a"] = {"codec_name": "aac" if "aac" in a[0] else a[0], "channels": 2 if "stereo" in a[0] else 1,
                     "sample_rate": "44100" if "44100 Hz" in a[0] else "other"}
    d = [l for l in txt.splitlines() if "Duration:" in l]
    if d:
        hh, mm, ss = d[0].split("Duration:")[1].split(",")[0].strip().split(":")
        info["dur"] = int(hh) * 3600 + int(mm) * 60 + float(ss)
v, a = info["v"], info["a"]
fsz = os.path.getsize(final)
chk("ファイルがある", fsz != 0, fsz, "サイズ0でない")
chk("映像コーデック", bool(v) and v.get("codec_name") == "h264", v and v.get("codec_name"), "h264")
chk("画素形式", bool(v) and v.get("pix_fmt") == "yuv420p", v and v.get("pix_fmt"), "yuv420p")
chk("解像度", bool(v) and (v.get("width"), v.get("height")) == (W, H), v and (v.get("width"), v.get("height")), f"{W}x{H}")
chk("長さ", info["dur"] is not None and LE(abs(info["dur"] - TOTAL), 0.3), info["dur"], f"{TOTAL}秒 ±0.3")
chk("音声ストリーム", bool(a) and a.get("codec_name") == "aac", a and a.get("codec_name"), "aac あり")
chk("サイズ上限", LE(fsz, 25 * 1024 * 1024), round(fsz / 1048576, 2), "25MB 以下")
dec = subprocess.run([FF, "-v", "error", "-i", final, "-f", "null", "-"], capture_output=True, text=True)
chk("最後まで復号できる", dec.returncode == 0 and dec.stderr.strip() == "", dec.stderr.strip()[:80] or "エラーなし", "復号エラー0")
chk("黒画面でない", LE(20, min(lum)), round(min(lum), 1), "各秒の平均輝度が20以上")
chk("文字のはみ出しなし", len(LAYOUT_ERRORS) == 0, "なし", f"余白{SAFE}px内・字幕帯と重ならない・秒数が足りる")
types = [s["type"] for s in SCENES]
chk("UI場面(cards/list/cta)の数", LE(2, sum(1 for x in types if x in ("cards", "list", "cta"))), sum(1 for x in types if x in ("cards", "list", "cta")), "2つ以上")
chk("動きがある", LE(1.0, motion), round(motion, 2), "0.5秒ごとの平均画素変化が1.0以上")
chk("ズームがある", LE(1.2, CAM_MAX), round(CAM_MAX, 2), "最大倍率1.2以上")
chk("注目要素へのズーム(中心以外)", LE(0.08, CAM_OFF), round(CAM_OFF, 2), "ズーム中の中心が画面中央から0.08以上ずれる")
nofoc = [i + 1 for i, s_ in enumerate(SCENES) if s_["type"] in ("cards", "list") and s_.get("focus", -1) not in range(len(s_.get("cards", s_.get("items", []))))]
chk("cards/list の全場面に focus 指定", len(nofoc) == 0, "なし" if not nofoc else f"未指定の場面 {nofoc}", "伝えたい要素(カード・行)を focus で指定")
left = [m for m in SAMPLE_MARKERS if any(m in t for t in all_strings(SCENES) + [APP_NAME])]
chk("サンプル・未入力の文言が残っていない", len(left) == 0 or DEMO, "なし" if not left else ("見本として実行(MKV_DEMO=1)" if DEMO else left), "利用者の内容に書き換え済み(サンプルの文言や【要入力】が残っていない)")
ill_names = sorted(set(nm for nm, _, _ in ILL_STATS))
chk("イラストが描画されている", LE(ILLUST_MIN, ILL_COUNT[0]) and (ILLUST_MIN == 0 or LE(0.06, min(cv for _, cv, _ in ILL_STATS))),
    f"{ILL_COUNT[0]}点 {ill_names}", f"イラスト {ILLUST_MIN} 点以上(各イラストが枠の6%以上を占める)")
chk("イラストが枠で欠けていない", all(LE(ed, 10) for _, _, ed in ILL_STATS), "なし" if all(LE(ed, 10) for _, _, ed in ILL_STATS) else [nm for nm, _, ed in ILL_STATS if not LE(ed, 10)], "イラストの外周が切れていない")
kinds = {}
for _, kd in EVENTS:
    kinds[kd] = kinds.get(kd, 0) + 1
chk("効果音の数", LE(NSC + 3, len(EVENTS)), len(EVENTS), f"場面数+3以上({NSC + 3})")
chk("効果音の種類", LE(4, len(kinds)), len(kinds), "4種類以上")
pk = float(np.abs(mix).max()); rms = float(np.sqrt((mix ** 2).mean()))
chk("音が割れていない", LE(pk, 0.95), round(pk, 3), "ピーク0.95以下")
chk("無音でない", LE(0.003, rms), round(rms, 4), "RMS 0.003以上")
chk("BGMの音量(控えめ)", LE(-30, bgm_db) and LE(bgm_db, -22), round(bgm_db, 1), "BGM単体の平均音量 -30〜-22dBFS")
chk("効果音が聞こえる", LE(4.0, sfx_ratio_db), round(sfx_ratio_db, 1), "効果音の瞬間が BGM より 4dB 以上大きい")
chk("BGMが雑音的でない(平坦度)", LE(bgm_flat, 0.001), float(f"{bgm_flat:.2e}"), "スペクトル平坦度 0.001以下(雑音が-30dB以下の、音程のある音楽)")
chk("BGMにざらつきがない(高域)", LE(hi_ratio, 0.001), float(f"{hi_ratio:.2e}"), "6kHz以上のエネルギー比 0.1%以下")
vd = subprocess.run([FF, "-hide_banner", "-i", final, "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
def vol(key):
    for l in vd.splitlines():
        if key + ":" in l:
            return float(l.split(key + ":")[1].replace("dB", "").strip())
    return None
mv, xv = vol("mean_volume"), vol("max_volume")
chk("MP4の平均音量(実測)", mv is not None and LE(-28, mv) and LE(mv, -14), mv, "書き出したMP4の音声を計測: -28〜-14 dB")
chk("MP4の最大音量(実測)", xv is not None and LE(-10, xv) and LE(xv, -1.0), xv, "-10〜-1 dB(小さすぎず、割れない)")
chk("音声の形式", bool(a) and str(a.get("channels")) == "2" and str(a.get("sample_rate")) == "44100", a and (a.get("channels"), a.get("sample_rate")), "ステレオ・44100Hz")
def decode_frame(idx):
    r = subprocess.run([FF, "-v", "error", "-i", final, "-vf", "select=eq(n\\," + str(idx) + ")", "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.uint8) if len(r.stdout) == W * H * 3 else None
psnrs = []
for idx, src in PSNR_SRC.items():
    dd = decode_frame(idx)
    if dd is not None:
        mse = float(((dd.astype(np.float32) - src.reshape(-1).astype(np.float32)) ** 2).mean())
        psnrs.append(99.0 if mse == 0 else 10 * math.log10(255.0 * 255.0 / mse))
chk("画質(元画像との一致 PSNR)", len(psnrs) == 3 and LE(38.0, min(psnrs)), [round(x, 1) for x in psnrs], "3か所すべて 38dB 以上")

# --- 止まり・メモリの検知(長い動画で途中から画面が止まる、メモリがあふれる、を見つける) ---
FREEZE_EPS, FREEZE_MAX_SEC, MEM_LIMIT_MB = 0.02, 2.0, 3000
def freeze_scan():
    r = subprocess.run([FF, "-v", "error", "-i", final, "-vf", "fps=2,scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    raw = np.frombuffer(r.stdout, dtype=np.uint8)
    nfr = len(raw) // (160 * 90)
    if LE(nfr, 2):
        return nfr, 99.0, 0.0
    fr = raw[:nfr * 160 * 90].reshape(nfr, 90, 160).astype(np.int16)
    run = best = 0; dmin = 99.0
    for j in range(1, nfr):
        dj = float(np.abs(fr[j] - fr[j - 1]).mean())
        dmin = min(dmin, dj)
        run = run + 1 if LE(dj, FREEZE_EPS) else 0
        best = max(best, run)
    return nfr, best * 0.5, dmin
fz_n, fz_sec, fz_min = freeze_scan()
chk("画面が止まっていない", LE(0.95 * TOTAL * 2, fz_n) and LE(fz_sec, FREEZE_MAX_SEC), f"最長の静止 {fz_sec}秒・読めたコマ {fz_n}/{int(TOTAL * 2)}",
    f"書き出した MP4 を 0.5 秒ごとに比べ、変化のない区間が {FREEZE_MAX_SEC} 秒以内・最後までコマが読める")
def peak_mem_mb():
    try:
        import resource
        return (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss) / 1024.0
    except Exception:
        return None
pm = peak_mem_mb()
chk("メモリのピーク", pm is None or LE(pm, MEM_LIMIT_MB), "測定不可(この環境では測れない)" if pm is None else f"{pm:.0f}MB", f"{MEM_LIMIT_MB}MB 以下(環境の上限は約 4GB)")
ms_frame = ENC_SEC * 1000.0 / max(n, 1)
chk("FPS(自動調整)", True, f"{FPS}fps / {FPS_NOTE}", "予想時間が目安(125 秒)を超えるときだけ、15fps に自動で下げる。下げたら、報告の(3)に「代替」として書く")
chk("書き出し速度(混雑の目安)", True, f"{ms_frame:.0f}ms/フレーム(基準の約 {ms_frame / 110.0:.1f} 倍)", "参考値: 基準 約110ms/フレーム(Copilot)。2倍を超えたら、報告に「混雑の可能性」と書く")

print(f"\nテンプレート版: {TEMPLATE_VERSION}  場面: {types}")
print(f"効果音: {kinds}")
print("\n| 検証項目 | 結果 | 実測値 | 合格基準 |\n|---|---|---|---|")
for c in checks:
    print(f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} |")
fails = [c[0] for c in checks if c[1] != "PASS"]
print("\n総合:", "全項目合格" if not fails else "不合格 " + ", ".join(fails))
print(f"出力: {OUT_NAME} / 映像の書き出し {time.time()-t_start:.1f}秒 / フレーム {n}")
# ===== CODE END v3.5-auto =====
