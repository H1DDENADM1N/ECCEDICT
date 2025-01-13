from datetime import datetime
from pathlib import Path

import duckdb
from loguru import logger


def convert_stardictdb_to_csv(stardictdb_file: Path, csv_file: Path) -> None:
    """
    将 stardict.ddb 数据库转换回 stardict.csv 文件。

    :param stardictdb_file: DuckDB 数据库文件路径
    :param csv_file: 目标 CSV 文件路径
    :raises FileNotFoundError: 如果 stardictdb_file 不存在
    """
    # 检查输入文件是否存在
    if not stardictdb_file.exists():
        logger.error(f"数据库文件 {stardictdb_file} 未找到")
        raise FileNotFoundError(f"数据库文件 {stardictdb_file} 未找到")

    # 处理目标文件已存在的情况
    if csv_file.exists():
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = csv_file.with_name(f"stardict_old_{current_time}.csv")
        csv_file.rename(new_name)
        logger.info(f"已存在的 {csv_file} 已重命名为 {new_name}")

    try:
        # 连接到 DuckDB 数据库（只读模式）
        with duckdb.connect(database=str(stardictdb_file), read_only=True) as conn:
            # 导出数据到 CSV 文件
            conn.execute(f"COPY stardict TO '{csv_file}' (FORMAT CSV, HEADER)")
            logger.info(f"成功将 {stardictdb_file} 导出为 {csv_file}")
    except Exception as e:
        logger.error(f"导出过程中发生错误: {e}")
        raise


if __name__ == "__main__":
    output_dir = Path("output")
    stardictdb_file = Path() / output_dir / "stardict.ddb"
    stardict_csv = Path() / "stardict.csv"
    convert_stardictdb_to_csv(stardictdb_file, stardict_csv)
