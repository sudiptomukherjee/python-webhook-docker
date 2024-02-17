#!/bin/bash

# Define thresholds for each app in megabytes
declare -A thresholds
thresholds["app1"]=500
thresholds["app2"]=700
thresholds["app3"]=600

# Define the URL of the webhook using the internal DNS name
WEBHOOK_URL="http://172.171.128.158/webhook"

# Loop through each app
for app in "${!thresholds[@]}"; do
    # Loop through each pod in your EKS cluster for the specific app
    for pod in $(kubectl get pods -l app=$app -o=name); do
        # Extract the pod name
        pod_name=$(echo $pod | cut -d'/' -f 2)

        # Loop through each container in the pod
        for container in $(kubectl get pods $pod_name -o=jsonpath='{.spec.containers[*].name}'); do
            # Get current memory usage for the container
            mem_usage=$(kubectl exec $pod_name -c $container -- df -m / | tail -n 1 | awk '{print $3}')

            # Get the threshold for the current app
            threshold=${thresholds[$app]}

            # Check if memory usage exceeds the threshold
            if [ $mem_usage -ge $threshold ]; then
                # Include container name, EKS cluster name, and container memory used in the curl command
                curl -X POST -d '{App: "'"$app"'", Pod: "'"$pod_name"'", Container: "'"$container"'", Memory Used: "'"$mem_usage"'" MB"}' $WEBHOOK_URL
            fi
        done
    done
done
