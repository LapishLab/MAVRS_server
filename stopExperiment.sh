#!/bin/bash

echo "stopping Pi recordings"
cssh piCluster -a "bash MAVRS_pi/stopExperiment.sh"

echo "moving med-PC data to archive"
REMOTE_USER="lapishla"
REMOTE_HOST="10.1.1.2"
REMOTE_TEMP="/mnt/c/med_NOW/"
REMOTE_ARCHIVE="/mnt/c/med_archive/"

CMD="find $REMOTE_TEMP -maxdepth 1 -mindepth 1 -exec mv {} $REMOTE_ARCHIVE  \;"
ssh "$REMOTE_USER@$REMOTE_HOST" $CMD