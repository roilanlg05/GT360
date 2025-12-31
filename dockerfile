FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps for building some Python packages if needed
RUN apt-get update \
	&& apt-get install -y --no-install-recommends gcc build-essential \
	&& rm -rf /var/lib/apt/lists/*

# copy requirements and install first (layer caching)
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
	&& pip install --no-cache-dir -r /app/requirements.txt

# copy app source
COPY . /app

# create a non-root user and use it
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# default command to run FastAPI with uvicorn

CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips='127.0.0.1'"]
