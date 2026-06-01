#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# BCETD PostgreSQL Backup Script
# Member 4 Deliverable
#
# Usage: ./backup_database.sh
# Cron:  0 2 * * * /path/to/backup_database.sh >> /var/log/bcetd_backup.log 2>&1
#
# Creates daily compressed backups and removes backups older than 30 days
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# Configuration (override via environment)
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-chatbot_stats}"
DB_USER="${POSTGRES_USER:-chatbot_user}"
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Derived values
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/bcetd_${DB_NAME}_${TIMESTAMP}.sql.gz"

echo "═══════════════════════════════════════════════════"
echo "  BCETD Database Backup"
echo "  Time:   $(date)"
echo "  Target: ${BACKUP_FILE}"
echo "═══════════════════════════════════════════════════"

# Create backup directory if needed
mkdir -p "${BACKUP_DIR}"

# Perform backup
echo "[1/3] Creating backup..."
pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-owner \
    --no-privileges \
    --if-exists \
    --clean \
    --create \
    | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "      Backup created: ${BACKUP_SIZE}"

# Verify backup integrity
echo "[2/3] Verifying backup..."
if gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    echo "      Backup integrity: OK"
else
    echo "      ERROR: Backup file is corrupted!"
    exit 1
fi

# Clean old backups
echo "[3/3] Cleaning backups older than ${RETENTION_DAYS} days..."
DELETED=$(find "${BACKUP_DIR}" -name "bcetd_*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
echo "      Removed ${DELETED} old backup(s)"

# Summary
TOTAL_BACKUPS=$(find "${BACKUP_DIR}" -name "bcetd_*.sql.gz" | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
echo ""
echo "  Backup complete."
echo "  Total backups: ${TOTAL_BACKUPS}"
echo "  Total size:    ${TOTAL_SIZE}"
echo "═══════════════════════════════════════════════════"
