@echo off
setlocal

:: 定义要打包的文件列表（可手动添加其他文件）
set "files=__init__.py,api_client.py,cache_manager.py,config_manager.py,main_logic.py,Process_Card.py,ui_manager.py,config.json,manifest.json"

:: 创建release目录（如果不存在）
if not exist "release" mkdir "release"

:: 打包文件到release目录下的打包.zip（自动覆盖旧文件）
powershell -Command "Compress-Archive -Path %files% -DestinationPath release\ContextFlow.zip -Force"

:: 检查打包结果
if %errorlevel% equ 0 (
    echo 打包成功！文件路径：%cd%\release\ContextFlow.zip
) else (
    echo 打包失败，请检查文件是否存在或权限问题
    exit /b 1
)

endlocal
