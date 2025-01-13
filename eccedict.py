# pip install beautifulsoup4 loguru duckdb
# writemdict -> https://github.com/skywind3000/writemdict
# ======================================================================
#
# eccedict.py -
#
# Created by H1DDENADM1N on 2025/01/09
# Last Modified: 2025/01/13 11:53
#
# ======================================================================
import json
import re
import sys
from datetime import datetime
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

# 定义 Qwerty Learner 项目中使用的 json 字典文件路径
ZK_JSON = Path(r"qwerty-learner\public\dicts\ZhongKaoHeXin.json")  # 2140
GK_JSON = Path(r"qwerty-learner\public\dicts\GaoKao_3500.json")  # 3877
CET4_JSON = Path(r"qwerty-learner\public\dicts\CET4_T.json")  # 2607
CET6_JSON = Path(r"qwerty-learner\public\dicts\CET6_T.json")  # 2345
KY2024_JSON = Path(r"qwerty-learner\public\dicts\KaoYan_2024.json")
KY2025_JSON = Path(r"qwerty-learner\public\dicts\2025KaoYanHongBaoShu.json")  # 7640
TOEFL_JSON = Path(r"qwerty-learner\public\dicts\TOEFL_3_T.json")  # 4264
IELTS_JSON = Path(r"qwerty-learner\public\dicts\IELTS_3_T.json")  # 3575
GRE_JSON = Path(r"qwerty-learner\public\dicts\GRE3000_3_T.json")  # 3036

# 定义自定义排序顺序
CUSTOM_ORDER = ["zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre"]


def configure_logging(log_dir, rotation="1 week", retention="1 month", level="DEBUG"):
    """
    配置日志记录器以输出到控制台和文件，同时保留颜色，并根据当前日期和日志级别生成文件名。

    :param log_dir: 日志文件的目录。
    :param rotation: 日志文件的轮转策略。
    :param retention: 日志文件的保留策略。
    :param level: 日志级别。
    """
    # 使用 pathlib 创建日志目录路径
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 获取当前日期
    current_date = datetime.now().strftime("%Y-%m-%d")

    # 配置控制台日志记录器，显示带颜色的日志
    logger.remove()  # 移除默认的日志记录器
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
        level=level,
    )

    # 配置文件日志记录器，根据日志级别生成不同的日志文件
    log_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
    for log_level in log_levels:
        log_file_path = log_path / f"{current_date}_{log_level}.log"
        logger.add(
            str(log_file_path),
            colorize=True,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            level=log_level,
            rotation=rotation,
            retention=retention,
            filter=lambda record, level=log_level: record["level"].name == level,
        )


def convert_csv_to_stardictdb(csv_file: Path, stardictdb_file: Path):
    """
    字典转化 stardict.csv 转换到 stardict.ddb
    """
    if not csv_file.exists():
        logger.error(f"{csv_file} 未找到")
        raise FileNotFoundError(f"{csv_file} 未找到")
    if stardictdb_file.exists():
        logger.error(f"{stardictdb_file} 已存在")
        raise FileExistsError(f"{stardictdb_file} 已存在")
    # 连接到 stardict.ddb 数据库（如果数据库不存在，则会自动创建）
    conn = duckdb.connect(database=str(stardictdb_file), read_only=False)
    # 读取CSV文件并导入到 stardict.ddb 数据库的 stardict 表中
    conn.execute(f"CREATE TABLE stardict AS SELECT * FROM read_csv_auto('{csv_file}')")
    conn.close()


def build_tag_ddb(json_file: Path, tag_str: str, tagdb_file: Path) -> int:
    """
    从 json 文件 "name" 中取单词，构建 words 表（包含 stardict.ddb 同格式 word 列 和 tag 列）
    返回添加了几个tag的计数
    """
    if not json_file.exists():
        logger.error(f"{json_file} 未找到")
        raise FileNotFoundError(f"{json_file} 未找到")

    # 连接到 tag.ddb 数据库
    conn = duckdb.connect(database=str(tagdb_file), read_only=False)
    cursor = conn.cursor()

    # 创建表（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS words (
            word VARCHAR PRIMARY KEY,
            tag VARCHAR
        )
    """)

    # 统计添加的 tag 数量
    added_tags_count = 0

    # 从 json_file 取单词
    try:
        with json_file.open("r", encoding="utf-8") as f:
            words_data = json.load(f)
            logger.info(f"开始处理文件: {json_file}")

            for word_entry in words_data:
                word = word_entry["name"]
                # 检查单词是否已存在
                cursor.execute("SELECT tag FROM words WHERE word = ?", (word,))
                result = cursor.fetchone()
                if result:
                    # 如果单词已存在，更新 tag
                    existing_tags = result[0]
                    if existing_tags:
                        tags_list = existing_tags.split(" ")
                        if tag_str not in tags_list:  # 去重
                            tags_list.append(tag_str)
                            new_tag = " ".join(tags_list)  # 用空格分隔
                            cursor.execute(
                                "UPDATE words SET tag = ? WHERE word = ?",
                                (new_tag, word),
                            )
                            added_tags_count += 1
                            # logger.debug(f"单词 '{word}' 已存在，追加 tag: {tag_str}")
                    else:
                        cursor.execute(
                            "UPDATE words SET tag = ? WHERE word = ?", (tag_str, word)
                        )
                        added_tags_count += 1
                        # logger.debug(f"单词 '{word}' 已存在，添加新 tag: {tag_str}")
                else:
                    # 如果单词不存在，插入新行
                    cursor.execute(
                        "INSERT INTO words (word, tag) VALUES (?, ?)", (word, tag_str)
                    )
                    added_tags_count += 1
                    # logger.debug(f"单词 '{word}' 不存在，插入新行并添加 tag: {tag_str}")
                conn.commit()
    except Exception as e:
        logger.error(f"从 {json_file} 取单词时发生错误：{e}")
    finally:
        conn.close()
        logger.info(
            f"文件 {json_file} 处理完成，共添加 {added_tags_count} 个 {tag_str} tag"
        )
        return added_tags_count


def update_tag_from_tagdb_to_stardictdb(tagdb_file: Path, stardictdb_file: Path):
    """
    从 tag.ddb 文件中读取 tag 列数据，并更新到 stardict.ddb 文件中的 tag 列
    """
    global CUSTOM_ORDER

    if not stardictdb_file.exists():
        logger.error(f"{stardictdb_file} 未找到")
        raise FileNotFoundError(f"{stardictdb_file} 未找到")
    if not tagdb_file.exists():
        logger.error(f"{tagdb_file} 未找到")
        raise FileNotFoundError(f"{tagdb_file} 未找到")

    # 连接到 stardict.ddb 数据库
    conn = duckdb.connect(database=str(stardictdb_file), read_only=False)
    cursor = conn.cursor()
    # 连接到 tag.ddb 数据库
    tag_conn = duckdb.connect(database=str(tagdb_file), read_only=True)
    tag_cursor = tag_conn.cursor()

    try:
        # 从 tag.ddb 中获取所有单词及其对应的 tag
        tag_cursor.execute("SELECT word, tag FROM words")
        tag_rows = tag_cursor.fetchall()

        # 遍历每个单词，检查 stardict.ddb 中是否存在该单词
        for tag_row in tag_rows:
            (word, new_tag) = tag_row
            if new_tag:  # 只处理有 tag 的单词
                cursor.execute("SELECT tag FROM stardict WHERE word = ?", (word,))
                result = cursor.fetchone()
                if result:
                    # 如果 stardict.ddb 中存在该单词，合并并更新 tag
                    existing_tag = result[0]
                    # 检查 existing_tag 是否为 None，如果是则替换为空字符串
                    existing_tag = existing_tag if existing_tag is not None else ""
                    # 检查 new_tag 是否为 None，如果是则替换为空字符串
                    new_tag = new_tag if new_tag is not None else ""
                    # 合并并排序
                    mixed_tag_set: set = set(existing_tag.split(" ")) | set(
                        new_tag.split(" ")
                    )
                    sorted_tag_list = sorted(
                        mixed_tag_set,
                        key=lambda x: CUSTOM_ORDER.index(x)
                        if x in CUSTOM_ORDER
                        else len(CUSTOM_ORDER),
                    )
                    mixed_tag = " ".join(sorted_tag_list)
                    cursor.execute(
                        "UPDATE stardict SET tag = ? WHERE word = ?", (mixed_tag, word)
                    )
                    logger.debug(
                        f"更新单词 {word} 的 tag: {existing_tag} -> {mixed_tag}"
                    )

        # 提交事务
        conn.commit()

    except Exception as e:
        logger.error(f"更新 tag 时发生错误: {e}")
    finally:
        # 关闭连接
        cursor.close()
        conn.close()
        tag_cursor.close()
        tag_conn.close()


def update_phonetics_from_phoneticsdb_to_stardictdb(
    phoneticsdb_file: Path, stardictdb_file: Path
):
    """
    从 phonetics.ddb 文件中 phon_uk 和 phon_us 列读取英、美音标数据，并更新到 stardict.ddb 文件中的 phonetic 列
    """
    if not stardictdb_file.exists():
        logger.error(f"{stardictdb_file} 未找到")
        raise FileNotFoundError(f"{stardictdb_file} 未找到")
    if not phoneticsdb_file.exists():
        logger.error(f"{phoneticsdb_file} 未找到")
        raise FileNotFoundError(f"{phoneticsdb_file} 未找到")

    # 连接到 stardict.ddb 数据库
    conn = duckdb.connect(database=str(stardictdb_file), read_only=False)
    cursor = conn.cursor()
    # 连接到 phonetics.ddb 数据库
    phonetics_conn = duckdb.connect(database=str(phoneticsdb_file), read_only=True)
    phonetics_cursor = phonetics_conn.cursor()

    try:
        # 从 phonetics.ddb 中获取所有单词及其对应的音标
        phonetics_cursor.execute("SELECT word, phon_uk, phon_us FROM words")
        phonetics_rows = phonetics_cursor.fetchall()

        # 遍历每个单词，检查 stardict.ddb 中是否存在该单词
        for phonetics_row in phonetics_rows:
            (word, phon_uk, phon_us) = phonetics_row
            if phon_uk or phon_us:  # 只处理有音标的单词
                cursor.execute("SELECT phonetic FROM stardict WHERE word = ?", (word,))
                result = cursor.fetchone()
                if result:
                    # 如果 stardict.ddb 中存在该单词，更新音标
                    if phon_uk == phon_us:
                        new_phonetic = phon_uk.strip("/")
                    else:
                        new_phonetic = (
                            f"英 {phon_uk.strip('/')} 美 {phon_us.strip('/')}"
                        )
                    cursor.execute(
                        "UPDATE stardict SET phonetic = ? WHERE word = ?",
                        (new_phonetic, word),
                    )
                    logger.debug(f"更新单词 {word} 的音标: {new_phonetic}")

        # 提交事务
        conn.commit()

    except Exception as e:
        logger.error(f"更新音标时发生错误: {e}")
    finally:
        # 关闭连接
        cursor.close()
        conn.close()
        phonetics_cursor.close()
        phonetics_conn.close()


def build_phonetics_ddb(oald_txt: Path, phoneticsdb_file: Path):
    """
    从 oald-fork.txt 文件中读取单词和英、美音标数据，并生成 phonetics.ddb 数据库（words 表包含 word、phon_uk、phon_us 三个列）
    """
    if not oald_txt.exists():
        logger.error(f"{oald_txt} 未找到")
        raise FileNotFoundError(f"{oald_txt} 未找到")

    # 连接到 phonetics.ddb 数据库
    conn = duckdb.connect(phoneticsdb_file)
    cursor = conn.cursor()

    # 创建表来存储单词和音标信息
    cursor.execute("""
        CREATE TABLE words (
            word TEXT PRIMARY KEY,
            phon_uk TEXT,
            phon_us TEXT
        )
    """)

    with oald_txt.open("r", encoding="utf-8") as f:
        word = None  # 当前词条
        # 逐行读取文件
        for line in f:
            line = line.strip()  # 去除首尾空白字符
            if not line:
                continue  # 跳过空行
            # 处理 "</>" 行
            if line.startswith("</>"):
                word = None  # 重置当前词条
                continue
            # 处理 "@@@LINK=" 行
            elif line.startswith("@@@LINK="):
                word = None  # 重置当前词条
                continue  # 跳过链接行，先建立非链接词条，稍后再处理链接词条
            # 处理普通词条行
            elif line.startswith("<link href="):
                if word is None:
                    logger.debug(f"未找到与行 '{line}' 对应的单词，跳过")
                    continue
                # 提取英式音标
                soup = BeautifulSoup(line, "html.parser")
                phon_uk = soup.find("div", class_="phons_br")
                phon_uk = (
                    phon_uk.find("span", class_="phon").text.strip()
                    if phon_uk
                    else None
                )
                # 提取美式音标
                phon_us = soup.find("div", class_="phons_n_am")
                phon_us = (
                    phon_us.find("span", class_="phon").text.strip()
                    if phon_us
                    else None
                )
                if phon_uk is not None and phon_us is not None:
                    # 将单词和音标信息插入 phonetics.ddb 数据库
                    try:
                        cursor.execute(
                            """
                            INSERT INTO words (word, phon_uk, phon_us)
                            VALUES (?, ?, ?)
                        """,
                            (word, phon_uk, phon_us),
                        )
                    except duckdb.duckdb.ConstraintException:
                        logger.debug(f"词条 {word} 已存在，跳过")
                        pass
            # 处理单词行
            else:
                if re.search(r"[\u4e00-\u9fff]", line):
                    word = None  # 跳过包含中文的行
                    continue
                else:
                    word = line.strip()

    # 提交事务并关闭连接
    conn.commit()
    conn.close()

    handle_linked_words(oald_txt, phoneticsdb_file)


def handle_linked_words(oald_txt: Path, phoneticsdb_file: Path):
    """
    处理 oald-fork.txt 文件中的链接词条
    """
    if not oald_txt.exists():
        logger.error(f"{oald_txt} 未找到")
        raise FileNotFoundError(f"{oald_txt} 未找到")
    if not phoneticsdb_file.exists():
        logger.error(f"{phoneticsdb_file} 数据库文件不存在")
        raise FileNotFoundError(f"{phoneticsdb_file} 数据库文件不存在")
    # 连接到 phonetics.ddb 数据库
    conn = duckdb.connect(phoneticsdb_file)
    cursor = conn.cursor()

    with oald_txt.open("r", encoding="utf-8") as f:
        word = None  # 当前词条
        # 逐行读取文件
        for line in f:
            line = line.strip()  # 去除首尾空白字符
            if not line:
                continue  # 跳过空行
            # 处理 "</>" 行
            if line.startswith("</>"):
                word = None  # 重置当前词条
                continue
            # 处理 "@@@LINK=" 行
            elif line.startswith("@@@LINK="):
                # 从 phonetics.ddb 取 phon_uk 和 phon_us
                linked_to = line.lstrip("@@@LINK=")
                cursor.execute(
                    """
                    SELECT phon_uk, phon_us
                    FROM words
                    WHERE word = ?""",
                    (linked_to,),
                )
                result = cursor.fetchone()

                if result:
                    (phon_uk, phon_us) = result
                    # 更新 phoneticsdb_file 中的 phon_uk 和 phon_am 列
                    if phon_uk is not None and phon_us is not None:
                        # 将单词和音标信息插入数据库
                        try:
                            cursor.execute(
                                """
                                INSERT INTO words (word, phon_uk, phon_us)
                                VALUES (?, ?, ?)
                            """,
                                (word, phon_uk, phon_us),
                            )
                        except duckdb.duckdb.ConstraintException:
                            logger.debug(f"链接词条 {linked_to} 已存在，跳过")
                            pass
            # 处理普通词条行
            elif line.startswith("<link href="):
                word = None  # 跳过普通词条
                continue
            # 处理单词行
            else:
                if re.search(r"[\u4e00-\u9fff]", line):
                    word = None  # 跳过包含中文的行
                    continue
                else:
                    word = line.strip()

    # 提交事务并关闭连接
    conn.commit()
    conn.close()


def convert_stardictdb_to_txt(
    stardictdb_file: Path, txt_file: Path, buffer_size: int = 1_000
):
    """
    从 stardict.ddb 取数据并生成指定格式的 HTML 内容，然后将其写入 stardict.txt 文件，用于生成mdx词典文件
    :param stardictdb_file: stardict.ddb 数据库文件路径
    :param txt_file: 输出的 stardict.txt 文件路径
    :param buffer_size: 缓冲区大小，表示缓存多少条 HTML 内容后写入文件，默认为 1000
    """
    if not stardictdb_file.exists():
        logger.error(f"{stardictdb_file} 未找到")
        raise FileNotFoundError(f"{stardictdb_file} 未找到")
    if txt_file.exists():
        logger.error(f"{txt_file} 已存在")
        raise FileExistsError(f"{txt_file} 已存在")

    # 连接到 stardict.ddb 数据库
    conn = duckdb.connect(database=str(stardictdb_file), read_only=True)
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
    """读取 stardict.txt 文件并解析词条，生成 concise-enhanced.mdx 词典文件"""
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
        title="英汉汉英字典",
        description="<font size=5 color=red>简明英汉汉英字典增强版 - CSS ：20250113<br>"
        "(数据：http://github.com/skywind3000/ECDICT)<br>"
        "1. 开源英汉字典：MIT / CC 双协议<br>"
        "2. 标注牛津三千关键词：音标后 K字符<br>"
        "3. 柯林斯星级词汇标注：音标后 1-5的数字<br>"
        "4. 标注 COCA/BNC 的词频顺序<br>"
        "5. 标注考试大纲信息：中高研四六托雅 等<br>"
        "6. 增加汉英反查、增加英美音标、更新考试大纲信息<br>"
        "</font>",
    )

    # 写入 concise-enhanced.mdx 文件
    with mdx_file.open("wb") as outfile:
        writer.write(outfile)


def calculate_time_interval(log1, log2):
    # 提取时间戳部分
    time_format = "%Y-%m-%d %H:%M:%S"
    timestamp1 = log1.split(" | ")[0]
    timestamp2 = log2.split(" | ")[0]

    # 将时间戳转换为 datetime 对象
    time1 = datetime.strptime(timestamp1, time_format)
    time2 = datetime.strptime(timestamp2, time_format)

    # 计算时间差
    time_diff = time2 - time1

    # 提取小时、分钟、秒
    total_seconds = int(time_diff.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    # 构建结果字符串，忽略值为 0 的部分
    result = []
    if hours > 0:
        result.append(f"{hours}h")
    if minutes > 0:
        result.append(f"{minutes}m")
    if seconds > 0:
        result.append(f"{seconds}s")

    # 如果所有值都为 0，返回 1s
    if not result:
        return "⏱️ 1s"

    return f"⏱️ {''.join(result)}"


if __name__ == "__main__":
    # 配置日志  完整流程耗时  ⏱️2h
    configure_logging("logs", level="DEBUG")

    # 记录开始时间
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 0️⃣ 📁 创建输出目录、定义文件路径  ⏱️1s
    logger.info("创建输出目录、定义文件路径...")
    # 源文件
    csv_file = Path("stardict.csv")
    oald_txt = Path().cwd() / "oald-fork" / "oald-fork.txt"
    # GoldenDict 路径
    goldendict_exe = Path(r"C:\SSS\GoldenDict-ng\goldendict.exe")
    # 输出文件
    output_dir = Path("output")
    stardictdb_file = Path() / output_dir / "stardict.ddb"
    tagdb_file = Path() / "output" / "tag.ddb"
    phoneticsdb_file = Path() / output_dir / "phonetics.ddb"
    txt_file = Path() / output_dir / "stardict.txt"
    mdx_file = Path("concise-enhanced.mdx")
    # 检查源文件是否存在
    if not csv_file.exists():
        raise FileNotFoundError(
            f"{csv_file} 未找到 (stardict.csv 由 stardict.7z 解包获得)"
        )
    if not oald_txt.exists():
        print(
            f"{oald_txt} 未找到 （oald-fork.txt 由 精装牛津十 mdx 使用 AutoMdxBuilder 解包获得）"
        )
    # 检查 GoldenDict 是否存在
    if not goldendict_exe.exists():
        raise FileNotFoundError(f"{goldendict_exe} 未找到 (GoldenDict-ng 软件)")
    # 清空输出目录
    if not output_dir.exists():
        output_dir.mkdir()
    if stardictdb_file.exists():
        # 删除旧的词典数据库文件
        stardictdb_file.unlink()
    if tagdb_file.exists():
        # 删除旧的标签数据库文件
        tagdb_file.unlink()
    if phoneticsdb_file.exists():
        # 删除旧的音标数据库文件
        phoneticsdb_file.unlink()
    if txt_file.exists():
        # 删除旧的 TXT 文件
        txt_file.unlink()
    if mdx_file.exists():
        # 删除旧的 MDX 文件
        mdx_file.unlink()
    logger.info("输出目录、文件路径配置完成")

    # 记录步骤0结束时间
    step0_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(start_time, step0_end_time)
    logger.success(f"步骤0完成，耗时: {time_interval}")

    logger.info("开始转换...")

    # 1️⃣ ⭐ 生成 stardict.ddb  ⏱️1s
    logger.info("生成 stardict.ddb 文件...")
    convert_csv_to_stardictdb(csv_file, stardictdb_file)
    logger.info(f"stardict.ddb 文件已生成：{stardictdb_file}")

    # 记录步骤1结束时间
    step1_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step0_end_time, step1_end_time)
    logger.success(f"步骤1完成，耗时: {time_interval}")

    # 2️⃣ 🔖 生成 tag.ddb  ⏱️1m17s
    logger.info("生成 tag.ddb 文件...")
    zk_tag_count = build_tag_ddb(ZK_JSON, "zk", tagdb_file)
    gk_tag_count = build_tag_ddb(GK_JSON, "gk", tagdb_file)
    cet4_tag_count = build_tag_ddb(CET4_JSON, "cet4", tagdb_file)
    cet6_tag_count = build_tag_ddb(CET6_JSON, "cet6", tagdb_file)
    ky2024_tag_count = build_tag_ddb(KY2024_JSON, "ky", tagdb_file)
    ky2025_tag_count = build_tag_ddb(KY2025_JSON, "ky", tagdb_file)
    toefl_tag_count = build_tag_ddb(TOEFL_JSON, "toefl", tagdb_file)
    ielts_tag_count = build_tag_ddb(IELTS_JSON, "ielts", tagdb_file)
    gre_tag_count = build_tag_ddb(GRE_JSON, "gre", tagdb_file)
    logger.info(
        f"tag.ddb 文件已生成：{tagdb_file}\nzk: {zk_tag_count}\ngk: {gk_tag_count}\nky: {ky2024_tag_count + ky2025_tag_count}\ncet4: {cet4_tag_count}\ncet6: {cet6_tag_count}\ntoefl: {toefl_tag_count}\nielts: {ielts_tag_count}\ngre: {gre_tag_count}"
    )

    # 记录步骤2结束时间
    step2_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step1_end_time, step2_end_time)
    logger.success(f"步骤2完成，耗时: {time_interval}")

    # 3️⃣ 🆕 更新 stardict.ddb 标签信息  ⏱️4m33s  更新了12365条tag
    logger.info("更新标签信息...")
    update_tag_from_tagdb_to_stardictdb(tagdb_file, stardictdb_file)
    logger.info(f"更新标签信息完成：{stardictdb_file}")

    # 记录步骤3结束时间
    step3_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step2_end_time, step3_end_time)
    logger.success(f"步骤3完成，耗时: {time_interval}")

    # 4️⃣ 🔖 生成 phonetics.ddb  ⏱️14m28s
    logger.info("生成 phonetics.ddb 文件...")
    build_phonetics_ddb(oald_txt, phoneticsdb_file)
    logger.info(f"phonetics.ddb 文件已生成：{phoneticsdb_file}")

    # 记录步骤4结束时间
    step4_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step3_end_time, step4_end_time)
    logger.success(f"步骤4完成，耗时: {time_interval}")

    # 5️⃣ 🆕 更新 stardict.ddb 音标信息  ⏱️1h13m20s  更新了160435条音标
    logger.info("更新音标信息...")
    update_phonetics_from_phoneticsdb_to_stardictdb(phoneticsdb_file, stardictdb_file)
    logger.info(f"更新音标信息完成：{stardictdb_file}")

    # 记录步骤5结束时间
    step5_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step4_end_time, step5_end_time)
    logger.success(f"步骤5完成，耗时: {time_interval}")

    # 6️⃣ 📄 生成 stardict.txt  ⏱️26m25s
    logger.info("生成 stardict.txt 文件...")
    convert_stardictdb_to_txt(stardictdb_file, txt_file, buffer_size=1_000_000)
    logger.info(f"stardict.txt 文件已生成：{txt_file}")

    # 记录步骤6结束时间
    step6_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step5_end_time, step6_end_time)
    logger.success(f"步骤6完成，耗时: {time_interval}")

    # 7️⃣ 📦 生成 concise-enhanced.mdx  ⏱️8m49s
    logger.info("生成 concise-enhanced.mdx 文件...")
    generate_mdx(txt_file, mdx_file)
    logger.info(f"concise-enhanced.mdx 文件已生成：{mdx_file}")

    # 记录步骤7结束时间
    step7_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step6_end_time, step7_end_time)
    logger.success(f"步骤7完成，耗时: {time_interval}")

    # 8️⃣ 🔍 打开 GoldenDict，自动重建索引  ⏱️1s
    logger.info("打开 GoldenDict...")
    import subprocess

    subprocess.Popen(str(goldendict_exe))
    logger.info("GoldenDict 已打开")

    # 记录步骤8结束时间
    step8_end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_interval = calculate_time_interval(step7_end_time, step8_end_time)
    logger.success(f"步骤8完成，耗时: {time_interval}")

    # 记录总耗时
    total_time_interval = calculate_time_interval(start_time, step6_end_time)
    logger.success(f"所有步骤完成，总耗时: {total_time_interval}")
