"""
打包脚本 - 将 GUI 程序打包为独立 .exe (onedir 模式)
运行: python build_exe.py
输出: dist\图片透明处理工具\图片透明处理工具.exe
"""
import subprocess
import sys
import os

# 确保在脚本所在目录运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"工作目录: {os.getcwd()}")

# 安装 PyInstaller（如果还没装）
print("\n[1/3] 检查 PyInstaller...")
try:
    import PyInstaller
    print(f"  PyInstaller {PyInstaller.__version__} 已安装")
except ImportError:
    print("  正在安装 PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

# 清理旧构建
print("\n[2/3] 清理旧构建...")
for d in ["dist", "build"]:
    if os.path.exists(d):
        import shutil
        shutil.rmtree(d)
        print(f"  已删除 {d}/")

# 构建
print("\n[3/3] 开始打包...")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",                          # 文件夹模式（不往C盘Temp写东西）
    "--windowed",                        # 无终端窗口
    "--name", "图片透明处理工具",
    "--add-data", f"图片透明处理工具.py{os.pathsep}.",  # 保留源码
    "--clean",
    "--noconfirm",
    "图片透明处理工具.py"
]

print(f"  命令: {' '.join(cmd)}")
result = subprocess.run(cmd)

if result.returncode == 0:
    exe_path = os.path.join("dist", "图片透明处理工具", "图片透明处理工具.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[OK] 打包成功!")
        print(f"  输出: {os.path.abspath(exe_path)}")
        print(f"  大小: {size_mb:.1f} MB")
    else:
        print(f"\n[WARN] 打包完成但找不到 .exe")
        print(f"  检查 dist/ 目录内容...")
        for root, dirs, files in os.walk("dist"):
            for f in files:
                print(f"    {os.path.join(root, f)}")
else:
    print(f"\n[FAIL] 打包失败 (exit code {result.returncode})")
