import os
import zipfile
import fnmatch
import json

def should_exclude(file_path, exclude_patterns):
    """检查文件是否应该被排除"""
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(file_path, pattern) or file_path.startswith(pattern):
            return True
    return False

def get_version_from_manifest():
    """从manifest.json获取版本号"""
    with open('manifest.json', 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    return manifest['version']

def get_exclude_patterns():
    """从.gitignore获取排除模式"""
    with open('.gitignore', 'r', encoding='utf-8') as f:
        patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return patterns

def package_addon():
    version = get_version_from_manifest()
    exclude_patterns = get_exclude_patterns()
    output_filename = f'ContextFlow_v{version}.ankiaddon'
    
    # 确保release目录存在
    os.makedirs('release', exist_ok=True)
    
    with zipfile.ZipFile(os.path.join('release', output_filename), 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            # 排除.git目录和.gitignore中指定的文件
            if '.git' in dirs:
                dirs.remove('.git')
                
            for dir_name in dirs[:]:
                dir_path = os.path.join(root, dir_name)
                rel_path = os.path.relpath(dir_path, '.')
                if should_exclude(rel_path, exclude_patterns):
                    dirs.remove(dir_name)
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, '.')
                
                # 排除打包脚本本身和.gitignore中指定的文件
                if (file == 'package.py' or 
                    should_exclude(rel_path, exclude_patterns) or 
                    should_exclude(file, exclude_patterns)):
                    continue
                
                try:
                    zipf.write(file_path, rel_path)
                except (PermissionError, IOError) as e:
                    print(f'警告: 跳过文件 {file_path} 由于错误: {e}')
    
    print(f'成功打包: {output_filename}')

if __name__ == '__main__':
    package_addon()
