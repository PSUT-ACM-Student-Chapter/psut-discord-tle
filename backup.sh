#!/bin/bash
BACKUP_DIR=~/db_backups
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Compress the databases into one file
tar -czvf $BACKUP_DIR/db_backup_$TIMESTAMP.tar.gz -C ~/psut-discord-tle/data/db .

# Optional: Keep only the last 7 days of backups
find $BACKUP_DIR -type f -mtime +7 -name "*.tar.gz" -delete
