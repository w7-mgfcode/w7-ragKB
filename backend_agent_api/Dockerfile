# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with home directory
RUN groupadd -r agent && useradd -r -g agent -m -d /home/agent agent

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Change ownership to non-root user
RUN chown -R agent:agent /app && \
    chown -R agent:agent /home/agent

# Switch to non-root user
USER agent

# No exposed ports — Slack Socket Mode uses outbound WebSocket only
ENV PYTHONUNBUFFERED=1

# Run the Slack Socket Mode bot
CMD ["python", "main.py"]
