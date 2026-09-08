FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONOPTIMIZE=1 MALLOC_ARENA_MAX=2
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 bot
COPY --chown=bot:bot bot.py engine.py gateway.py ./
USER bot
CMD ["python", "bot.py"]
