import sys
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    if len(sys.argv) != 2:
        print("用法: python runner.py <epub文件路径>")
        sys.exit(1)
    epub_path = Path(sys.argv[1])
    if not epub_path.exists():
        print(f"文件不存在: {epub_path}")
        sys.exit(1)
    orig_name = epub_path.stem
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 解析
    try:
        subprocess.run([sys.executable, "reader3.py", str(epub_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"解析 epub 失败: {e}")
        sys.exit(2)
    # 构建 _data 路径
    data_folder = epub_path.parent.parent / "data" / f"{orig_name}_data"
    if not data_folder.exists():
        # 兼容新命名
        data_folder = epub_path.parent.parent / "data" / f"{orig_name}_{now_str}_data"
    data_folder = data_folder.resolve()
    # 生成AI缓存
    try:
        subprocess.run([sys.executable, "generate_ai_cache.py", str(data_folder)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"生成 AI 缓存失败: {e}")
        sys.exit(3)
    print("处理完成！")

if __name__ == "__main__":
    main()
