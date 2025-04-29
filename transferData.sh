#!/bin/bash
cd $(dirname "$(readlink -f "$0")")

echo "copying data from  MED-PC"
./transfer_med.sh

echo "Hit enter to begin pi transfer"
read

echo "copying data from Pi"
cssh piCluster -a "bash MAVRS_pi/transferData.sh lapishla /home/lapishla/Desktop/piData"
