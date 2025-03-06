# tools/memory_tool.py
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import json
import uuid

memory_routes = Blueprint('memory', __name__)

# Initialize SQLAlchemy
Base = declarative_base()

class MemoryItem(Base):
    """Model for storing memory items"""
    __tablename__ = 'memory_items'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

# Initialize database
engine = None
Session = None

def initialize_db(app):
    """Initialize the database with the Flask app context"""
    global engine, Session
    engine = create_engine(app.config['MEMORY_DB_URI'])
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

def handle_action(action, parameters):
    """Handle Memory tool actions according to MCP standard"""
    action_handlers = {
        "get": get_memory,
        "set": set_memory,
        "delete": delete_memory,
        "list": list_memory,
        "search": search_memory
    }
    
    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}")
    
    return action_handlers[action](parameters)

def get_memory(parameters):
    """Get a memory item by key"""
    key = parameters.get('key')
    
    if not key:
        raise ValueError("Key parameter is required")
    
    # Initialize DB if needed
    if engine is None:
        initialize_db(current_app)
    
    session = Session()
    item = session.query(MemoryItem).filter_by(key=key).first()
    session.close()
    
    if not item:
        raise ValueError(f"Memory item with key '{key}' not found")
    
    return item.to_dict()

def set_memory(parameters):
    """Create or update a memory item"""
    key = parameters.get('key')
    value = parameters.get('value')
    metadata = parameters.get('metadata', {})
    
    if not key:
        key = str(uuid.uuid4())
    
    # Initialize DB if needed
    if engine is None:
        initialize_db(current_app)
    
    session = Session()
    item = session.query(MemoryItem).filter_by(key=key).first()
    
    if item:
        item.value = value
        item.metadata = metadata
        item.updated_at = datetime.datetime.utcnow()
    else:
        item = MemoryItem(key=key, value=value, metadata=metadata)
        session.add(item)
    
    session.commit()
    result = item.to_dict()
    session.close()
    
    return result

def delete_memory(parameters):
    """Delete a memory item by key"""
    key = parameters.get('key')
    
    if not key:
        raise ValueError("Key parameter is required")
    
    # Initialize DB if needed
    if engine is None:
        initialize_db(current_app)
    
    session = Session()
    item = session.query(MemoryItem).filter_by(key=key).first()
    
    if not item:
        session.close()
        raise ValueError(f"Memory item with key '{key}' not found")
    
    session.delete(item)
    session.commit()
    session.close()
    
    return {'success': True, 'message': f'Memory item with key {key} deleted successfully'}

def list_memory(parameters):
    """List all memory items, with optional filtering"""
    filter_key = parameters.get('filterKey')
    limit = int(parameters.get('limit', 100))
    offset = int(parameters.get('offset', 0))
    
    # Initialize DB if needed
    if engine is None:
        initialize_db(current_app)
    
    session = Session()
    query = session.query(MemoryItem)
    
    if filter_key:
        query = query.filter(MemoryItem.key.like(f'%{filter_key}%'))
    
    total = query.count()
    items = query.limit(limit).offset(offset).all()
    result = [item.to_dict() for item in items]
    session.close()
    
    return {
        'items': result,
        'total': total,
        'limit': limit,
        'offset': offset
    }

def search_memory(parameters):
    """Search memory items by value"""
    query_string = parameters.get('q')
    
    if not query_string:
        raise ValueError("Query parameter is required")
    
    # Initialize DB if needed
    if engine is None:
        initialize_db(current_app)
    
    session = Session()
    items = session.query(MemoryItem).filter(MemoryItem.value.like(f'%{query_string}%')).all()
    result = [item.to_dict() for item in items]
    session.close()
    
    return {
        'items': result,
        'count': len(result),
        'query': query_string
    }

# API routes for direct access (not through MCP gateway)
@memory_routes.route('/get', methods=['GET'])
def api_get_memory():
    """API endpoint for getting a memory item"""
    try:
        key = request.args.get('key')
        result = get_memory({'key': key})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@memory_routes.route('/set', methods=['POST'])
def api_set_memory():
    """API endpoint for setting a memory item"""
    try:
        data = request.get_json()
        parameters = {
            'key': data.get('key'),
            'value': data.get('value'),
            'metadata': data.get('metadata', {})
        }
        result = set_memory(parameters)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@memory_routes.route('/delete', methods=['DELETE'])
def api_delete_memory():
    """API endpoint for deleting a memory item"""
    try:
        key = request.args.get('key')
        result = delete_memory({'key': key})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@memory_routes.route('/list', methods=['GET'])
def api_list_memory():
    """API endpoint for listing memory items"""
    try:
        parameters = {
            'filterKey': request.args.get('filterKey'),
            'limit': request.args.get('limit', 100),
            'offset': request.args.get('offset', 0)
        }
        result = list_memory(parameters)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@memory_routes.route('/search', methods=['GET'])
def api_search_memory():
    """API endpoint for searching memory items"""
    try:
        query = request.args.get('q')
        result = search_memory({'q': query})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Initialize the database on first request
@memory_routes.before_app_first_request
def before_first_request():
    initialize_db(current_app)
