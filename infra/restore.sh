#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# infra/restore.sh
# Production restore script for PostgreSQL, Redis, and ChromaDB data
# ---------------------------------------------------------------------------
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path-to-backup-tar.gz>"
    exit 1
fi

ARCHIVE_PATH="$1"
RESTORE_TMP="./backups/tmp_restore"

if [ ! -f "${ARCHIVE_PATH}" ]; then
    echo "Error: Archive file not found at ${ARCHIVE_PATH}"
    exit 1
fi

echo "==> Restoring Voice Agent data from ${ARCHIVE_PATH}"
mkdir -p "${RESTORE_TMP}"
tar -xzf "${ARCHIVE_PATH}" -C "${RESTORE_TMP}"

BACKUP_SUBDIR=$(find "${RESTORE_TMP}" -mindepth 1 -maxdepth 1 -type d | head -n 1)

# 1. PostgreSQL restore
if [ -f "${BACKUP_SUBDIR}/postgres_backup.sql" ]; then
    echo "--> Restoring PostgreSQL database..."
    cat "${BACKUP_SUBDIR}/postgres_backup.sql" | docker exec -i voice-postgres psql -U "${POSTGRES_USER:-voiceuser}" -d "${POSTGRES_DB:-voiceagent}"
fi

# 2. Redis restore
if [ -f "${BACKUP_SUBDIR}/redis_dump.rdb" ]; then
    echo "--> Restoring Redis snapshot..."
    docker cp "${BACKUP_SUBDIR}/redis_dump.rdb" voice-redis:/data/dump.rdb
    docker restart voice-redis
fi

# 3. ChromaDB restore
if [ -f "${BACKUP_SUBDIR}/chroma_backup.tar.gz" ]; then
    echo "--> Restoring ChromaDB vectors..."
    docker run --rm --volumes-from voice-chromadb -v "${BACKUP_SUBDIR}:/backup" alpine tar xzf /backup/chroma_backup.tar.gz -C /
    docker restart voice-chromadb
fi

rm -rf "${RESTORE_TMP}"
echo "==> Restore completed successfully."

