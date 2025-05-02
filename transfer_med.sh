#!/bin/bash

# Define variables
REMOTE_USER="lapishla"
REMOTE_HOST="10.1.1.2"
REMOTE_ARCHIVE="/mnt/c/med_archive/"
LOCAL_ARCHIVE="/home/lapishla/Desktop/piData/"

# Run rsync to copy files from remote to local
rsync --progress -h -a "$REMOTE_USER@$REMOTE_HOST:$REMOTE_ARCHIVE/" "$LOCAL_ARCHIVE/"

# Check if rsync was successful
if [ $? -eq 0 ]; then
    echo "Files copied successfully."
else
    echo "ERROR: Rsync failed"
fi

