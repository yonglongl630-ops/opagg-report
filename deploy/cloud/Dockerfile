FROM python:3.12-slim

WORKDIR /app

# 项目仅依赖 Python 标准库（urllib/json/re），无需 pip install
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# --cloud：绑定 0.0.0.0:8000；OPAGG_TOKEN 用于保护 /api/refresh 与 /api/publish
CMD ["python3", "-m", "src.serve", "--cloud", "--port", "8000"]
