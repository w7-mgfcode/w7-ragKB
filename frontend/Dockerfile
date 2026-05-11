# Build stage
FROM node:18-slim as builder

# Set working directory
WORKDIR /app

# Copy package.json only (not the lockfile)
COPY package.json ./

# Install all dependencies fresh (this generates native bindings for the container's architecture)
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Accept build arguments for environment variables
ARG VITE_API_BASE_URL
ARG VITE_AGENT_ENDPOINT
ARG VITE_ENABLE_STREAMING
ARG VITE_LANGFUSE_HOST_WITH_PROJECT
ARG VITE_LANGFUSE_PUBLIC_KEY
ARG VITE_LANGFUSE_HOST
ARG VITE_RATING_THRESHOLDS

# Set environment variables from build args
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_AGENT_ENDPOINT=${VITE_AGENT_ENDPOINT}
ENV VITE_ENABLE_STREAMING=${VITE_ENABLE_STREAMING}
ENV VITE_LANGFUSE_HOST_WITH_PROJECT=${VITE_LANGFUSE_HOST_WITH_PROJECT}
ENV VITE_LANGFUSE_PUBLIC_KEY=${VITE_LANGFUSE_PUBLIC_KEY}
ENV VITE_LANGFUSE_HOST=${VITE_LANGFUSE_HOST}
ENV VITE_RATING_THRESHOLDS=${VITE_RATING_THRESHOLDS}

# Build the application
RUN npm run build

# Production stage
# Note: nginx is used here to serve static files within the container
# Caddy (or another reverse proxy) would sit in front of this container
FROM nginx:alpine

# Install dumb-init for proper signal handling
RUN apk add --no-cache dumb-init

# Create non-root user
RUN addgroup -g 1001 -S appuser && \
    adduser -S appuser -u 1001

# Copy nginx configuration
COPY --from=builder /app/nginx.conf /etc/nginx/nginx.conf

# Copy built application
COPY --from=builder /app/dist /usr/share/nginx/html

# Create nginx cache and run directories
RUN mkdir -p /var/cache/nginx /var/run/nginx && \
    chown -R appuser:appuser /var/cache/nginx /var/run/nginx /usr/share/nginx/html

# Expose port
EXPOSE 8080

# Switch to non-root user
USER appuser

# Use dumb-init to handle signals properly
ENTRYPOINT ["dumb-init", "--"]

# Start nginx
CMD ["nginx", "-g", "daemon off;"]