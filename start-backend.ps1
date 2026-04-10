# 启动后端（需先安装依赖：pip install -r requirements-web.txt）
Set-Location $PSScriptRoot
python -m uvicorn web_server:app --host 0.0.0.0 --port 8001 --reload
