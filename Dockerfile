FROM python:3.11

COPY requirements.txt /app/
COPY app.py /app/
COPY summarization.py /app/
COPY communication.py /app/
COPY prompts/ /app/prompts/
COPY docker-entrypoint.sh /app/

RUN python3 -m pip install -r /app/requirements.txt && \
    chmod +x /app/docker-entrypoint.sh

WORKDIR /app

CMD ["/app/docker-entrypoint.sh"]
