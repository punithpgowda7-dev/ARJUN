#!/bin/bash

# Start OmniRoute gateway in the background
echo "Starting OmniRoute AI Gateway..."
npx omniroute &

# Wait a few seconds for OmniRoute to initialize on port 20128
sleep 5

# Start the Arjun bot
echo "Starting Arjun..."
python main.py
