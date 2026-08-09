# Chainlit needs a long-lived server with WebSocket support, so it is deployed
# as a container rather than as a serverless function.
#
# Hugging Face Spaces serves on port 7860, which is why that is the default;
# any host that runs a container (Railway, Fly, Cloud Run) works the same way.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face runs containers as a non-root user; Chainlit needs to write its
# session files, so give an unprivileged user ownership of the app directory.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

CMD ["sh", "-c", "chainlit run app.py --host 0.0.0.0 --port ${PORT}"]
