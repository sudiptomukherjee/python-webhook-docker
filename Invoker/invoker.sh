#!/bin/bash

# Define the URL of the webhook using the internal DNS name
#WEBHOOK_URL="http://webhook-service.default.svc.cluster.local/webhook"
WEBHOOK_URL="http://172.171.128.158/webhook"

# Define the JSON payload to send
JSON_PAYLOAD='{"maxMemory": 300}'

# Infinite loop to keep sending requests
while true; do
    # Execute the curl command to invoke the webhook
    curl -X POST -H "Content-Type: application/json" -d "${JSON_PAYLOAD}" "${WEBHOOK_URL}"
    
    # Sleep for X seconds before the next iteration
    sleep 5
done
