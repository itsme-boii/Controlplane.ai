# ==========================================
# Stage 1: Build the Next.js frontend
# ==========================================
FROM node:20-slim AS frontend-builder
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /app/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./

# Bake the relative /api path into the build so the browser proxies requests 
# through the Next.js server to the internal FastAPI backend.
ENV NEXT_PUBLIC_GATEWAY_URL="/api"
RUN pnpm build

# ==========================================
# Stage 2: Build the FastAPI backend + Node
# ==========================================
FROM python:3.11-slim

# Install Node.js so we can run the Next.js production server alongside Python
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages
COPY gateway/ /app/gateway/
COPY policy/ /app/policy/
COPY detectors/ /app/detectors/
COPY decision/ /app/decision/

# Install Python dependencies using uv
RUN pip install uv && \
    cd gateway && \
    uv pip install --system -e ../policy -e ../detectors -e ../decision -e .

# Copy policies
COPY policies/ /app/policies/

# Copy the built Next.js application from Stage 1
COPY --from=frontend-builder /app/web /app/web

# Expose Render's default port
EXPOSE 10000

# Create a startup script that runs both servers
RUN echo '#!/bin/bash\n\
# Start FastAPI backend in the background on port 8000 (internal)\n\
cd /app/gateway && uvicorn controlplane_gateway.main:app --host 127.0.0.1 --port 8000 &\n\
\n\
# Wait for backend to be ready\n\
sleep 3\n\
\n\
# Start Next.js frontend on the public port provided by Render ($PORT)\n\
# Next.js will proxy /api requests to 127.0.0.1:8000\n\
cd /app/web && pnpm start --port ${PORT:-10000}\n\
' > /app/start.sh && chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]
