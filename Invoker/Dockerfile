# Use a base image
FROM ubuntu:22.04

WORKDIR  /invoker

# Install curl
RUN apt-get update \
 && apt-get install -y curl

# Copy the bash script into the container
COPY invoker.sh .

# Make the bash script executable
#RUN chmod +x /app/invoker.sh
RUN ["chmod", "+x", "invoker.sh"]

# Run the bash script through the shell
#CMD /app/invoker.sh
CMD ["bash", "./invoker.sh"]
