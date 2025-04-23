#!/bin/bash
echo "Uploading the piData folder to DataStar"
rsync -a --progress "/home/lapishla/Desktop/piData/" "lapishla@datastar.psych.indianapolis.iu.edu:/research/behavior_rooms/2CAP/"
echo "Transfer complete: Hit enter to close window"
read
