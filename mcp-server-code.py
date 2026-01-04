# Model Context Protocol (MCP) Server - Main Application
# project structure:
# mcp_server/
# ├── app.py
# ├── config.py
# ├── tools/
# │   ├── __init__.py
# │   ├── github_tool.py
# │   ├── gitlab_tool.py
# │   ├── gmaps_tool.py
# │   ├── memory_tool.py
# │   └── puppeteer_tool.py
# ├── tiered_memory/
# │   ├── __init__.py
# │   ├── models.py
# │   ├── tiers.py
# │   ├── engine.py
# │   ├── config.py
# │   └── mcp_interface.py
# ├── static/
# └── templates/

# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from config import Config
from tools.github_tool import github_routes
from tools.gitlab_tool import gitlab_routes
from tools.gmaps_tool import gmaps_routes
from tools.memory_tool import memory_routes
from tools.puppeteer_tool import puppeteer_routes
from tiered_memory.mcp_interface import tiered_memory_routes

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

# Register tool routes
app.register_blueprint(github_routes, url_prefix='/tool/github')
app.register_blueprint(gitlab_routes, url_prefix='/tool/gitlab')
app.register_blueprint(gmaps_routes, url_prefix='/tool/gmaps')
app.register_blueprint(memory_routes, url_prefix='/tool/memory')
app.register_blueprint(puppeteer_routes, url_prefix='/tool/puppeteer')

# Register tiered memory routes
app.register_blueprint(tiered_memory_routes, url_prefix='/tool/tiered_memory')

# MCP Gateway endpoint
@app.route('/mcp/gateway', methods=['POST'])
def mcp_gateway():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    
    # Parse the MCP request
    tool_name = data.get('tool')
    action = data.get('action')
    parameters = data.get('parameters', {})
    
    # Check for required fields
    if not tool_name:
        return jsonify({"error": "Tool name is required"}), 400
    if not action:
        return jsonify({"error": "Action is required"}), 400
    
    # Route to the appropriate tool
    try:
        # Construct the tool endpoint URL
        tool_url = f"/tool/{tool_name}/{action}"
        
        # Forward the request to the tool handler
        # In a real implementation, you'd use Flask's test_client or requests library
        # But for this demo, we'll simulate the routing
        if tool_name == "github":
            from tools.github_tool import handle_action
            result = handle_action(action, parameters)
        elif tool_name == "gitlab":
            from tools.gitlab_tool import handle_action
            result = handle_action(action, parameters)
        elif tool_name == "gmaps":
            from tools.gmaps_tool import handle_action
            result = handle_action(action, parameters)
        elif tool_name == "memory":
            from tools.memory_tool import handle_action
            result = handle_action(action, parameters)
        elif tool_name == "puppeteer":
            from tools.puppeteer_tool import handle_action
            result = handle_action(action, parameters)
        elif tool_name == "tiered_memory":
            from tiered_memory.mcp_interface import handle_action
            result = handle_action(action, parameters)
        else:
            return jsonify({"error": f"Unknown tool: {tool_name}"}), 404
        
        # Format the response according to MCP
        mcp_response = {
            "tool": tool_name,
            "action": action,
            "status": "success",
            "result": result
        }
        
        return jsonify(mcp_response)
    
    except Exception as e:
        # Handle errors according to MCP
        mcp_error = {
            "tool": tool_name,
            "action": action,
            "status": "error",
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }
        
        return jsonify(mcp_error), 500

# MCP manifest endpoint
@app.route('/mcp/manifest', methods=['GET'])
def mcp_manifest():
    """Returns the MCP manifest describing available tools"""
    
    manifest = {
        "manifestVersion": "1.0",
        "tools": {
            "github": {
                "actions": {
                    "listRepos": {
                        "description": "List repositories for a user or organization",
                        "parameters": {
                            "username": {
                                "type": "string",
                                "description": "GitHub username or organization name"
                            }
                        },
                        "returns": {
                            "type": "array",
                            "description": "List of repository objects"
                        }
                    },
                    "getRepo": {
                        "description": "Get details for a specific repository",
                        "parameters": {
                            "owner": {
                                "type": "string",
                                "description": "Repository owner"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository name"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Repository details"
                        }
                    },
                    "searchRepos": {
                        "description": "Search for repositories",
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Search results"
                        }
                    },
                    "getIssues": {
                        "description": "Get issues for a repository",
                        "parameters": {
                            "owner": {
                                "type": "string",
                                "description": "Repository owner"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository name"
                            },
                            "state": {
                                "type": "string",
                                "description": "Issue state (open, closed, all)",
                                "default": "open"
                            }
                        },
                        "returns": {
                            "type": "array",
                            "description": "List of issue objects"
                        }
                    },
                    "createIssue": {
                        "description": "Create a new issue in a repository",
                        "parameters": {
                            "owner": {
                                "type": "string",
                                "description": "Repository owner"
                            },
                            "repo": {
                                "type": "string",
                                "description": "Repository name"
                            },
                            "title": {
                                "type": "string",
                                "description": "Issue title"
                            },
                            "body": {
                                "type": "string",
                                "description": "Issue body"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Created issue"
                        }
                    }
                }
            },
            "gitlab": {
                "actions": {
                    "listProjects": {
                        "description": "List all projects accessible by the authenticated user",
                        "parameters": {},
                        "returns": {
                            "type": "array",
                            "description": "List of project objects"
                        }
                    },
                    "getProject": {
                        "description": "Get details for a specific project",
                        "parameters": {
                            "projectId": {
                                "type": "string",
                                "description": "GitLab project ID"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Project details"
                        }
                    },
                    "searchProjects": {
                        "description": "Search for projects on GitLab",
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Search results"
                        }
                    }
                }
            },
            "gmaps": {
                "actions": {
                    "geocode": {
                        "description": "Convert an address to geographic coordinates",
                        "parameters": {
                            "address": {
                                "type": "string",
                                "description": "Address to geocode"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Geocoding results"
                        }
                    },
                    "reverseGeocode": {
                        "description": "Convert geographic coordinates to an address",
                        "parameters": {
                            "lat": {
                                "type": "number",
                                "description": "Latitude"
                            },
                            "lng": {
                                "type": "number",
                                "description": "Longitude"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Reverse geocoding results"
                        }
                    },
                    "getDirections": {
                        "description": "Get directions between two locations",
                        "parameters": {
                            "origin": {
                                "type": "string",
                                "description": "Origin address or coordinates"
                            },
                            "destination": {
                                "type": "string",
                                "description": "Destination address or coordinates"
                            },
                            "mode": {
                                "type": "string",
                                "description": "Travel mode (driving, walking, bicycling, transit)",
                                "default": "driving"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Directions results"
                        }
                    }
                }
            },
            "memory": {
                "actions": {
                    "get": {
                        "description": "Get a memory item by key",
                        "parameters": {
                            "key": {
                                "type": "string",
                                "description": "Memory item key"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Memory item"
                        }
                    },
                    "set": {
                        "description": "Create or update a memory item",
                        "parameters": {
                            "key": {
                                "type": "string",
                                "description": "Memory item key"
                            },
                            "value": {
                                "type": "any",
                                "description": "Memory item value"
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Optional metadata",
                                "default": {}
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Created or updated memory item"
                        }
                    },
                    "delete": {
                        "description": "Delete a memory item by key",
                        "parameters": {
                            "key": {
                                "type": "string",
                                "description": "Memory item key"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Deletion result"
                        }
                    },
                    "list": {
                        "description": "List all memory items, with optional filtering",
                        "parameters": {
                            "filterKey": {
                                "type": "string",
                                "description": "Optional key filter"
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of items to return",
                                "default": 100
                            },
                            "offset": {
                                "type": "number",
                                "description": "Number of items to skip",
                                "default": 0
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "List of memory items with pagination info"
                        }
                    }
                }
            },
            "puppeteer": {
                "actions": {
                    "screenshot": {
                        "description": "Take a screenshot of a webpage",
                        "parameters": {
                            "url": {
                                "type": "string",
                                "description": "URL to screenshot"
                            },
                            "fullPage": {
                                "type": "boolean",
                                "description": "Whether to capture the full page",
                                "default": False
                            },
                            "type": {
                                "type": "string",
                                "description": "Image type (png or jpeg)",
                                "default": "png"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Screenshot result with base64-encoded image"
                        }
                    },
                    "pdf": {
                        "description": "Generate a PDF of a webpage",
                        "parameters": {
                            "url": {
                                "type": "string",
                                "description": "URL to convert to PDF"
                            },
                            "printBackground": {
                                "type": "boolean",
                                "description": "Whether to print background graphics",
                                "default": True
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "PDF result with base64-encoded document"
                        }
                    },
                    "extract": {
                        "description": "Extract content from a webpage",
                        "parameters": {
                            "url": {
                                "type": "string",
                                "description": "URL to extract content from"
                            },
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for content to extract"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Extracted content"
                        }
                    }
                }
            },
            "tiered_memory": {
                "description": "Tiered memory system with T0-T4 storage, promotion/demotion, versioning, and hybrid search",
                "actions": {
                    "search": {
                        "description": "Hybrid search across memory tiers (T0-T3)",
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "Search query (natural language)",
                                "required": True
                            },
                            "scope": {
                                "type": "object",
                                "description": "Filter scope (e.g., {source_type: 'github'})"
                            },
                            "domain_tags": {
                                "type": "array",
                                "description": "Filter by domain tags (e.g., ['finance', 'code'])"
                            },
                            "time_range": {
                                "type": "object",
                                "description": "{start: ISO, end: ISO} time range filter"
                            },
                            "k": {
                                "type": "number",
                                "description": "Number of results",
                                "default": 10
                            },
                            "budget_ms": {
                                "type": "number",
                                "description": "Time budget in milliseconds",
                                "default": 500
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for T0 access"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Search results with context pack references"
                        }
                    },
                    "get": {
                        "description": "Retrieve a memory object by ID",
                        "parameters": {
                            "object_id": {
                                "type": "string",
                                "description": "Memory object ID",
                                "required": True
                            },
                            "view": {
                                "type": "string",
                                "description": "View type: snippet, summary, or raw",
                                "default": "summary"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for T0 access"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Memory object"
                        }
                    },
                    "write_event": {
                        "description": "Write an event (episodic/procedural) to memory",
                        "parameters": {
                            "event_type": {
                                "type": "string",
                                "description": "Event type (tool_call, correction, preference)",
                                "required": True
                            },
                            "payload": {
                                "type": "any",
                                "description": "Event content",
                                "required": True
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Additional metadata (object_type, domain_tags, trust_level)"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Created event with ID and tier"
                        }
                    },
                    "pin": {
                        "description": "Pin an object to a specific tier (prevent demotion)",
                        "parameters": {
                            "object_id": {
                                "type": "string",
                                "description": "Object ID to pin",
                                "required": True
                            },
                            "tier_target": {
                                "type": "string",
                                "description": "Target tier (t1 or t2)",
                                "default": "t1"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Pin status"
                        }
                    },
                    "unpin": {
                        "description": "Remove pin from an object",
                        "parameters": {
                            "object_id": {
                                "type": "string",
                                "description": "Object ID to unpin",
                                "required": True
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Unpin status"
                        }
                    },
                    "context_pack": {
                        "description": "Assemble a token-budgeted context pack",
                        "parameters": {
                            "query": {
                                "type": "string",
                                "description": "Query to build context for",
                                "required": True
                            },
                            "scope": {
                                "type": "object",
                                "description": "Scope filters"
                            },
                            "token_budget": {
                                "type": "number",
                                "description": "Maximum tokens",
                                "default": 4000
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Context pack with summary, snippets, facts, validity notes"
                        }
                    },
                    "version": {
                        "description": "Create a new version of an object (don't overwrite)",
                        "parameters": {
                            "object_id": {
                                "type": "string",
                                "description": "Object to version",
                                "required": True
                            },
                            "new_content": {
                                "type": "string",
                                "description": "New content",
                                "required": True
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Additional metadata"
                            },
                            "change_reason": {
                                "type": "string",
                                "description": "Why the change was made"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Version info with old/new IDs"
                        }
                    },
                    "get_versions": {
                        "description": "Get version history for an object",
                        "parameters": {
                            "object_id": {
                                "type": "string",
                                "description": "Object ID",
                                "required": True
                            },
                            "include_content": {
                                "type": "boolean",
                                "description": "Include content in response",
                                "default": False
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Version history"
                        }
                    },
                    "resolve_conflict": {
                        "description": "Resolve conflicts between versions",
                        "parameters": {
                            "object_ids": {
                                "type": "array",
                                "description": "List of conflicting object IDs",
                                "required": True
                            },
                            "resolution": {
                                "type": "string",
                                "description": "Strategy: latest_valid, highest_trust, merge, manual",
                                "default": "latest_valid"
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Resolved object or candidates"
                        }
                    },
                    "export_training_batch": {
                        "description": "Export data for continual learning",
                        "parameters": {
                            "criteria": {
                                "type": "object",
                                "description": "Export criteria (batch_type, time_range, domain_tags)",
                                "required": True
                            }
                        },
                        "returns": {
                            "type": "object",
                            "description": "Training batch manifest"
                        }
                    },
                    "stats": {
                        "description": "Get memory system statistics",
                        "parameters": {},
                        "returns": {
                            "type": "object",
                            "description": "Stats for all tiers"
                        }
                    },
                    "maintenance": {
                        "description": "Run maintenance tasks (promotion/demotion)",
                        "parameters": {},
                        "returns": {
                            "type": "object",
                            "description": "Maintenance results"
                        }
                    }
                },
                "resources": {
                    "context_pack": {
                        "uri": "memory://context_pack/{request_id}",
                        "description": "Cached context pack"
                    },
                    "schema": {
                        "uri": "memory://schema/{project}",
                        "description": "Project-specific retrieval schema"
                    },
                    "object": {
                        "uri": "memory://object/{object_id}",
                        "description": "Memory object by ID"
                    }
                },
                "prompts": {
                    "memory_usage_finance": "Safe memory usage for finance domain",
                    "memory_usage_engineering": "Safe memory usage for engineering domain",
                    "memory_usage_code": "Safe memory usage for code context"
                }
            }
        }
    }
    
    return jsonify(manifest)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=Config.DEBUG)
