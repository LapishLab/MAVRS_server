#!/bin/bash
#cssh piCluster -a "bash MAVRS_pi/transferData.sh server /home/server/Desktop/piData"

echo "copying data from  MED-PC"
rsync --progress -a 'dlinsenb@10.0.0.3:/data/' '/mnt/c/data/'

echo "copying data from Pi"
rsync --progress -a 'pi@10.1.1.2:~/MAVRS_pi/data/' '/mnt/c/data/'
