#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# AGVS4RTL Setup Wizard — First-time setup script
# Generates .env, builds Docker images, starts
# services, and verifies health.
# ──────────────────────────────────────────────

# ── Colors ───────────────────────────────────
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
CYAN='\033[1;36m'
NC='\033[0m' # No Color

# ── Trap SIGINT ──────────────────────────────
trap 'echo -e "\n${YELLOW}Setup cancelled.${NC}"; exit 130' SIGINT

# ── Parse flags ──────────────────────────────
NON_INTERACTIVE=false
if [[ "${1:-}" == "--help" ]]; then
    echo "AGVS4RTL Setup Wizard"
    echo ""
    echo "Usage: bash scripts/setup.sh [--help|--non-interactive]"
    echo "  --help              Show this help"
    echo "  --non-interactive   Use all defaults, no prompts"
    exit 0
fi
if [[ "${1:-}" == "--non-interactive" ]]; then
    NON_INTERACTIVE=true
fi


# ╔══════════════════════════════════════════════╗
# ║  SECTION 1 — Banner                         ║
# ╚══════════════════════════════════════════════╝
echo -e "${GREEN}"
echo "╔══════════════════════════════════════╗"
echo "║      AGVS4RTL Setup Wizard          ║"
echo "║   Multi-Agent RTL Gen & Verify      ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"


# ╔══════════════════════════════════════════════╗
# ║  SECTION 2 — Prerequisites check            ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[1/9] Checking prerequisites...${NC}"

# Check Docker
if ! docker --version >/dev/null 2>&1; then
    echo -e "${RED}Docker not found. Please install Docker first: https://docs.docker.com/engine/install/${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker found"

# Determine compose command
DOCKER_COMPOSE=""
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose --version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}Neither 'docker compose' nor 'docker-compose' found. Please install Docker Compose: https://docs.docker.com/compose/install/${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker Compose found (${DOCKER_COMPOSE})"


# ╔══════════════════════════════════════════════╗
# ║  SECTION 3 — USER_ID / GROUP_ID detection   ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[2/9] Detecting user mapping...${NC}"

USER_ID=$(id -u)
GROUP_ID=$(id -g)

if [[ "$USER_ID" == "0" ]]; then
    echo -e "  ${YELLOW}⚠ Running as root. Consider creating a non-root user for Docker.${NC}"
fi

export USER_ID GROUP_ID
echo -e "  ${GREEN}✓${NC} USER_ID=${USER_ID} GROUP_ID=${GROUP_ID}"


# ╔══════════════════════════════════════════════╗
# ║  SECTION 4 — Existing .env detection        ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[3/9] Checking .env...${NC}"

SKIP_TO_DOCKER=false
GEN_ENV=false

if [[ -f .env ]]; then
    if $NON_INTERACTIVE; then
        echo -e "  ${YELLOW}ℹ Existing .env found, using as-is (non-interactive mode)${NC}"
        SKIP_TO_DOCKER=true
    else
        echo -e "  ${YELLOW}Existing .env found.${NC}"
        read -p "  [M]erge new defaults / [O]verwrite / [S]kip? [M] " choice
        choice=${choice:-M}

        case "$choice" in
            [Oo]*)
                echo -e "  ${YELLOW}Backing up to .env.bak...${NC}"
                cp .env .env.bak
                echo -e "  ${YELLOW}Overwriting .env${NC}"
                GEN_ENV=true
                ;;
            [Ss]*)
                echo -e "  ${YELLOW}Skipping .env generation, using existing.${NC}"
                SKIP_TO_DOCKER=true
                ;;
            *)
                # Merge: read existing keys, only add missing ones
                echo -e "  ${YELLOW}Merging — will only add missing keys to existing .env${NC}"
                ;;
        esac
    fi
else
    GEN_ENV=true
fi

if $SKIP_TO_DOCKER; then
    # Source existing .env to pick up USER_ID/GROUP_ID for docker-compose
    set -a
    source .env
    set +a
fi


# ╔══════════════════════════════════════════════╗
# ║  SECTION 5 — LLM configuration              ║
# ╚══════════════════════════════════════════════╝
if ! $SKIP_TO_DOCKER; then
    echo -e "${CYAN}[4/9] LLM configuration...${NC}"

    if $NON_INTERACTIVE; then
        LLM_ENABLED=false
        llm_base_url=""
        llm_api_key=""
        llm_model=""
        echo -e "  ${YELLOW}ℹ LLM disabled (non-interactive mode)${NC}"
    else
        read -p "  Enable LLM support? [y/N] " llm_choice
        if [[ "$llm_choice" =~ ^[Yy]$ ]]; then
            LLM_ENABLED=true
            read -p "  LLM Base URL: " llm_base_url
            read -s -p "  LLM API Key (hidden): " llm_api_key; echo
            read -p "  LLM Model name: " llm_model
        else
            LLM_ENABLED=false
            llm_base_url=""
            llm_api_key=""
            llm_model=""
            echo -e "  ${YELLOW}ℹ LLM disabled${NC}"
        fi
    fi
fi


# ╔══════════════════════════════════════════════╗
# ║  SECTION 6 — Timeout configuration          ║
# ╚══════════════════════════════════════════════╝
if ! $SKIP_TO_DOCKER; then
    echo -e "${CYAN}[5/9] Timeout configuration...${NC}"

    if $NON_INTERACTIVE; then
        VERIFY_SERVICE_TIMEOUT_SECONDS=240
        GEN_SERVICE_TIMEOUT_SECONDS=600
        AGVS4RTL_LLM_TIMEOUT_SECONDS=300
        echo -e "  ${YELLOW}ℹ Using default timeout values (240/600/300)${NC}"
    else
        read -p "  Use default timeout values? [Y/n] " timeout_choice
        timeout_choice=${timeout_choice:-Y}
        if [[ "$timeout_choice" =~ ^[Yy]$ ]]; then
            VERIFY_SERVICE_TIMEOUT_SECONDS=240
            GEN_SERVICE_TIMEOUT_SECONDS=600
            AGVS4RTL_LLM_TIMEOUT_SECONDS=300
            echo -e "  ${GREEN}✓${NC} Using defaults: verify=240s gen=600s llm=300s"
        else
            read -p "  VERIFY_SERVICE_TIMEOUT_SECONDS [240]: " v
            read -p "  GEN_SERVICE_TIMEOUT_SECONDS [600]: " g
            read -p "  AGVS4RTL_LLM_TIMEOUT_SECONDS [300]: " l
            VERIFY_SERVICE_TIMEOUT_SECONDS=${v:-240}
            GEN_SERVICE_TIMEOUT_SECONDS=${g:-600}
            AGVS4RTL_LLM_TIMEOUT_SECONDS=${l:-300}
        fi
    fi
fi


# ╔══════════════════════════════════════════════╗
# ║  SECTION 7 — Generate .env file             ║
# ╚══════════════════════════════════════════════╝
generate_env() {
    local outfile=".env.tmp"

    cat > "$outfile" <<EOF
# AGVS4RTL Environment Configuration
# Generated by setup.sh on $(date)

# User mapping
USER_ID=${USER_ID}
GROUP_ID=${GROUP_ID}

# LLM Configuration
AGVS4RTL_LLM_ENABLED=${LLM_ENABLED:-false}
AGVS4RTL_LLM_BASE_URL=${llm_base_url:-}
AGVS4RTL_LLM_API_KEY=${llm_api_key:-}
AGVS4RTL_LLM_MODEL=${llm_model:-}
AGVS4RTL_LLM_PROFILE=default

# Timeout settings (seconds)
VERIFY_SERVICE_TIMEOUT_SECONDS=${VERIFY_SERVICE_TIMEOUT_SECONDS:-240}
GEN_SERVICE_TIMEOUT_SECONDS=${GEN_SERVICE_TIMEOUT_SECONDS:-600}
AGVS4RTL_LLM_TIMEOUT_SECONDS=${AGVS4RTL_LLM_TIMEOUT_SECONDS:-300}
EOF

    mv "$outfile" .env
}

merge_env() {
    # Read existing .env, only add keys from the template that don't already exist
    local tmpfile=".env.tmp"

    # Generate template into tmpfile
    cat > "$tmpfile" <<EOF
# AGVS4RTL Environment Configuration
# Generated by setup.sh on $(date)

# User mapping
USER_ID=${USER_ID}
GROUP_ID=${GROUP_ID}

# LLM Configuration
AGVS4RTL_LLM_ENABLED=${LLM_ENABLED:-false}
AGVS4RTL_LLM_BASE_URL=${llm_base_url:-}
AGVS4RTL_LLM_API_KEY=${llm_api_key:-}
AGVS4RTL_LLM_MODEL=${llm_model:-}
AGVS4RTL_LLM_PROFILE=default

# Timeout settings (seconds)
VERIFY_SERVICE_TIMEOUT_SECONDS=${VERIFY_SERVICE_TIMEOUT_SECONDS:-240}
GEN_SERVICE_TIMEOUT_SECONDS=${GEN_SERVICE_TIMEOUT_SECONDS:-600}
AGVS4RTL_LLM_TIMEOUT_SECONDS=${AGVS4RTL_LLM_TIMEOUT_SECONDS:-300}
EOF

    # For each key in the template, check if it exists in .env
    # If not, append it from the template
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        key=$(echo "$key" | xargs)
        # Check if key already exists in .env (as a variable assignment, not comment)
        if ! grep -qE "^[[:space:]]*${key}[[:space:]]*=" .env 2>/dev/null; then
            echo "${key}=${value}" >> .env
        fi
    done < <(grep -E '^[A-Z_]' "$tmpfile")

    rm -f "$tmpfile"
}

if $GEN_ENV; then
    echo -e "${CYAN}[6/9] Generating .env...${NC}"
    generate_env
    echo -e "  ${GREEN}✓${NC} .env generated successfully"
elif ! $SKIP_TO_DOCKER; then
    # Merge mode — only add missing keys
    echo -e "${CYAN}[6/9] Merging .env...${NC}"
    merge_env
    echo -e "  ${GREEN}✓${NC} Missing keys added to .env"
else
    echo -e "${CYAN}[6/9] Using existing .env${NC}"
fi

# Ensure .env is sourced for docker-compose
set -a
source .env
set +a


# ╔══════════════════════════════════════════════╗
# ║  SECTION 8 — Build Docker images            ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[7/9] Building Docker images...${NC}"
if ! $DOCKER_COMPOSE build 2>&1; then
    echo -e "${RED}Docker build failed. Check the output above for errors.${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker images built successfully"


# ╔══════════════════════════════════════════════╗
# ║  SECTION 9 — Start services                 ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[8/9] Starting services...${NC}"
if ! $DOCKER_COMPOSE up -d 2>&1; then
    echo -e "${RED}Failed to start services. Check the output above for errors.${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Services started"


# ╔══════════════════════════════════════════════╗
# ║  SECTION 10 — Health verification           ║
# ╚══════════════════════════════════════════════╝
echo -e "${CYAN}[9/9] Waiting for services to be ready...${NC}"

MAX_ATTEMPTS=15
ATTEMPT=0
HEALTH_OK=false

while [[ $ATTEMPT -lt $MAX_ATTEMPTS ]]; do
    if curl -s --max-time 2 http://localhost:8001/health >/dev/null 2>&1; then
        HEALTH_OK=true
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 2
done

if $HEALTH_OK; then
    echo -e "  ${GREEN}✓${NC} Parser service is healthy"
else
    echo -e "  ${YELLOW}⚠ Could not verify health. Check docker compose logs parser${NC}"
fi


# ╔══════════════════════════════════════════════╗
# ║  SECTION 11 — Success message               ║
# ╚══════════════════════════════════════════════╝
echo ""
echo -e "${GREEN}"
echo "╔══════════════════════════════════════╗"
echo "║           Setup Complete!            ║"
echo "╠══════════════════════════════════════╣"
echo "║  API:  http://localhost:8001         ║"
echo "║  UI:   http://localhost:8002         ║"
echo "║                                      ║"
echo "║  Next: docker compose logs -f        ║"
echo "║        docker compose down           ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"
