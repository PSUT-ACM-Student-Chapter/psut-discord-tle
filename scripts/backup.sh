#!/bin/bash
BACKUP_DIR=~/db_backups
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 1. Create the compressed backup
tar -czvf $BACKUP_DIR/db_backup_$TIMESTAMP.tar.gz -C ~/psut-discord-tle/data/db .

# 2. DELETE OLD BACKUPS (Safety Step)
# This deletes any backups older than 7 days so your disk doesn't fill up.
find $BACKUP_DIR -type f -mtime +7 -name "*.tar.gz" -delete
