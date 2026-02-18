FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps for building some Python packages if needed
RUN apt-get update \
	&& apt-get install -y --no-install-recommends gcc build-essential cron \
	&& rm -rf /var/lib/apt/lists/*

# copy requirements and install first (layer caching)
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip \
	&& pip install --no-cache-dir -r /app/requirements.txt

# copy app source
COPY . /app

# create upload directories for earnings system
RUN mkdir -p /app/uploads/receipts /app/uploads/w9 \
	&& chmod -R 755 /app/uploads

# create a non-root user
RUN useradd -m appuser && chown -R appuser /app

# setup cron job for auto-closing shifts
RUN echo "*/30 * * * * cd /app && /usr/local/bin/python /app/shared/utils/auto_close_shifts_job.py >> /var/log/auto_close_shifts.log 2>&1" | crontab - \
	&& touch /var/log/auto_close_shifts.log

# Copy and set entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN python -m psqlmodel profile save 'dev' \
    --username gt360 --password Rlg*020305 \
	-db gt360 --host postgres \
	--models-path 'shared/db/schemas/auth/' 'shared/db/schemas/entities/' 'shared/db/schemas/trips/' 'shared/db/schemas/drivers/' --default

EXPOSE 8000

# Use entrypoint script to start cron and uvicorn
ENTRYPOINT ["docker-entrypoint.sh"]
