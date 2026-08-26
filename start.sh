#!/bin/bash

# Start OmniRoute gateway in the background and log output
echo "Starting OmniRoute AI Gateway..."
omniroute > omniroute.log 2>&1 &

# Wait 10 seconds for OmniRoute to initialize on port 20128 (free tier can be slow)
sleep 10

# Start the Arjun bot
echo "Starting Arjun..."
python main.py
