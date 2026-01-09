#!/bin/bash
# verify-postgres-setup.sh - Verify PostgreSQL migration setup

set -e

echo "======================================"
echo "Wizarr PostgreSQL Setup Verification"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}✗ docker-compose not found${NC}"
    echo "  Please install docker-compose first"
    exit 1
fi
echo -e "${GREEN}✓ docker-compose found${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ .env file not found${NC}"
    echo "  Creating .env from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}  Please edit .env with your Stripe API keys${NC}"
fi

# Check if docker-compose.yml exists
if [ ! -f docker-compose.yml ]; then
    echo -e "${RED}✗ docker-compose.yml not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ docker-compose.yml found${NC}"

# Check if init scripts exist
if [ ! -d docker-entrypoint-initdb.d ]; then
    echo -e "${RED}✗ docker-entrypoint-initdb.d directory not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ docker-entrypoint-initdb.d directory found${NC}"

if [ ! -f docker-entrypoint-initdb.d/01-init-schemas.sql ]; then
    echo -e "${RED}✗ 01-init-schemas.sql not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 01-init-schemas.sql found${NC}"

if [ ! -f docker-entrypoint-initdb.d/02-init-wizarr-schema.sql ]; then
    echo -e "${RED}✗ 02-init-wizarr-schema.sql not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 02-init-wizarr-schema.sql found${NC}"

echo ""
echo "======================================"
echo "Starting Docker Compose Services"
echo "======================================"
echo ""

# Start services
docker-compose up -d

echo ""
echo "Waiting for PostgreSQL to be healthy..."
timeout=60
counter=0
until docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
    sleep 1
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
        echo -e "${RED}✗ PostgreSQL failed to start within ${timeout}s${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ PostgreSQL is healthy${NC}"

echo ""
echo "======================================"
echo "Verifying Database Setup"
echo "======================================"
echo ""

# Check schemas
echo "Checking schemas..."
SCHEMAS=$(docker-compose exec -T postgres psql -U postgres -d postgres -t -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('public', 'stripe');" | tr -d ' ')
if echo "$SCHEMAS" | grep -q "public"; then
    echo -e "${GREEN}✓ public schema exists${NC}"
else
    echo -e "${RED}✗ public schema not found${NC}"
    exit 1
fi

if echo "$SCHEMAS" | grep -q "stripe"; then
    echo -e "${GREEN}✓ stripe schema exists${NC}"
else
    echo -e "${RED}✗ stripe schema not found${NC}"
    exit 1
fi

# Check Wizarr tables
echo ""
echo "Checking Wizarr tables in public schema..."
TABLE_COUNT=$(docker-compose exec -T postgres psql -U postgres -d postgres -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';" | tr -d ' ')
if [ "$TABLE_COUNT" -ge 20 ]; then
    echo -e "${GREEN}✓ Found $TABLE_COUNT tables in public schema${NC}"
else
    echo -e "${YELLOW}⚠ Only $TABLE_COUNT tables found (expected ~22)${NC}"
fi

# Check alembic version
echo ""
echo "Checking migration version..."
ALEMBIC_VERSION=$(docker-compose exec -T postgres psql -U postgres -d postgres -t -c "SELECT version_num FROM alembic_version LIMIT 1;" | tr -d ' ')
if [ -n "$ALEMBIC_VERSION" ]; then
    echo -e "${GREEN}✓ Alembic version: $ALEMBIC_VERSION${NC}"
else
    echo -e "${YELLOW}⚠ No alembic version found${NC}"
fi

# Check services status
echo ""
echo "======================================"
echo "Service Status"
echo "======================================"
echo ""

docker-compose ps

echo ""
echo "======================================"
echo "Connection Information"
echo "======================================"
echo ""
echo "PostgreSQL:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: postgres"
echo "  User: postgres"
echo "  Password: rock-fall-death"
echo ""
echo "Wizarr:"
echo "  URL: http://localhost:5690"
echo ""
echo "Stripe Sync Engine:"
echo "  URL: http://localhost:3000"
echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Visit http://localhost:5690 to configure Wizarr"
echo "2. Check logs: docker-compose logs -f wizarr"
echo "3. See POSTGRES_MIGRATION.md for more information"
echo ""
