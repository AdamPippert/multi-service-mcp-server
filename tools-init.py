# tools/__init__.py
"""
MCP Tools Package
Contains the various tool implementations for the Model Context Protocol server.
"""

from flask import Flask

def register_tools(app: Flask):
    """
    Register all tool blueprints with the Flask application.
    
    Args:
        app: The Flask application instance
    """
    from .github_tool import github_routes
    from .gitlab_tool import gitlab_routes
    from .gmaps_tool import gmaps_routes
    from .memory_tool import memory_routes
    from .puppeteer_tool import puppeteer_routes
    
    # Register blueprints
    app.register_blueprint(github_routes, url_prefix='/tool/github')
    app.register_blueprint(gitlab_routes, url_prefix='/tool/gitlab')
    app.register_blueprint(gmaps_routes, url_prefix='/tool/gmaps')
    app.register_blueprint(memory_routes, url_prefix='/tool/memory')
    app.register_blueprint(puppeteer_routes, url_prefix='/tool/puppeteer')
