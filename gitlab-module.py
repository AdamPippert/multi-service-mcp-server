# tools/gitlab_tool.py
from flask import Blueprint, request, jsonify, current_app
import requests

gitlab_routes = Blueprint('gitlab', __name__)

def handle_action(action, parameters):
    """Handle GitLab tool actions according to MCP standard"""
    action_handlers = {
        "listProjects": list_projects,
        "getProject": get_project,
        "searchProjects": search_projects,
        "getIssues": get_issues,
        "createIssue": create_issue,
        "getPipelines": get_pipelines
    }
    
    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}")
    
    return action_handlers[action](parameters)

def list_projects(parameters):
    """List all projects accessible by the authenticated user"""
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.get(f'{current_app.config["GITLAB_API_URL"]}/projects', headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

def get_project(parameters):
    """Get details for a specific project"""
    project_id = parameters.get('projectId')
    
    if not project_id:
        raise ValueError("Project ID parameter is required")
    
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.get(f'{current_app.config["GITLAB_API_URL"]}/projects/{project_id}', headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

def search_projects(parameters):
    """Search for projects on GitLab"""
    query = parameters.get('query')
    
    if not query:
        raise ValueError("Query parameter is required")
    
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.get(
        f'{current_app.config["GITLAB_API_URL"]}/search',
        params={'scope': 'projects', 'search': query},
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

def get_issues(parameters):
    """Get issues for a project"""
    project_id = parameters.get('projectId')
    state = parameters.get('state', 'opened')
    
    if not project_id:
        raise ValueError("Project ID parameter is required")
    
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.get(
        f'{current_app.config["GITLAB_API_URL"]}/projects/{project_id}/issues',
        params={'state': state},
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

def create_issue(parameters):
    """Create a new issue in a project"""
    project_id = parameters.get('projectId')
    title = parameters.get('title')
    description = parameters.get('description', '')
    
    if not project_id:
        raise ValueError("Project ID parameter is required")
    if not title:
        raise ValueError("Title parameter is required")
    
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.post(
        f'{current_app.config["GITLAB_API_URL"]}/projects/{project_id}/issues',
        json={'title': title, 'description': description},
        headers=headers
    )
    
    if response.status_code not in (201, 200):
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

def get_pipelines(parameters):
    """Get pipelines for a project"""
    project_id = parameters.get('projectId')
    
    if not project_id:
        raise ValueError("Project ID parameter is required")
    
    headers = {'Private-Token': current_app.config['GITLAB_TOKEN']}
    response = requests.get(
        f'{current_app.config["GITLAB_API_URL"]}/projects/{project_id}/pipelines',
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"GitLab API error: {response.json()}")
    
    return response.json()

# API routes for direct access (not through MCP gateway)
@gitlab_routes.route('/listProjects', methods=['GET'])
def api_list_projects():
    """API endpoint for listing projects"""
    try:
        result = list_projects({})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gitlab_routes.route('/getProject/<project_id>', methods=['GET'])
def api_get_project(project_id):
    """API endpoint for getting a specific project"""
    try:
        result = get_project({'projectId': project_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gitlab_routes.route('/searchProjects', methods=['GET'])
def api_search_projects():
    """API endpoint for searching projects"""
    try:
        query = request.args.get('query')
        result = search_projects({'query': query})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gitlab_routes.route('/getIssues/<project_id>', methods=['GET'])
def api_get_issues(project_id):
    """API endpoint for getting issues for a project"""
    try:
        state = request.args.get('state', 'opened')
        result = get_issues({'projectId': project_id, 'state': state})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gitlab_routes.route('/createIssue/<project_id>', methods=['POST'])
def api_create_issue(project_id):
    """API endpoint for creating a new issue"""
    try:
        data = request.get_json()
        parameters = {
            'projectId': project_id,
            'title': data.get('title'),
            'description': data.get('description', '')
        }
        result = create_issue(parameters)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gitlab_routes.route('/getPipelines/<project_id>', methods=['GET'])
def api_get_pipelines(project_id):
    """API endpoint for getting pipelines for a project"""
    try:
        result = get_pipelines({'projectId': project_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
