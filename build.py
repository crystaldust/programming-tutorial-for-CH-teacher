#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《把话说尽》静态书站生成器

用法：
    python3 build.py

做的事：
    1. 读 content/ 里的 Markdown（每章一个文件）
    2. 生成 dist/ 下的纯静态 HTML（无框架、无外部字体、断网可读）
    3. 额外生成一个单文件版《把话说尽.html》，可以直接发微信

加新的一章：
    把 md 丢进 content/，在 book.json 里给对应章节填上 "file"，重跑 build.py。
"""

import html
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
DIST = os.path.join(ROOT, "dist")
ASSETS = os.path.join(ROOT, "assets")

READ_SPEED = 420  # 字/分钟

# ────────────────────────────── Markdown ──────────────────────────────


def inline(s):
    """行内标记：代码、粗体、斜体、链接。"""
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


SEP_CELL = re.compile(r"^:?-{2,}:?$")


def md_to_html(md):
    """够用的 Markdown 子集：标题、段落、代码块、引用、列表符号、表格、分隔线。"""
    lines = md.replace("\r\n", "\n").split("\n")
    out, para = [], []
    i, n = 0, len(lines)
    h1 = None
    sidx = 0

    def flush_para():
        if para:
            out.append("<p>" + "".join(inline(x) for x in para) + "</p>")
            para.clear()

    while i < n:
        raw = lines[i]
        s = raw.strip()

        if s.startswith("```"):
            flush_para()
            lang = s[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            cls = ' class="language-%s"' % lang if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, html.escape("\n".join(buf))))
            continue

        if not s:
            flush_para()
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush_para()
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1 and h1 is None:
                h1 = text
                i += 1
                continue
            if level == 2:
                sidx += 1
                out.append('<h2 id="s%d">%s</h2>' % (sidx, inline(text)))
            else:
                out.append("<h%d>%s</h%d>" % (level, inline(text), level))
            i += 1
            continue

        if s in ("---", "***", "___"):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        if s.startswith(">"):
            flush_para()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body = "".join(inline(x) for x in buf if x)
            out.append("<blockquote><p>%s</p></blockquote>" % body)
            continue

        if s.startswith("|") and s.endswith("|"):
            flush_para()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            cells = [r for r in cells if not all(SEP_CELL.match(c or "-") for c in r)]
            if cells:
                head, body = cells[0], cells[1:]
                t = ["<table>", "<thead><tr>"]
                t += ["<th>%s</th>" % inline(c) for c in head]
                t.append("</tr></thead><tbody>")
                for r in body:
                    t.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
                t.append("</tbody></table>")
                out.append("".join(t))
            continue

        # 列表项：保留条目感，但不做成 ul，避免打断散文节奏
        if re.match(r"^[-*]\s+", s):
            flush_para()
            out.append("<p class=\"li\">%s</p>" % inline(re.sub(r"^[-*]\s+", "", s)))
            i += 1
            continue

        para.append(s)
        i += 1

    flush_para()
    return h1, "\n".join(out)


def load_chapter(path):
    md = open(path, encoding="utf-8").read()
    h1, body = md_to_html(md)
    plain = re.sub(r"```.*?```", "", md, flags=re.S)
    chars = len(re.sub(r"\s", "", plain))
    return {
        "h1": h1,
        "html": body,
        "chars": chars,
        "minutes": max(1, round(chars / READ_SPEED)),
    }


# ────────────────────────────── 页面骨架 ──────────────────────────────

FAVICON = "favicon.svg"


def shell(title, body, book, cls="", head_extra=""):
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="book">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta name="theme-color" content="#fbf8f1" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#191714" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{favicon}" type="image/svg+xml">
<link rel="stylesheet" href="style.css">
{extra}
</head>
<body class="{cls}">
{body}
</body>
</html>
""".format(
        title=html.escape(title),
        desc=html.escape(book["subtitle"] + "。" + book.get("lead", "")),
        favicon=FAVICON,
        extra=head_extra,
        cls=cls,
        body=body,
    )


def topbar(book, current=None, first_href=None):
    links = ['<a href="index.html"%s>目录</a>' % (' class="on"' if current == "index" else "")]
    if first_href:
        links.append('<a href="%s"%s>开始读</a>' % (first_href, ' class="on"' if current == "read" else ""))
    return """<header class="topbar">
  <a class="brand" href="index.html">%s</a>
  <nav>%s</nav>
</header>
""" % (html.escape(book["title"]), "".join(links))


# ────────────────────────────── 生成 ──────────────────────────────


def build():
    book = json.load(open(os.path.join(ROOT, "book.json"), encoding="utf-8"))

    # 1. 载入所有已发布的章节
    flat = []
    for part in book["parts"]:
        for ch in part["chapters"]:
            if not ch.get("file"):
                continue
            data = load_chapter(os.path.join(CONTENT, ch["file"]))
            href = os.path.splitext(ch["file"])[0] + ".html"
            flat.append({
                "part": part["name"],
                "label": ch.get("label") or ("第%s章" % num_cn(ch["n"]) if ch.get("n") else ""),
                "nav": ch.get("label") or ("第%s章" % num_cn(ch["n"]) if ch.get("n") else part["name"].strip()),
                "n": ch.get("n"),
                "title": ch.get("title") or data["h1"] or "",
                "href": href,
                "chars": data["chars"],
                "minutes": data["minutes"],
                "html": data["html"],
            })
    by_href = {c["href"]: c for c in flat}
    first_href = flat[0]["href"] if flat else None
    # 封面上的"从第一章开始"要指向第一个有编号的章节，而不是序
    start_href = next((c["href"] for c in flat if c["n"]), first_href)

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    # 2. 静态资源
    shutil.copy(os.path.join(ASSETS, "style.css"), os.path.join(DIST, "style.css"))
    shutil.copy(os.path.join(ASSETS, "favicon.svg"), os.path.join(DIST, "favicon.svg"))

    # 3. 章节页
    for idx, c in enumerate(flat):
        prev_c = flat[idx - 1] if idx > 0 else None
        next_c = flat[idx + 1] if idx + 1 < len(flat) else None

        pager = ['<nav class="pager">']
        if prev_c:
            pager.append('<a class="prev" href="%s"><span class="dir">← 回看</span>%s　%s</a>'
                         % (prev_c["href"], prev_c["nav"], html.escape(prev_c["title"])))
        if next_c:
            pager.append('<a class="next" href="%s"><span class="dir">接着读 →</span>%s　%s</a>'
                         % (next_c["href"], next_c["nav"], html.escape(next_c["title"])))
        pager.append("</nav>")

        body = topbar(book, "read", start_href) + """<div class="progress" id="bar"></div>
<main class="wrap">
  <header class="chapter-head">
    %s
    <h1><span class="num">%s</span>%s</h1>
    <p class="meta">约 %s 字 · 读完约 %s 分钟</p>
  </header>
  <article>
%s
  </article>
%s
</main>
<script>%s</script>
""" % (
            "" if c["part"].strip() == c["nav"].strip() else '<p class="part">%s</p>' % html.escape(c["part"]),
            html.escape(c["nav"]),
            html.escape(c["title"]),
            format(c["chars"], ","),
            c["minutes"],
            c["html"],
            "".join(pager),
            reader_js(prev_c["href"] if prev_c else "", next_c["href"] if next_c else ""),
        )

        open(os.path.join(DIST, c["href"]), "w", encoding="utf-8").write(
            shell("%s · %s" % (c["nav"], c["title"]), body, book, cls="chapter")
        )

    # 4. 首页
    parts_html = []
    for part in book["parts"]:
        rows = []
        for ch in part["chapters"]:
            if ch.get("file"):
                c = by_href.get(os.path.splitext(ch["file"])[0] + ".html")
                rows.append(
                    '<li><a class="row" href="%s"><span class="n">%s</span>'
                    '<span class="t">%s</span><span class="badge">%s 分钟</span></a></li>'
                    % (c["href"], html.escape(c["label"]), html.escape(c["title"]), c["minutes"])
                )
            else:
                rows.append(
                    '<li class="pending"><span class="row"><span class="n">%s</span>'
                    '<span class="t">%s</span><span class="badge">待写</span></span></li>'
                    % (html.escape("第%s章" % num_cn(ch["n"])), html.escape(ch["title"]))
                )
        block = ['<section class="part"><h3>%s</h3><ol>%s</ol>'
                 % (html.escape(part["name"]), "".join(rows))]
        if part.get("project"):
            block.append('<p class="project">%s</p>' % html.escape(part["project"]))
        block.append("</section>")
        parts_html.append("".join(block))

    tagline = "<br>".join(html.escape(x) for x in book["tagline"].split("\n"))
    index_body = topbar(book, "index", start_href) + """<main class="wrap">
  <section class="cover">
    <p class="kicker">%s</p>
    <h1 class="book-title">%s</h1>
    <p class="book-sub">%s</p>
    <div class="rule-mark"></div>
    <p class="tagline">%s</p>
    <p class="lead">%s</p>
    <a class="cta" href="%s">从第一章开始</a>
  </section>
  <section class="toc">
    <h2>目　录</h2>
%s
    <p class="colophon">%s</p>
  </section>
</main>
""" % (
        html.escape(book["kicker"]),
        html.escape(book["title"]),
        html.escape(book["subtitle"]),
        tagline,
        html.escape(book["lead"]),
        start_href,
        "\n".join(parts_html),
        html.escape(book["ending"]),
    )

    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(
        shell("%s · %s" % (book["title"], book["subtitle"]), index_body, book, cls="home")
    )

    # 5. 单文件版（发微信、传 U 盘、离线读）
    css = open(os.path.join(ASSETS, "style.css"), encoding="utf-8").read()
    single = [topbar(book, "index", start_href), '<main class="wrap">']
    single.append("""<section class="cover">
  <p class="kicker">%s</p>
  <h1 class="book-title">%s</h1>
  <p class="book-sub">%s</p>
  <div class="rule-mark"></div>
  <p class="tagline">%s</p>
</section>
""" % (html.escape(book["kicker"]), html.escape(book["title"]),
       html.escape(book["subtitle"]), tagline))
    for c in flat:
        single.append('<article id="%s" class="single">' % os.path.splitext(c["href"])[0])
        single.append('<header class="chapter-head"><p class="part">%s</p>'
                      '<h1><span class="num">%s</span>%s</h1></header>'
                      % (html.escape(c["part"]), html.escape(c["label"]), html.escape(c["title"])))
        single.append(c["html"])
        single.append("</article>")
    single.append('<p class="colophon">%s</p></main>' % html.escape(book["ending"]))

    single_body = "\n".join(single)
    single_page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · %s</title>
<style>
%s
</style>
<style>
/* 单文件版的章节分隔 */
article.single { border-top: 1px solid var(--rule); margin-top: 3.5rem; padding-top: 1rem; }
article.single:first-of-type { border-top: 0; }
.topbar nav { display: none; }
</style>
</head>
<body class="chapter">
%s
</body>
</html>
""" % (book["title"], book["subtitle"], css, single_body)

    # 单文件版放在 dist 之外：它是"送人 / 存档"用的，不属于网站本身
    open(os.path.join(ROOT, "把话说尽-单文件版.html"), "w", encoding="utf-8").write(single_page)

    # 6. 报告
    total = sum(c["chars"] for c in flat)
    print("已生成 → %s" % DIST)
    for c in flat:
        print("  %-14s %-26s %s 字" % (c["href"], c["title"], format(c["chars"], ",")))
    print("  共 %d 章，%s 字" % (len(flat), format(total, ",")))
    print("  单文件版：把话说尽-单文件版.html（%.1f KB）"
          % (os.path.getsize(os.path.join(ROOT, "把话说尽-单文件版.html")) / 1024))


def num_cn(n):
    """1 → 一，22 → 二十二。只处理 1–99。"""
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else digits[tens]) + "十" + (digits[ones] if ones else "")


JS_TEMPLATE = """
(function(){
  var bar=document.getElementById('bar'),h=document.documentElement;
  function tick(){
    var max=h.scrollHeight-h.clientHeight;
    var y=h.scrollTop||document.body.scrollTop||0;
    if(bar) bar.style.width=(max>0?(y/max)*100:0)+'__PCT__';
  }
  addEventListener('scroll',tick,{passive:true});
  addEventListener('resize',tick);
  tick();
  var P='__PREV__',N='__NEXT__';
  addEventListener('keydown',function(e){
    if(e.metaKey||e.ctrlKey||e.altKey) return;
    if(e.key==='ArrowLeft'&&P) location.href=P;
    if(e.key==='ArrowRight'&&N) location.href=N;
  });
})();
"""


def reader_js(prev_href, next_href):
    return (JS_TEMPLATE.replace("__PCT__", "%")
            .replace("__PREV__", prev_href)
            .replace("__NEXT__", next_href))


if __name__ == "__main__":
    build()
