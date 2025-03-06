# tools/github_tool.py
from flask import Blueprint, request, jsonify, current_app
import requests

github_routes = Blueprint('github', __name__)

def handle_action(action, parameters):
    """Handle GitHub tool actions according to MCP standard"""
    action_handlers = {
        "listRepos": list_repos,
        "getRepo": get_repo,
        "searchRepos": search_repos,
        "getIssues": get_issues,
        "createIssue": create_issue
    }
    
    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}")
    
    return action_handlers[action](parameters)

def list_repos(parameters):
    """List repositories for a user or organization"""
    username = parameters.get('username')
    if not username:
        raise ValueError("Username parameter is required")
    
    headers = {'Authorization': f'token {current_app.config["GITHUB_TOKEN"]}'}
    response = requests.get(f'{current_app.config["GITHUB_API_URL"]}/users/{username}/repos', headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.json()}")
    
    return response.json()

def get_repo(parameters):
    """Get details for a specific repository"""
    owner = parameters.get('owner')
    repo = parameters.get('repo')
    
    if not owner or not repo:
        raise ValueError("Owner and repo parameters are required")
    
    headers = {'Authorization': f'token {current_app.config["GITHUB_TOKEN"]}'}
    response = requests.get(f'{current_app.config["GITHUB_API_URL"]}/repos/{owner}/{repo}', headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.json()}")
    
    return response.json()

def search_repos(parameters):
    """Search for repositories"""
    query = parameters.get('query')
    
    if not query:
        raise ValueError("Query parameter is required")
    
    headers = {'Authorization': f'token {current_app.config["GITHUB_TOKEN"]}'}
    response = requests.get(
        f'{current_app.config["GITHUB_API_URL"]}/search/repositories',
        params={'q': query},
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.json()}")
    
    return response.json()

def get_issues(parameters):
    """Get issues for a repository"""
    owner = parameters.get('owner')
    repo = parameters.get('repo')
    state = parameters.get('state', 'open')
    
    if not owner or not repo:
        raise ValueError("Owner and repo parameters are required")
    
    headers = {'Authorization': f'token {current_app.config["GITHUB_TOKEN"]}'}
    response = requests.get(
        f'{current_app.config["GITHUB_API_URL"]}/repos/{owner}/{repo}/issues',
        params={'state': state},
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.json()}")
    
    return response.json()

def create_issue(parameters):
    """Create a new issue in a repository"""
    owner = parameters.get('owner')
    repo = parameters.get('repo')
    title = parameters.get('title')
    body = parameters.get('body', '')
    
    if not owner or not repo:
        raise ValueError("Owner and repo parameters are required")
    if not title:
        raise ValueError("Title parameter is required")
    
    headers = {'Authorization': f'token {current_app.config["GITHUB_TOKEN"]}'}
    response = requests.post(
        f'{current_app.config["GITHUB_API_URL"]}/repos/{owner}/{repo}/issues',
        json={'title': title, 'body': body},
        headers=headers
    )
    
    if response.status_code not in (201, 200):
        raise Exception(f"GitHub API error: {response.json()}")
    
    return response.json()

# API routes for direct access (not through MCP gateway)
@github_routes.route('/listRepos', methods=['GET'])
def api_list_repos():
    """API endpoint for listing repositories"""
    try:
        username = request.args.get('username')
        result = list_repos({'username': username})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@github_routes.route('/getRepo/<owner>/<repo>', methods=['GET'])
def api_get_repo(owner, repo):
    """API endpoint for getting a specific repository"""
    try:
        result = get_repo({'owner': owner, 'repo': repo})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@github_routes.route('/searchRepos', methods=['GET'])
def api_search_repos():
    """API endpoint for searching repositories"""
    try:
        query = request.args.get('query')
        result = search_repos({'query': query})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@github_routes.route('/getIssues/<owner>/<repo>', methods=['GET'])
def api_get_issues(owner, repo):
    """API endpoint for getting issues for a repository"""
    try:
        state = request.args.get('state', 'open')
        result = get_issues({'owner': owner, 'repo': repo, 'state': state})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@github_routes.route('/createIssue/<owner>/<repo>', methods=['POST'])
def api_create_issue(owner, repo):
    """API endpoint for creating a new issue"""
    try:
        data = request.get_json()
        parameters = {
            'owner': owner,
            'repo': repo,
            'title': data.get('title'),
            'body': data.get('body', '')
        }
        result = create_issue(parameters)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400
