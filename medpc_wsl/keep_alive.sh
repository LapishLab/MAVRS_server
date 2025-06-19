#!/bin/bash

echo "starting tmux"
tmux new -d -s keep_alive

echo "hit enter to close window. WSL should keep running in the background."
read
