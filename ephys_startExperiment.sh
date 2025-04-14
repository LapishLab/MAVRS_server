#!/bin/bash
cd $(dirname "$(readlink -f "$0")")

prefix="$(date +%Y-%m-%d_%H-%M-%S)_rat"

echo 'Enter session name:'
read -e -i "$prefix" session

echo 'creating MED-PC folder'
ssh lapishla@10.0.0.1 'mkdir \data\'$session'\med-pc_'$session

echo 'creating experiment folder on this PC'
mkdir "/mnt/c/data/$session"

echo 'creating Anymaze folder'
mkdir "/mnt/c/data/$session/anymaze_$session"

echo 'creating open-ephys folder'
mkdir "/mnt/c/data/$session/open-ephys_$session"

echo 'Hit enter when ready to start Pi recording'
read

echo "experiment started at $(date)"
cssh piCluster -a "python -u MAVRS_pi/startExperiment.py --session $session/pi-data_$session"
