#!/bin/bash
# Production startup script for Telegram Bot with webhook

set -e

echo "========================================="
echo "🤖 Starting Telegram Bot in Production Mode"
echo "========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found${NC}"
    echo -e "${YELLOW}💡 Copy .env.example to .env and configure it first${NC}"
    exit 1
fi

# Source .env
set -a
source .env
set +a

# Check required variables
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo -e "${RED}❌ Error: TELEGRAM_BOT_TOKEN not set in .env${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment configuration loaded${NC}"

# Start Docker containers
echo -e "\n${YELLOW}📦 Starting Docker containers...${NC}"
docker compose up -d

# Wait for services to be healthy
echo -e "\n${YELLOW}⏳ Waiting for services to be healthy...${NC}"
sleep 10

# Check if web service is healthy
if docker compose ps web | grep -q "healthy"; then
    echo -e "${GREEN}✅ Web service is healthy${NC}"
else
    echo -e "${RED}❌ Web service is not healthy${NC}"
    docker compose logs web
    exit 1
fi

# Check if ngrok is running
echo -e "\n${YELLOW}🌐 Checking ngrok status...${NC}"
sleep 5

NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; data=json.load(sys.stdin); print([t['public_url'] for t in data.get('tunnels', []) if t.get('proto')=='https'][0] if data.get('tunnels') else '')" 2>/dev/null)

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}❌ Error: Could not get ngrok URL${NC}"
    echo -e "${YELLOW}💡 Check ngrok logs: docker compose logs ngrok${NC}"
    exit 1
fi

echo -e "${GREEN}✅ ngrok is running${NC}"
echo -e "${GREEN}   Public URL: ${NGROK_URL}${NC}"

# Setup webhook
echo -e "\n${YELLOW}🔗 Setting up Telegram webhook...${NC}"
WEBHOOK_URL="${NGROK_URL}/telegram/webhook/"

python3 scripts/setup_telegram_webhook.py set --url "$WEBHOOK_URL"

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}=========================================${NC}"
    echo -e "${GREEN}✅ Bot Successfully Started!${NC}"
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}🔗 Webhook URL: ${WEBHOOK_URL}${NC}"
    echo -e "${GREEN}🌐 ngrok URL: ${NGROK_URL}${NC}"
    echo -e "${GREEN}📊 ngrok dashboard: http://localhost:4040${NC}"
    echo -e "${GREEN}🎯 Now send a message to your bot to test!${NC}"
    echo -e "${GREEN}=========================================${NC}"
else
    echo -e "${RED}❌ Failed to setup webhook${NC}"
    exit 1
fi

# Show logs
echo -e "\n${YELLOW}📋 Showing web service logs (Ctrl+C to stop):${NC}"
docker compose logs -f web
