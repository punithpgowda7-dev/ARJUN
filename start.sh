#!/bin/bash

# Start OmniRoute gateway in the background and log output
echo "Starting OmniRoute AI Gateway..."
touch omniroute.log
npx -y omniroute > omniroute.log 2>&1 &

# Wait 2 seconds and print initial startup logs
sleep 2
cat omniroute.log

# Continuously print the proxy logs to Render's console
tail -f omniroute.log &

# Wait 10 seconds for OmniRoute to initialize on port 20128 (free tier can be slow)
sleep 10

# Test if the LLM proxy is actually listening!
echo "Testing OmniRoute connection..."
curl -v http://127.0.0.1:20128/v1/models || echo "CURL FAILED"

# Start the Arjun bot
echo "Starting Arjun..."
python main.py
