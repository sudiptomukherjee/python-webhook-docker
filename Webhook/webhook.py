from flask import Flask, request, jsonify
import yaml
import requests
from github import Github
from github.GithubException import GithubException
import os
from datetime import datetime
import random
from termcolor import colored
from base64 import b64encode
import re
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

app = Flask(__name__)
# Load environment variables from .env file (GITHUB_TOKEN="github token value")
load_dotenv()
# Read GitHub token from environment variables
github_token = os.getenv("GITHUB_TOKEN")

# GitHub repository details
github_repo_owner = 'sudiptomukherjee'
github_repo_name = 'demo-webhook'
base_branch = 'main' # or master ?
reviewers = ['user1','user2']
file_path = f'deployment.yaml' #webhook/deployment.yaml ?

def log_error(error_message):
    print(colored(f"Error: {error_message}", "red"))

@app.route('/webhook', methods=['POST'])
def webhook():
    try:        
        # Check if GitHub token is available
        if github_token is None:
            raise ValueError("GITHUB_TOKEN was not found")
        # Parse JSON payload
        #sample payload : curl -X POST -H "Content-Type: application/json" -d '{"maxMemory": 512, "appName": "wsc","environment": "staging","region": "all-regions"}' http://localhost:5000/webhook
        payload = request.get_json()

        # Null checks for payload parsing
        #if not payload or 'maxMemory' not in payload or 'appName' not in payload or 'environment' not in payload or 'region' not in payload:
        if 'maxMemory' not in payload:
            raise Exception("Invalid payload format. Required field: maxMemory")

        # Extract values from payload
        max_memory = payload.get('maxMemory')
        #max_memory = payload.get('maxCPU')
        #app_name = payload.get('appName')
        #environment = payload.get('environment')
        #region = payload.get('region')

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
                    # Create a pull request with two reviewers
                    pr_title = f'Update Memory Limit and Request to {max_memory}'
                    create_pull_request(branch_name, pr_title, reviewers)
                    return jsonify({"status": "success"})

    except Exception as e:
        log_error(str(e))
        return jsonify({"status": "error", "message": str(e)})    

    #return jsonify({"status": "success"})

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
        raise Exception(f"Error extracting memory limit: {str(e)}")

def connect_to_github(api_url, headers):
    try:
        print("Connecting to Github...")
        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            print(colored("Connected to GitHub successfully.", "green"))
            return response
        elif response.status_code == 403:
            rate_limit_info = {
                'limit': response.headers.get('X-RateLimit-Limit'),
                'remaining': response.headers.get('X-RateLimit-Remaining'),
                'reset_time': response.headers.get('X-RateLimit-Reset'),
            }
            raise Exception(f"GitHub API rate limit exceeded. Rate limit details: {rate_limit_info}")
        else:
            raise Exception(f"Failed to connect to GitHub. Status code: {response.status_code}")

    except Exception as e:
        raise Exception(f"Error connecting to GitHub: {str(e)}")

def read_github_file(file_path):
    try:
        print("Reading current limits from Github...")        
        # GitHub API details for reading a specific file
        github_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/contents/{file_path}'

        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }

        print(colored(f"Reading file from GitHub: {file_path}", "blue"))

        # Connect to GitHub
        response = connect_to_github(github_api_url, headers)

        # Decode base64 content and load YAML data
        file_content = yaml.safe_load(requests.get(response.json()['download_url']).text)

        # Extract memory limit from the deployment manifest
        memory_limit = extract_memory_limit(file_content)

        print(colored(f"Memory Limit from Deployment Manifest: {memory_limit}", "green"))

        return {"status": "success", "memory_limit": memory_limit}

    except Exception as e:
        log_error(f"Error reading GitHub file: {str(e)}")
        return {"status": "error", "message": str(e)}

def create_branch(file_path, branch_name):
    try:
        print("Creating new branch in Github...")
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
            print(colored(f"Branch '{branch_name}' created successfully.", "green"))
            return True
        else:
            raise Exception(f"Failed to create branch '{branch_name}'. Status code: {response.status_code}")

    except Exception as e:
        log_error(f"Error creating branch: {str(e)}")
        return False

def fetch_latest_changes(branch_name):
    try:
        print("Fetching latest from Github...")
        fetch_api_url = f'https://api.github.com/repos/{github_repo_owner}/{github_repo_name}/git/refs/heads/{branch_name}'
        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }
        response = connect_to_github(fetch_api_url, headers)
        return response.json()['object']['sha']
    except Exception as e:
        log_error(f"Error fetching latest changes: {str(e)}")
        return None

def update_yaml_manifest(file_path, new_memory_limit, branch_name):
    try:
        print("Updating yaml manifest in Github...")
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
        commit_message = f"Update memory limit to {new_memory_limit}Mi"

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
            print(colored(f"YAML file in branch '{branch_name}' updated successfully.", "green"))
            return True
        else:
            raise Exception(f"Failed to update YAML file in branch '{branch_name}'. Status code: {commit_response.status_code}")

    except Exception as e:
        log_error(f"Error updating YAML manifest: {str(e)}")
        return False


def create_pull_request(branch_name, pr_title, reviewers):
    try:
        print("Creating PR in Github...")
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
            'body': f'Pull request to update memory limit for {branch_name}',
            'maintainer_can_modify': True,
            'draft': False,
            'reviewers': reviewers,
        }
        response = requests.post(pr_api_url, headers=headers, json=payload)

        if response.status_code == 201:
            pr_number = response.json()['number']
            print(colored(f"Pull request '{pr_title}' created successfully.", "green"))
        else:
            raise Exception(f"Failed to create pull request. Status code: {response.status_code}")

    except Exception as e:
        log_error(f"Error creating pull request: {str(e)}")


def get_github_token_from_secrets_manager_aws(secret_name):    
    region_name = "eu-west-1"
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        secret = get_secret_value_response['SecretString']
        return secret
    except ClientError as e:
        raise e
        return None

if __name__ == '__main__':
    app.run(port=5000)