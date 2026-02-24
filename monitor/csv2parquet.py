import pandas as pd
import sys
import os

def convert_csv_to_parquet(csv_file):
    # 1. 检查文件是否存在
    if not os.path.exists(csv_file):
        print(f"❌ 报告舰长：找不到文件 '{csv_file}'，请确认路径。")
        return

    # 2. 构造输出文件名 (将 .csv 替换为 .parquet)
    file_name, _ = os.path.splitext(csv_file)
    output_file = f"{file_name}.parquet"

    print(f"📡 正在读取 '{csv_file}'...")
    
    try:
        # 使用 pandas 读取 CSV
        # 提示：如果您的数据量巨大，这里可以增加 low_memory=False
        df = pd.read_csv(csv_file)

        # 3. 写入 Parquet 格式
        # 使用 snappy 压缩算法，这是在读写速度和压缩率之间的最佳平衡点
        print(f"📦 正在压缩并写入 '{output_file}'...")
        df.to_parquet(output_file, engine='pyarrow', compression='snappy')
        
        # 计算一下节省了多少空间
        old_size = os.path.getsize(csv_file) / (1024 * 1024)
        new_size = os.path.getsize(output_file) / (1024 * 1024)
        
        print(f"✅ 转换完成！")
        print(f"📊 体积变化: {old_size:.2f}MB -> {new_size:.2f}MB (压缩率: {new_size/old_size:.1%})")

    except Exception as e:
        print(f"💥 警报！转换过程中发生事故: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("💡 用法: python csv2parquet.py <文件名.csv>")
    else:
        convert_csv_to_parquet(sys.argv[1])