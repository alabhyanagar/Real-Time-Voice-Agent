#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# infra/backup.sh
# Production backup script for PostgreSQL, Redis, and ChromaDB data
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TARGET_DIR="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${TARGET_DIR}"

echo "==> Starting Voice Agent backup at ${TIMESTAMP}"

# 1. PostgreSQL backup
echo "--> Dumping PostgreSQL database..."
docker exec voice-postgres pg_dump -U "${POSTGRES_USER:-voiceuser}" "${POSTGRES_DB:-voiceagent}" > "${TARGET_DIR}/postgres_backup.sql"

# 2. Redis backup
echo "--> Triggering Redis snapshot..."
docker exec voice-redis redis-cli BGSAVE
sleep 2
docker cp voice-redis:/data/dump.rdb "${TARGET_DIR}/redis_dump.rdb" || true

# 3. ChromaDB vector archive
echo "--> Archiving ChromaDB vector storage..."
docker run --rm --volumes-from voice-chromadb -v "${TARGET_DIR}:/backup" alpine tar czf /backup/chroma_backup.tar.gz /chroma/chroma || true

# Compress all components into a single dated archive
tar -czf "${BACKUP_DIR}/voice_agent_backup_${TIMESTAMP}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
rm -rf "${TARGET_DIR}"

echo "==> Backup completed successfully: ${BACKUP_DIR}/voice_agent_backup_${TIMESTAMP}.tar.gz"

