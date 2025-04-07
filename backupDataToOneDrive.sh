#!/bin/bash
echo "Uploading the piData folder to DataStar"
xfce4-terminal --hold -x bash -c 'rsync -av --progress /media/server/piData/ lapishla@datastar.psych.indianapolis.iu.edu:/research/pi_DD ; echo transfer complete'
