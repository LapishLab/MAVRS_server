#!/bin/bash

# Define variables
REMOTE_USER="lapishla"
REMOTE_HOST="10.1.1.2"
REMOTE_DIR="/mnt/c/data/"
LOCAL_DIR="/home/lapishla/Desktop/piData"
ARCHIVE_DIR="/mnt/c/data_archive/"

# Run rsync to copy files from remote to local
rsync --progress -h -a "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR" "$LOCAL_DIR"

# Check if rsync was successful
if [ $? -eq 0 ]; then
    echo "Files copied successfully. Moving original files to $ARCHIVE_DIR"
    CMD="find $REMOTE_DIR -maxdepth 1 -mindepth 1 -exec mv {} $ARCHIVE_DIR  \;"
    ssh "$REMOTE_USER@$REMOTE_HOST" $CMD
else
    echo "ERROR: Rsync failed"
fi

