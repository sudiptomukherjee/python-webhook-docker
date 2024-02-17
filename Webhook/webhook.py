from flask import Flask, request, jsonify
import yaml
import requests
from github import Github
from github.GithubException import GithubException
import os
from datetime import datetime
from base64 import b64encode
import re
from dotenv import load_dotenv
from applicationinsights import TelemetryClient
import traceback
from logging import StreamHandler
import sys
import logging

app = Flask(__name__)
# Load and read values from kubernetes configmaps and secrets
load_dotenv()
github_token = os.getenv("GITHUB_TOKEN")
github_repo_owner = os.getenv("GITHUB_REPO_OWNER")
github_repo_name = os.getenv("GITHUB_REPO_NAME")
file_path = os.getenv("FILE_PATH")
appinsight_instrumentation_key = os.getenv("INSTRUMENTATION_KEY")
base_branch = os.getenv("BASE_BRANCH")

# Write logs to stdout
handler = StreamHandler(sys.stdout)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)
app.logger.propagate = True
def log_event_stdout(message):
    current_datetime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    app.logger.info(f'{message} - {current_datetime}')

# Send telemtery to azure app insights
telemetry_client = TelemetryClient(appinsight_instrumentation_key)
def log_event_azure(message):
    current_datetime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    telemetry_client.track_event(f'{message} - {current_datetime}')   
    telemetry_client.flush()
def log_exception_azure():
    telemetry_client.track_exception()
    telemetry_client.flush()
def log_success_azure(message):
    current_datetime = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    telemetry_client.track_trace(f'{message} - {current_datetime}')   
    telemetry_client.flush()

# Logging messages
msg_app_title = "Alert listener Webhook"
msg_missing_token = f"{msg_app_title} - GITHUB_TOKEN was not found"
msg_invalid_payload = f"{msg_app_title} - Invalid payload format. Missing field - maxMemory"
msg_extract_error = f"{msg_app_title} - Error extracting memory limit from GitHub"
msg_rate_limit_error = f"{msg_app_title} - GitHub API rate limit exceeded. Rate limit details"
msg_connection_error = f"{msg_app_title} - Error connecting to GitHub"
msg_read_error = f"{msg_app_title} - Error reading file from GitHub"
msg_branch_success = f"{msg_app_title} - Successfully created branch in GitHub"
msg_branch_error = f"{msg_app_title} - Error creating branch in GitHub"
msg_get_latest_error = f"{msg_app_title} - Error fetching latest files from GitHub"
msg_update_success = f"{msg_app_title} - YAML manifest file updated successfully in GitHub"
msg_update_error = f"{msg_app_title} - Error updating YAML manifest file in GitHub"
msg_pr_title = f"{msg_app_title} - PR for updating memory limit and request"
msg_pr_success = f"{msg_app_title} - Successfully PR created in GitHub"
msg_pr_error = f"{msg_app_title} - Error creating PR in GitHub"
msg_error = f"{msg_app_title} - An error has occurred"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:        
        # proceed only if token is present
        if github_token is None:
            log_event_azure(msg_missing_token)
            log_event_stdout(msg_missing_token)
            raise ValueError(msg_missing_token)
        # Parse JSON payload
        payload = request.get_json()

        # Null checks for payload parsing
        #if not payload or 'maxMemory' not in payload or 'appName' not in payload or 'environment' not in payload or 'region' not in payload:
        if 'maxMemory' not in payload:
            log_event_azure(msg_invalid_payload)
            log_event_stdout(msg_invalid_payload)
            raise Exception(msg_invalid_payload)

        # Extract values from payload
        max_memory = payload.get('maxMemory')

        # Construct file_path based on input payload
        #file_path = f'platform/{environment}/{region}/default/{app_name}.yaml'

        # Read current limits
        result = read_github_file(file_path)

        if result.get("status") == "success":
            # Calculate new memory limit by raising max_memory by 25%
            new_memory_limit = int(max_memory * 1.25)

            # Create a new branch
            branch_name = f'update-memory-limit-{datetime.now().strftime("%Y%m%d%H%M%S")}'
            if create_branch(file_path, branch_name):
                # Update YAML manifest in the new branch
                if update_yaml_manifest(file_path, new_memory_limit, branch_name):
                    # Create a pull request
                    pr_title = msg_pr_title
                    create_pull_request(branch_name, pr_title)
                    return jsonify({"status": "success"})

    except Exception as e:
        log_event_stdout(f"{msg_error} - {traceback.format_exc()}")
        log_event_azure(f"{msg_error} - {traceback.format_exc()}")
        log_exception_azure()
        return jsonify({"status": "error", "message": str(e)})

def extract_memory_limit(deployment_manifest):
    try:
        spec = deployment_manifest.get('spec', {})
        values = spec.get('values', {})
        resources = values.get('resources', {})

        if 'limits' in resources and 'memory' in resources['limits']:
            memory_limit = resources['limits']['memory']
            return memory_limit

        return 'Not found'

    except Exception as e:
        log_event_azure(f"{msg_extract_error} - {traceback.format_exc()}")
        log_exception_azure()
        log_event_stdout(msg_extract_error)
        raise Exception(f"{msg_extract_error}: {str(e)}")

def connect_to_github(api_url, headers):
    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            return response
        elif response.status_code == 403:
            rate_limit_info = {
                'limit': response.headers.get('X-RateLimit-Limit'),
                'remaining': response.headers.get('X-RateLimit-Remaining'),
                'reset_time': response.headers.get('X-RateLimit-Reset'),
            }            
            raise Exception(f"{msg_rate_limit_error}: {rate_limit_info}")
        else:
            raise Exception(f"{msg_connection_error}. Status code: {response.status_code}")

    except Exception as e:
        log_event_stdout(msg_connection_error)
        log_event_azure(f"{msg_connection_error} - {traceback.format_exc()}")
        log_exception_azure()
        raise Exception(f"{msg_connection_error} : {str(e)}")

def read_github_file(file_path):
    try:
        # GitHub API details for reading a specific file
        github_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/contents/{file_path}'

        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }

        # Connect to GitHub
        response = connect_to_github(github_api_url, headers)
        # Decode base64 content and load YAML data
        file_content = yaml.safe_load(requests.get(response.json()['download_url']).text)
        # Extract memory limit from the deployment manifest
        memory_limit = extract_memory_limit(file_content)
        return {"status": "success", "memory_limit": memory_limit}

    except Exception as e:
        log_event_stdout(msg_read_error)
        log_event_azure(f"{msg_read_error} - {traceback.format_exc()}")
        log_exception_azure()
        return {"status": "error", "message": str(e)}

def create_branch(file_path, branch_name):
    try:
        # GitHub API details to get the latest SHA of the base branch
        base_branch_sha_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs/heads/{base_branch}'
        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }

        # Get the latest SHA of the base branch
        base_branch_response = connect_to_github(base_branch_sha_url, headers)
        base_branch_sha = base_branch_response.json()['object']['sha']

        # Create a new branch using the latest SHA of the base branch
        branch_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs'
        payload = {
            'ref': f'refs/heads/{branch_name}',
            'sha': base_branch_sha
        }
        response = requests.post(branch_api_url, headers=headers, json=payload)

        if response.status_code == 201:
            log_event_stdout(msg_branch_success)
            log_event_azure(msg_branch_success)                        
            return True
        else:
            log_event_stdout(msg_branch_error)
            log_event_azure(f"{msg_branch_error}. Status code - {response.status_code}")
            raise Exception(f"{msg_branch_error}. Status code: {response.status_code}")

    except Exception as e:
        log_event_stdout("Error creating branch")
        log_event_azure(f"Error creating branch - {traceback.format_exc()}")  
        log_exception_azure()      
        return False

def fetch_latest_changes(branch_name):
    try:
        fetch_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs/heads/{branch_name}'
        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }
        response = connect_to_github(fetch_api_url, headers)
        return response.json()['object']['sha']
    except Exception as e:
        log_event_stdout(msg_get_latest_error)
        log_event_azure(f"{msg_get_latest_error} - {traceback.format_exc()}")  
        log_exception_azure()      
        return None

def update_yaml_manifest(file_path, new_memory_limit, branch_name):
    try:
        # Fetch the latest changes
        latest_commit_sha = fetch_latest_changes(branch_name)

        if latest_commit_sha is None:
            return False

        # GitHub API details for updating a file in a branch
        update_file_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/contents/{file_path}'

        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }

        # Connect to GitHub
        response = connect_to_github(update_file_api_url, headers)

        # Get the current file SHA
        file_sha = response.json()['sha']

        # Read the current file content
        current_content = requests.get(response.json()['download_url']).text

        # Decode base64 content and load YAML data
        lines = current_content.split('\n')

        # Search for lines containing memory limits and update them
        for i, line in enumerate(lines):
            if re.search(r'\s*memory:\s*"\d+Mi"', line):
                lines[i] = re.sub(r'("\d+)Mi"', f'"{new_memory_limit}Mi"', line)

        # Updated content
        updated_content = '\n'.join(lines)

        # Encode the updated content to base64
        updated_base64_content = b64encode(updated_content.encode('utf-8')).decode('utf-8')

        # Commit message
        commit_message = f"{msg_pr_title} - {new_memory_limit}Mi"

        # Create a commit with the updated content
        commit_payload = {
            'message': commit_message,
            'content': updated_base64_content,
            'sha': file_sha,
            'branch': branch_name,
            'parents': [latest_commit_sha]
        }
        commit_response = requests.put(update_file_api_url, headers=headers, json=commit_payload)

        if commit_response.status_code == 200:
            log_event_stdout(msg_update_success)
            log_event_azure(msg_update_success)
            return True
        else:
            log_event_stdout(msg_update_error)
            log_event_azure(msg_update_error)
            raise Exception(f"{msg_update_error} '{branch_name}'. Status code: {commit_response.status_code}")

    except Exception as e:
        log_event_stdout(msg_update_error)
        log_event_azure(f"{msg_update_error} - {traceback.format_exc()}")
        log_exception_azure()
        return False


def create_pull_request(branch_name, pr_title):
    try:
        #GitHub API details for creating a pull request
        pr_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/pulls'

        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }

        # Base branch SHA
        base_branch_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs/heads/{base_branch}'
        base_branch_response = connect_to_github(base_branch_api_url, headers)
        base_branch_sha = base_branch_response.json()['object']['sha']

        # Branch SHA
        branch_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs/heads/{branch_name}'
        branch_response = connect_to_github(branch_api_url, headers)
        branch_sha = branch_response.json()['object']['sha']

        # Create a pull request
        payload = {
            'title': pr_title,
            'head': branch_name,
            'base': base_branch,
            'body': msg_pr_title,
            'maintainer_can_modify': True,
            'draft': False,
        }
        response = requests.post(pr_api_url, headers=headers, json=payload)

        if response.status_code == 201:
            pr_number = response.json()['number']
            log_event_stdout(msg_pr_success)
            log_success_azure(msg_pr_success)
        else:
            log_event_stdout(msg_pr_error)
            log_event_azure(f"{msg_pr_error} - {traceback.format_exc()}")
            raise Exception(f"{msg_pr_error}. Status code: {response.status_code}")

    except Exception as e:
        log_event_stdout(msg_pr_error)
        log_event_azure(f"{msg_pr_error} - {traceback.format_exc()}")
        log_exception_azure()

if __name__ == '__main__':
    app.run(port=5000)