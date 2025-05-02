#!/bin/bash
cd $(dirname "$(readlink -f "$0")")

echo "setting clock time on Pis"
./setTime.sh
echo "reporting disk space on Pis"
./reportDiskSpace.sh

echo 'Enter experiment name:'
read -e exp

echo 'Enter group number:'
read -e group

time="$(date +%Y-%m-%d_%H-%M-%S)"

suggested="${time}_${exp}_group${group}"

echo 'Verify correct name, then hit enter'
read -e -i "$suggested" session

echo 'creating MED-PC folder'
REMOTE_USER="lapishla"
REMOTE_HOST="10.1.1.2"
REMOTE_TEMP="/mnt/c/med_NOW/"

CMD="mkdir -p $REMOTE_TEMP/$session/med-pc_$session"
ssh "$REMOTE_USER@$REMOTE_HOST" $CMD

echo 'Hit enter when ready to start Pi recording'
read

echo "started recording ${session}"
cssh piCluster -a "python -u MAVRS_pi/startExperiment.py --session $session/pi-data_$session"