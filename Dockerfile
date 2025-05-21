FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies for Playwright AND xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xauth \ 
    # playwright install-deps should handle most browser-specific X11 libs
    # but if you still have issues, you might need to add more like:
    # libxrender1 libxtst6 libxi6 libnss3 libasound2 libatk-bridge2.0-0 libgtk-3-0
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# COPY . ./src/  <-- This line is problematic if main.py is at the project root
# Assuming main.py is at the root of your project context:
COPY . .  

# Install Playwright browsers and their OS dependencies
RUN playwright install-deps # Installs OS dependencies for browsers
RUN python -m playwright install chromium # Installs the chromium browser itself

# Expose port from environment variable (default 8000)
ARG PORT=8000
ENV PORT=${PORT}
EXPOSE ${PORT}