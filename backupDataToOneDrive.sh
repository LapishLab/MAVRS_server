#!/bin/bash
echo "Uploading the piData folder to David's Onerive"
xfce4-terminal --hold -x bash -c 'rclone copy /home/server/Desktop/piData OneDrive_David:/piData_backup --metadata --human-readable -v ; echo transfer complete'
