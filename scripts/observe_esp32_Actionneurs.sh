#!/bin/bash
pwd | grep scripts
if [ $? -eq 0 ]
then
	cd ..
fi
pio run -e Actionneurs -t monitor
