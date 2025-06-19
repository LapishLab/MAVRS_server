#!/bin/bash
echo "copying data from  MED-PC"
rsync --progress -a 'lapishla@10.0.0.1:/data/' '/mnt/c/data/'

echo "copying data from Pi"
rsync --progress -a 'pi@10.0.0.2:~/MAVRS_pi/data/' '/mnt/c/data/'
