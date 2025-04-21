#!/bin/bash
cd $(dirname "$(readlink -f "$0")")

echo 'Enter experiment name:'
read -e exp

echo 'Enter group number:'
read -e group

time="$(date +%Y-%m-%d_%H-%M-%S)"

suggested="${time}_${exp}_group${group}"

echo 'Verify correct name, then hit enter to start recording:'
read -e -i "$suggested" session

echo "started recording ${session}"
cssh piCluster -a "python -u MAVRS_pi/startExperiment.py --session ${session}"
