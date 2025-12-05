FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY packages/web/package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY packages/web .

# Build the app
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Copy built app from builder
COPY --from=builder /app/build ./build
COPY --from=builder /app/package*.json ./

# Install production dependencies only
RUN npm ci --production

# Expose port
EXPOSE 3000

# Start the app
ENV NODE_ENV=production
CMD ["node", "build"]
