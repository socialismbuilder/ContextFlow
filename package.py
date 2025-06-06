import os
import json
import zipfile
import pathspec

# --- 配置 ---
MANIFEST_FILE = 'manifest.json'
GITIGNORE_FILE = '.gitignore'
RELEASE_DIR = 'release'
# 脚本本身的文件名，也需要被忽略
SCRIPT_NAME = os.path.basename(__file__)

# --- 硬编码的、总是需要忽略的模式 ---
# 即使 .gitignore 里没有写，这些也总是被忽略
# 使用 '/' 后缀表示这是一个目录
ALWAYS_IGNORE = [
    '.git/',
    '.idea/',
    '.vscode/',
    '__pycache__/',
    RELEASE_DIR + '/',
    '*.pyc',
    SCRIPT_NAME,
]

def get_addon_info():
    """从 manifest.json 读取插件信息"""
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        package_name = manifest['package']
        version = manifest['version']
        return package_name, version
    except FileNotFoundError:
        print(f"错误: 未找到 '{MANIFEST_FILE}' 文件。")
        return None, None
    except KeyError as e:
        print(f"错误: '{MANIFEST_FILE}' 文件中缺少键: {e}")
        return None, None

def get_gitignore_spec():
    """读取 .gitignore 文件并合并总是忽略的规则"""
    all_patterns = ALWAYS_IGNORE.copy()
    if os.path.exists(GITIGNORE_FILE):
        print(f"正在读取 '{GITIGNORE_FILE}' 中的忽略规则...")
        with open(GITIGNORE_FILE, 'r', encoding='utf-8') as f:
            # 过滤掉空行和注释行
            gitignore_patterns = [line for line in f.read().splitlines() if line.strip() and not line.strip().startswith('#')]
            all_patterns.extend(gitignore_patterns)
    else:
        print(f"警告: 未找到 '{GITIGNORE_FILE}' 文件。将只使用内置的忽略规则。")

    # 使用 'gitwildmatch' 模式来模拟 git 的行为
    return pathspec.PathSpec.from_lines('gitwildmatch', all_patterns)

def create_addon_package(output_path, spec):
    """创建 .ankiaddon 压缩包"""
    # 获取当前目录下的所有文件和文件夹
    all_files = []
    for root, dirs, files in os.walk('.', topdown=True):
        # 使用 pathspec 来决定哪些目录应该被忽略
        # 注意：这里需要修改 dirs 列表本身，以防止 os.walk 进入这些目录
        # 我们检查的是目录路径，例如 '.\.git' 或 './.git'
        dirs[:] = [d for d in dirs if not spec.match_file(os.path.join(root, d))]
        
        for file in files:
            file_path = os.path.join(root, file)
            # 使用 pathspec 来检查文件是否应该被忽略
            if not spec.match_file(file_path):
                all_files.append(file_path)

    if not all_files:
        print("错误：没有找到任何可以打包的文件。请检查您的忽略规则。")
        return

    print(f"\n准备打包 {len(all_files)} 个文件到 '{output_path}'...")

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in all_files:
            # arcname 参数确保了在 zip 包内的路径是相对路径
            zf.write(file, arcname=file)
            print(f"  -> 已添加: {file}")

    print("\n打包成功！")


def main():
    """主执行函数"""
    print("--- Anki 插件打包脚本 ---")

    # 1. 获取插件信息
    package_name, version = get_addon_info()
    if not package_name or not version:
        return

    print(f"插件名: {package_name}, 版本: {version}")

    # 2. 创建 release 目录
    os.makedirs(RELEASE_DIR, exist_ok=True)

    # 3. 构建输出文件名和路径
    output_filename = f"{package_name}_v{version}.ankiaddon"
    output_path = os.path.join(RELEASE_DIR, output_filename)
    print(f"目标文件: {output_path}")

    # 4. 获取所有忽略规则
    spec = get_gitignore_spec()

    # 5. 创建压缩包
    create_addon_package(output_path, spec)

    print(f"\n✅ 完成！插件已保存至: {os.path.abspath(output_path)}")


if __name__ == '__main__':
    main()