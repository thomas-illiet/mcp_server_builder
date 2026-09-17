#!/bin/bash

# ==============================
# Configuration
# ==============================

LOGIN="administrator"
PASSWORD="Rinvophyoarnyovjurc5!"
HOST="192.168.1.58"

SOURCE="/volume1/homes"
DESTINATION="/volume1/homes"

# ==============================
# Execution
# ==============================

export RSYNC_PASSWORD="$PASSWORD"

rsync -avz \
    --delete \
    "$SOURCE" \
    "${LOGIN}@${HOST}:${DESTINATION}"

RET=$?

unset RSYNC_PASSWORD

if [ $RET -eq 0 ]; then
    echo "Rsync completed successfully."
else
    echo "ERROR: Rsync failed with code $RET."
fi

exit $RET
