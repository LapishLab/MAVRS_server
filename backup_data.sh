#!/bin/bash
echo "Uploading the piData folder to DataStar"
rsync -ah --info=progress2 "/home/lapishla/Desktop/piData/" "lapishla@datastar.psych.indianapolis.iu.edu:/research/behavior_rooms/2CAP/"

if [ $? -eq 0 ]; then
    echo
    echo "---Transfer Complete---"
    echo "Data has been backed up to Datastar"
    echo "-----------------------"
    echo
else
    echo
    echo "---WARNING---"
    echo "Rsyncing to Datastar failed!"
    echo "-------------"
    echo
fi

read -p "Hit enter to close window"
