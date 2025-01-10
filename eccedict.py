# pip install beautifulsoup4 loguru duckdb
# writemdict -> https://github.com/skywind3000/writemdict
# ======================================================================
#
# eccedict.py -
#
# Created by H1DDENADM1N on 2025/01/09
# Last Modified: 2025/01/09 21:48
#
# ======================================================================
import re
from pathlib import Path

import duckdb
from bs4 import BeautifulSoup
from loguru import logger

from writemdict.writemdict import MDictWriter

# 支持常见的词性缩写
POS_PATTERN = re.compile(
    r"^(a|na|n|un|v|vt|vi|adj|adv|pron|prep|conj|interj|art|num|aux|pl|sing|past|pp|pres|ger|det|modal|part|suf|pref|abbr|coll|phr)\.\s*(.*)"
)
# 定义正则表达式匹配中文字符
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def convert_csv_to_duckdb(csv_file: Path, duckdb_file: Path):
    """
    字典转化，csv 转换到 duckdb
    """
    if not csv_file.exists():
        logger.error(f"{csv_file} 未找到")
        raise FileNotFoundError(f"{csv_file} 未找到")
    if duckdb_file.exists():
        logger.error(f"{duckdb_file} 已存在")
        raise FileExistsError(f"{duckdb_file} 已存在")
    # 连接到DuckDB数据库（如果数据库不存在，则会自动创建）
    conn = duckdb.connect(database=str(duckdb_file), read_only=False)
    # 读取CSV文件并导入到DuckDB表中
    conn.execute(f"CREATE TABLE stardict AS SELECT * FROM read_csv_auto('{csv_file}')")
    conn.close()


def convert_duckdb_to_txt(duckdb_file: Path, txt_file: Path, buffer_size: int = 1000):
    """
    从 duckdb_file 文件中读取数据并生成指定格式的 HTML 内容，然后将其写入 txt_file 文件，用于生成mdx词典文件
    :param duckdb_file: DuckDB 数据库文件路径
    :param txt_file: 输出的 TXT 文件路径
    :param buffer_size: 缓冲区大小，表示缓存多少条 HTML 内容后写入文件，默认为 1000
    """
    if not duckdb_file.exists():
        logger.error(f"{duckdb_file} 未找到")
        raise FileNotFoundError(f"{duckdb_file} 未找到")
    if txt_file.exists():
        logger.error(f"{txt_file} 已存在")
        raise FileExistsError(f"{txt_file} 已存在")

    # 连接到 DuckDB 数据库
    conn = duckdb.connect(database=str(duckdb_file), read_only=True)
    cursor = conn.cursor()
    query = """SELECT word, phonetic, definition, translation, collins, oxford, tag, bnc, frq, exchange FROM stardict"""
    cursor.execute(query)

    # 一次性读取所有数据
    rows = cursor.fetchall()

    # 写入 txt_file 文件
    with txt_file.open("w", encoding="utf-8") as f:
        buffer = []  # 用于缓存生成的 HTML 内容
        for row in rows:
            (
                word,
                phonetic,
                definition,
                translation,
                collins,
                oxford,
                tag,
                bnc,
                frq,
                exchange,
            ) = row

            # 生成英文到中文的 HTML 结构
            soup = generate_html(
                word,
                phonetic,
                definition,
                translation,
                collins,
                oxford,
                tag,
                bnc,
                frq,
                exchange,
            )
            buffer.append(str(soup) + "\n")

            # 生成中文到英文的 HTML 结构
            if translation:
                translations = translation.split("\\n")
                for trans in translations:
                    # 排除不包含中文的情况
                    if not CHINESE_PATTERN.search(trans):
                        continue
                    # 使用 POS_PATTERN 提取词性和翻译内容
                    match = POS_PATTERN.match(trans)
                    if match:
                        pos_part = match.group(1) + "."  # 词性部分（如 "n."）
                        trans_part = match.group(2)  # 翻译内容部分
                    else:
                        pos_part = ""
                        trans_part = trans
                    # 生成中文到英文的条目
                    chinese_soup = generate_html(
                        trans_part, "", definition, word, "", "", "", "", "", ""
                    )
                    buffer.append(str(chinese_soup) + "\n")

            # 如果缓冲区达到指定大小，写入文件
            if len(buffer) >= buffer_size:
                f.write("".join(buffer))  # 批量写入
                buffer.clear()  # 清空缓冲区

        # 写入剩余的缓冲区内容
        if buffer:
            f.write("".join(buffer))

    # 关闭游标和连接
    cursor.close()
    conn.close()


def generate_html(
    word,
    phonetic,
    definition,
    translation,
    collins,
    oxford,
    tag,
    bnc,
    frq,
    exchange,
):
    """
    生成 HTML 结构
    """
    global POS_PATTERN

    soup = BeautifulSoup(features="html.parser")
    html_tag = soup.new_tag("html")
    soup.append(html_tag)

    head_tag = soup.new_tag("head")
    html_tag.append(head_tag)

    title_tag = soup.new_tag("title")
    title_tag.string = word
    head_tag.append(title_tag)

    link_tag = soup.new_tag(
        "link", href="concise-enhanced.css", rel="stylesheet", type="text/css"
    )
    head_tag.append(link_tag)

    body_tag = soup.new_tag("body")
    html_tag.append(body_tag)

    div_bdy = soup.new_tag("div", **{"class": "bdy", "id": "ecdict"})
    body_tag.append(div_bdy)

    div_ctn = soup.new_tag("div", **{"class": "ctn", "id": "content"})
    div_bdy.append(div_ctn)

    div_hwd = soup.new_tag("div", **{"class": "hwd"})
    div_hwd.string = word
    div_ctn.append(div_hwd)

    hr_hrz = soup.new_tag("hr", **{"class": "hrz"})
    div_ctn.append(hr_hrz)

    # git(ipa hnt oxf col)  phonetic  oxford  collins
    if phonetic or collins or oxford:
        div_git = soup.new_tag("div", **{"class": "git"})
        div_ctn.append(div_git)
        if phonetic:
            span_ipa = soup.new_tag("span", **{"class": "ipa"})
            span_ipa.string = f"[{phonetic}]"
            div_git.append(span_ipa)

        if collins or oxford:
            span_hnt = soup.new_tag("span", **{"class": "hnt"})
            span_hnt.string = "-"
            div_git.append(span_hnt)
            if oxford:
                span_oxf = soup.new_tag(
                    "span", **{"class": "oxf", "title": "Oxford 3000 Keywords"}
                )
                span_oxf.string = "※" * int(oxford)
                div_git.append(span_oxf)

            if collins:
                span_col = soup.new_tag(
                    "span", **{"class": "col", "title": "Collins Stars"}
                )
                span_col.string = "★" * int(collins)
                div_git.append(span_col)

    # gdc(dcb dcb ...)  translation
    # dcb(pos dcn) / dcb(dnt dne)  词性 翻译 / [网络] 翻译
    if translation:
        div_gdc = soup.new_tag("div", **{"class": "gdc"})
        div_ctn.append(div_gdc)

        # 按换行符分割翻译内容
        translations = translation.split("\\n")
        for trans in translations:
            # 匹配词性和翻译内容
            match = POS_PATTERN.match(trans)
            if match:
                pos_part = match.group(1) + "."  # 词性部分（如 "n."）
                trans_part = match.group(2)  # 翻译内容部分
            else:
                pos_part = ""
                trans_part = trans

            # 创建翻译条目的 HTML 结构
            div_dcb = soup.new_tag("span", **{"class": "dcb"})

            # 匹配 dcb(dnt dne)  [网络] 翻译
            if trans_part.startswith("[网络]"):
                span_dnt = soup.new_tag("span", **{"class": "dnt"})
                span_dnt.string = "[网络]"
                div_dcb.append(span_dnt)
                span_dne = soup.new_tag("span", **{"class": "dne"})
                span_dne.string = trans_part.lstrip("[网络]")
                div_dcb.append(span_dne)
            else:
                # 如果有词性，添加词性部分
                if pos_part:
                    span_pos = soup.new_tag("span", **{"class": "pos"})
                    span_pos.string = pos_part
                    div_dcb.append(span_pos)

                # 添加翻译内容部分
                span_dcn = soup.new_tag("span", **{"class": "dcn"})
                span_dcn.string = trans_part
                div_dcb.append(span_dcn)

            # 将翻译条目添加到 gdc 容器中
            div_gdc.append(div_dcb)

            # 添加换行标签
            br_tag = soup.new_tag("br")
            div_gdc.append(br_tag)
    else:
        if definition:
            # 没有中文翻译内容，但有英文定义，则生成英文到英文的条目
            # gcd(dcb dcb ...)  definition
            # dcb(dcn) / dcb(deq)
            div_gdc = soup.new_tag("div", **{"class": "gdc"})
            div_ctn.append(div_gdc)
            definitions = definition.split("\\n")
            for defi in definitions:
                # 创建翻译条目的 HTML 结构
                div_dcb = soup.new_tag("span", **{"class": "dcb"})
                if defi.startswith(">"):
                    span_deq = soup.new_tag("span", **{"class": "deq"})
                    span_deq.string = defi
                    div_dcb.append(span_deq)
                else:
                    span_dcn = soup.new_tag("span", **{"class": "dcn"})
                    span_dcn.string = defi
                    div_dcb.append(span_dcn)
                # 将翻译条目添加到 gdc 容器中
                div_gdc.append(div_dcb)

                # 添加换行标签
                br_tag = soup.new_tag("br")
                div_gdc.append(br_tag)

    # gfm()  exchange
    if exchange:
        div_gfm = soup.new_tag("div", **{"class": "gfm"})
        div_ctn.append(div_gfm)
        exchange_dict = {}
        exchanges = exchange.split("/")
        for exch in exchanges:
            type_part, word_part = exch.split(":", 1)
            if type_part not in exchange_dict:
                exchange_dict[type_part] = []
            exchange_dict[type_part].append(word_part)
        if (  # 时态
            "p" in exchange_dict
            or "d" in exchange_dict
            or "i" in exchange_dict
            or "3" in exchange_dict
        ):
            div_fmb = soup.new_tag("div", **{"class": "fmb"})
            div_fnm = soup.new_tag("span", **{"class": "fnm"})
            div_fnm.string = "时态:"
            div_fmb.append(div_fnm)
            div_frm = soup.new_tag("span", **{"class": "frm"})
            div_frm.string = ", ".join(
                exchange_dict.get("p", [])
                + exchange_dict.get("d", [])
                + exchange_dict.get("i", [])
                + exchange_dict.get("3", [])
            )
            div_fmb.append(div_frm)
            div_gfm.append(div_fmb)
        if (  # 级别
            "r" in exchange_dict or "t" in exchange_dict
        ):
            div_qmb = soup.new_tag("div", **{"class": "qmb"})
            div_qnm = soup.new_tag("span", **{"class": "qnm"})
            div_qnm.string = "级别:"
            div_qmb.append(div_qnm)
            div_qrm = soup.new_tag("span", **{"class": "qrm"})
            div_qrm.string = ", ".join(
                exchange_dict.get("r", []) + exchange_dict.get("t", [])
            )
            div_qmb.append(div_qrm)
            div_gfm.append(div_qmb)
        if (  # 原型
            "0" in exchange_dict and "1" in exchange_dict
        ):
            div_orb = soup.new_tag("div", **{"class": "orb"})
            div_onm = soup.new_tag("span", **{"class": "onm"})
            div_onm.string = "原型:"
            div_orb.append(div_onm)
            div_orm = soup.new_tag("span", **{"class": "orm"})
            # 使用列表存储 what 内容
            what_list = []
            # 根据 exchange_dict 的 "1" 键值填充 what_list
            for key in exchange_dict.get("1", []):
                for char in key:
                    match char:
                        case "p":
                            what_list.append("过去式")
                        case "d":
                            what_list.append("过去分词")
                        case "i":
                            what_list.append("现在分词")
                        case "3":
                            what_list.append("第三人称单数")
                        case "r":
                            what_list.append("比较级")
                        case "t":
                            what_list.append("最高级")
                        case "s":
                            what_list.append("复数形式")
            # 将 what_list 用 "和" 连接起来
            what_str = "和".join(what_list)  # 使用中文顿号连接
            if what_str:
                div_orm.string = (
                    f"{word} 是 {str(exchange_dict.get('0', [])[0])} 的{what_str}"
                )
            else:
                div_orm.string = f"{word} 的原型是 {str(exchange_dict.get('0', [])[0])}"
            div_orb.append(div_orm)
            div_gfm.append(div_orb)

    # frq (tag frq/bnc)
    if tag or frq or bnc:
        div_frq = soup.new_tag(
            "div", **{"class": "frq", "title": f"COCA: {frq}, BNC: {bnc}"}
        )
        tag_list = str(tag).split(" ")
        tag_part = ""
        if "zk" in tag_list:
            tag_part += "中"
        if "gk" in tag_list:
            tag_part += "高"
        if "ky" in tag_list:
            tag_part += "研"
        if "cet4" in tag_list:
            tag_part += "四"
        if "cet6" in tag_list:
            tag_part += "六"
        if "toefl" in tag_list:
            tag_part += "托"
        if "ielts" in tag_list:
            tag_part += "雅"
        if "gre" in tag_list:
            tag_part += "宝"
        if frq or bnc:
            div_frq.string = f"{tag_part} {frq}/{bnc}"
        else:
            div_frq.string = f"{tag_part}"
        div_ctn.append(div_frq)

    hr_hr2 = soup.new_tag("hr", **{"class": "hr2"})
    div_ctn.append(hr_hr2)

    return soup


def generate_mdx(txt_file: Path, mdx_file: Path):
    """读取 txt_file 文件并解析词条，生成 MDX 词典文件"""
    dictionary = {}

    with txt_file.open("r", encoding="utf-8") as f:
        content = f.read()

        # 按 </html> 分割词条
        entries = content.split("</html>")
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue  # 跳过空内容

            # 提取词条和 HTML 内容
            if "<title>" in entry:
                # 提取词条
                start = entry.find("<title>") + len("<title>")
                end = entry.find("</title>")
                word = entry[start:end].strip()

                # 提取完整的 HTML 内容
                html_content = entry + "</html>"

                # 将词条和 HTML 内容存入字典
                dictionary[word] = html_content

    # 使用 MDictWriter 生成 MDX 文件
    writer = MDictWriter(
        dictionary,
        title="英汉汉英字典",  # 从 concise-enhanced.title.html 中提取
        description="<font size=5 color=red>简明英汉汉英字典增强版 - CSS ：20250109<br>"
        "(数据：http://github.com/skywind3000/ECDICT)<br>"
        "1. 开源英汉字典：MIT / CC 双协议<br>"
        "2. 标注牛津三千关键词：音标后 K字符<br>"
        "3. 柯林斯星级词汇标注：音标后 1-5的数字<br>"
        "4. 标注 COCA/BNC 的词频顺序<br>"
        "5. 标注考试大纲信息：中高研四六托雅 等<br>"
        "6. 增加汉英反查<br>"
        "</font>",  # 从 concise-enhanced.info.html 中提取
    )

    # 写入 MDX 文件
    with mdx_file.open("wb") as outfile:
        writer.write(outfile)


if __name__ == "__main__":
    logger.info("开始转换...")

    csv_file = Path("stardict.csv")
    if not csv_file.exists():
        raise FileNotFoundError(f"{duckdb_file} 未找到")

    duckdb_file = Path("stardict.ddb")
    if not duckdb_file.exists():
        convert_csv_to_duckdb(csv_file, duckdb_file)

    txt_file = Path("stardict.txt")
    if txt_file.exists():
        # 删除旧的 TXT 文件
        txt_file.unlink()
    convert_duckdb_to_txt(duckdb_file, txt_file, buffer_size=1_000_000)
    logger.info(f"TXT 文件已生成：{txt_file}")

    mdx_file = Path("concise-enhanced.mdx")
    if mdx_file.exists():
        # 删除旧的 MDX 文件
        mdx_file.unlink()
    generate_mdx(txt_file, mdx_file)
    logger.info(f"MDX 文件已生成：{mdx_file}")

    # goldendict_exe = Path(r"C:\SSS\GoldenDict-ng\goldendict.exe")
    # if goldendict_exe.exists():
    #     # 打开 GoldenDict，自动重建索引
    #     import subprocess

    #     subprocess.run(str(goldendict_exe))
