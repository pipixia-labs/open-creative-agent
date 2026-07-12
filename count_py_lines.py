import os

# 需要排除的目录（可按需补充）
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "build",
    "dist",
}

def count_lines_in_py_files(root_dir: str) -> tuple[int, int]:
    total_lines = 0
    file_count = 0

    for root, dirs, files in os.walk(root_dir):
        # 原地修改 dirs，阻止 os.walk 进入这些目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        total_lines += len(lines)
                        file_count += 1
                except (UnicodeDecodeError, OSError):
                    print(f"跳过无法读取的文件: {file_path}")

    return total_lines, file_count


if __name__ == "__main__":
    project_root = os.getcwd()  # 默认统计当前目录
    lines, files = count_lines_in_py_files(project_root)

    print(f"📁 项目路径: {project_root}")
    print(f"🐍 Python 文件数量: {files}")
    print(f"📏 Python 代码总行数: {lines}")
