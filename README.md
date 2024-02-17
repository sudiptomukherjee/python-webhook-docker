
Problem :
Customer has 20+ apps running in AKS cluster with memory and CPU limits set.
Since the deployment is in early days, we’ve monitoring data only for about 5/6 months. Therefore, we’re yet to get a reliable trend as to what should be the value for memory/CPU for each app.
As a result, most pods were crashing frequently because of memory / CPU reaching the limits defined.

Why is that a big deal since Kubernetes is self-healing by nature?
When a pod crashes, Kubernetes creates a new Pod automatically, but it takes a little time for scheduling the pod, this may cause a small outage. This is not desirable for critical apps. This may also impact SLO, and in turn, SLA.

Solution:
- One word answer - Automation!
- When an app nears its threshold, monitoring system (New Relic, in this case) raises an alert and calls my Python webhook by sending a POST request with JSON payload containing app information and memory / CPU consumption.
- Developed a Python webhook that:
	. listens to incoming HTTP POST request from monitoring systems.
	. extracts the data (app_name, max_memory and max_cpu) from JSON payload.
	. connects to github repo (OAuth 2.0)
	. updates the kubernetes deployment manifest by bumping up memory and CPU limits.
	. creates a pull request.
	. applies the updated manifest automatically through GitOps (FluxCD).
- This makes the app in question, ready to serve increased demand without any human intervention

Design:
. Monitoring system (New Relic) invokes the webhook when an app nears (90%) of its threshold.
. Python flask app reads the data from payload, connects to github through OAuth 2.0 and updates the deployment.yaml file by raising memory/CPU limits to handle increased demand.
. The app also sends Telemetry to Azure App Insights for analytics and troubleshooting.

Deployment:
. The app is packaged (Docker) with all its dependencies and the image is pushed into Azure Container Registry (ACR).
. The image is pulled by Azure Kubernetes Services (AKS) Cluster which exposes the app through a LoadBalancer service to serve HTTP traffic.
. Secret (Github token) is served by Kubernetes Secret.
. All config values (Github repo name, Azure App Insights Instrumentation Key etc.) are sourced from Kubernetes ConfigMap – which means the app will work on any environment just by changing these values.

Networking and Security:
. Traffic from outside world is served by Istio Ingress Gateway that handles tasks like authentication, SSL offloading, retry limits etc. and forwards the traffic to Istio virtual service, which, in turn exposes the app running inside Kubernetes pods.
. In other words, the pods are not exposed outside the cluster, providing granular traffic management and security.
. Istio encrypts all communication between services through mTLS.
. All secrets are securely managed and served through Kubernetes Secret.

Observability:
. The webhook logs events, traces and exceptions to App Insights.
. Prometheus has been deployed and configured to scrape all necessary metrics and traces.
. Istio sends its own metrics and logs to Prometheus as well.
. All the logs collected can be viewed through Kiali and Grafana.

![image](https://github.com/sudiptomukherjee/python-webhook-docker/assets/12342105/9ccb2f24-532e-45c7-ae83-c0e8a9e77890)
