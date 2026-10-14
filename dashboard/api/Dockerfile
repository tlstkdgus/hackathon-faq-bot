# 현황판 API 이미지. 빌드 컨텍스트는 저장소 루트다 (봇 모듈을 함께 담아야 하므로).
#   docker build -f dashboard/api/Dockerfile -t faq-dashboard-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOT_ROOT=/app/bot \
    DATA_DIR=/data \
    TZ=Asia/Seoul

WORKDIR /app

COPY dashboard/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" tzdata

# 봇에서 재사용하는 모듈만 복사한다 (discord.py·LLM SDK는 필요 없다).
# 집계·묶기 기준을 봇과 똑같이 유지하려고 코드를 복사해 고치지 않고 그대로 import한다.
COPY faq_engine.py digest.py paths.py faq.md ./bot/
COPY dashboard/api/app ./app

# 로그는 컨테이너에 굽지 않는다. 실행할 때 /data에 마운트한다.
# (시연용 이미지는 docker-compose.demo.yml이 예시 데이터를 마운트한다)
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
