#!/bin/bash
echo "copying data from  MED-PC"
rsync --progress -a 'lapishla@10.1.1.2:/mnt/c/data/' '/home/lapishla/Desktop/piData'
echo "MED-PC Sync completed: Hit enter to begin pi transfer"
read

echo "copying data from Pi"
cssh piCluster -a "bash MAVRS_pi/transferData.sh lapishla /home/lapishla/Desktop/piData"
