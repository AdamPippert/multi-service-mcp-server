# tiered_memory/mcp_interface.py
"""
MCP Interface for Tiered Memory System

Implements the Model Context Protocol (MCP) surface area:

Tools:
- memory.search(query, scope, domain_tags, time_range, k, budget_ms)
- memory.get(object_id, view)
- memory.write_event(event_type, payload, metadata)
- memory.pin(object_id, tier_target) / memory.unpin(object_id)
- memory.export_training_batch(criteria)
- memory.context_pack(query, scope, token_budget)
- memory.version(object_id, new_content, change_reason)
- memory.stats()
- memory.maintenance()

Resources:
- memory://context_pack/<request_id>
- memory://schema/<project>
- memory://object/<object_id>

Prompts:
- memory_usage_finance: Safe usage for finance domain
- memory_usage_engineering: Safe usage for engineering domain
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

tiered_memory_routes = Blueprint('tiered_memory', __name__)

# Global engine instance (initialized on first request)
_engine = None
_tier_manager = None


def get_engine():
    """Get or initialize the memory engine."""
    global _engine, _tier_manager

    if _engine is None:
        from .tiers import TierManager
        from .engine import MemoryEngine

        # Get config from Flask app or environment
        profile = current_app.config.get('MEMORY_PROFILE', 'S')
        config = {
            't1_max_items': current_app.config.get('MEMORY_T1_MAX_ITEMS', 10000),
            't1_ttl': current_app.config.get('MEMORY_T1_TTL', 3600),
            't2_db_path': current_app.config.get('MEMORY_T2_DB_PATH', 'data/memory_t2.db'),
            't3_path': current_app.config.get('MEMORY_T3_PATH', 'data/t3'),
            't4_path': current_app.config.get('MEMORY_T4_PATH', 'data/audit'),
            'valkey_url': current_app.config.get('VALKEY_URL'),
            'postgres_url': current_app.config.get('MEMORY_POSTGRES_URL'),
            's3_bucket': current_app.config.get('MEMORY_S3_BUCKET'),
            's3_endpoint': current_app.config.get('MEMORY_S3_ENDPOINT'),
        }

        _tier_manager = TierManager(profile=profile, config=config)
        _engine = MemoryEngine(_tier_manager, config)

    return _engine


def handle_action(action: str, parameters: Dict) -> Any:
    """
    Handle Memory tool actions according to MCP standard.

    This is the main dispatcher for the MCP gateway.
    """
    action_handlers = {
        # Core operations
        "search": action_search,
        "get": action_get,
        "write_event": action_write_event,
        "pin": action_pin,
        "unpin": action_unpin,

        # Context and retrieval
        "context_pack": action_context_pack,
        "get_context_pack": action_get_context_pack,

        # Versioning and conflict
        "version": action_version,
        "get_versions": action_get_versions,
        "resolve_conflict": action_resolve_conflict,

        # Training and export
        "export_training_batch": action_export_training_batch,

        # Administration
        "stats": action_stats,
        "maintenance": action_maintenance,

        # Legacy compatibility (simple get/set)
        "set": action_set_legacy,
        "delete": action_delete_legacy,
        "list": action_list_legacy,
    }

    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}. Available: {list(action_handlers.keys())}")

    return action_handlers[action](parameters)


# =============================================================================
# Core MCP Actions
# =============================================================================

def action_search(parameters: Dict) -> Dict:
    """
    memory.search - Hybrid search across tiers.

    Parameters:
        query (str, required): Search query
        scope (dict, optional): Filter scope
        domain_tags (list, optional): Filter by domain tags
        time_range (dict, optional): {start: ISO, end: ISO}
        k (int, optional): Number of results (default 10)
        budget_ms (int, optional): Time budget in ms (default 500)
        session_id (str, optional): Session ID for T0 access

    Returns:
        results: List of matching objects
        total: Total matches
        tiers_searched: Which tiers were queried
        latency_ms: Actual latency
    """
    engine = get_engine()

    query = parameters.get('query')
    if not query:
        raise ValueError("query parameter is required")

    scope = parameters.get('scope')
    domain_tags = parameters.get('domain_tags')
    k = int(parameters.get('k', 10))
    budget_ms = int(parameters.get('budget_ms', 500))
    session_id = parameters.get('session_id')

    # Parse time range
    time_range = None
    if parameters.get('time_range'):
        tr = parameters['time_range']
        start = datetime.fromisoformat(tr['start']) if tr.get('start') else None
        end = datetime.fromisoformat(tr['end']) if tr.get('end') else datetime.utcnow()
        time_range = (start, end)

    return engine.search(
        query=query,
        scope=scope,
        domain_tags=domain_tags,
        time_range=time_range,
        k=k,
        budget_ms=budget_ms,
        session_id=session_id
    )


def action_get(parameters: Dict) -> Dict:
    """
    memory.get - Retrieve a memory object by ID.

    Parameters:
        object_id (str, required): The memory object ID
        view (str, optional): One of "snippet", "summary", "raw" (default "summary")
        session_id (str, optional): Session ID for T0 access

    Returns:
        Memory object dict or error
    """
    engine = get_engine()

    object_id = parameters.get('object_id') or parameters.get('id') or parameters.get('key')
    if not object_id:
        raise ValueError("object_id parameter is required")

    view = parameters.get('view', 'summary')
    if view not in ('snippet', 'summary', 'raw'):
        raise ValueError("view must be one of: snippet, summary, raw")

    session_id = parameters.get('session_id')

    result = engine.get(object_id, view=view, session_id=session_id)
    if not result:
        raise ValueError(f"Memory object '{object_id}' not found")

    return result


def action_write_event(parameters: Dict) -> Dict:
    """
    memory.write_event - Write an event into the memory system.

    Parameters:
        event_type (str, required): Type of event (tool_call, correction, etc.)
        payload (dict/str, required): Event content
        metadata (dict, optional): Additional metadata
            - object_type: semantic, episodic, procedural, meta
            - domain_tags: list of tags
            - source_type: source identifier
            - trust_level: verified, user_input, inferred, external
            - summary: optional summary
        session_id (str, optional): Session ID

    Returns:
        id: Created object ID
        status: "created"
        tier: Initial tier
        created_at: Timestamp
    """
    engine = get_engine()

    event_type = parameters.get('event_type')
    if not event_type:
        raise ValueError("event_type parameter is required")

    payload = parameters.get('payload')
    if payload is None:
        raise ValueError("payload parameter is required")

    metadata = parameters.get('metadata', {})
    session_id = parameters.get('session_id')

    return engine.write_event(
        event_type=event_type,
        payload=payload,
        metadata=metadata,
        session_id=session_id
    )


def action_pin(parameters: Dict) -> Dict:
    """
    memory.pin - Pin an object to a specific tier.

    Parameters:
        object_id (str, required): The object to pin
        tier_target (str, optional): Target tier (default "t1")

    Returns:
        success: bool
        id: Object ID
        pinned_tier: Target tier
    """
    engine = get_engine()

    object_id = parameters.get('object_id')
    if not object_id:
        raise ValueError("object_id parameter is required")

    tier_target = parameters.get('tier_target', 't1')
    if tier_target not in ('t1', 't2'):
        raise ValueError("tier_target must be t1 or t2")

    return engine.pin(object_id, tier_target)


def action_unpin(parameters: Dict) -> Dict:
    """
    memory.unpin - Remove pin from an object.

    Parameters:
        object_id (str, required): The object to unpin

    Returns:
        success: bool
        id: Object ID
    """
    engine = get_engine()

    object_id = parameters.get('object_id')
    if not object_id:
        raise ValueError("object_id parameter is required")

    return engine.unpin(object_id)


# =============================================================================
# Context Pack Actions
# =============================================================================

def action_context_pack(parameters: Dict) -> Dict:
    """
    memory.context_pack - Assemble a token-budgeted context pack.

    Parameters:
        query (str, required): Query to build context for
        scope (dict, optional): Scope filters
        token_budget (int, optional): Max tokens (default 4000)
        session_id (str, optional): Session ID

    Returns:
        Context pack with summary, snippets, facts, validity notes
    """
    engine = get_engine()

    query = parameters.get('query')
    if not query:
        raise ValueError("query parameter is required")

    scope = parameters.get('scope')
    token_budget = int(parameters.get('token_budget', 4000))
    session_id = parameters.get('session_id')

    return engine.assemble_context_pack(
        query=query,
        scope=scope,
        token_budget=token_budget,
        session_id=session_id
    )


def action_get_context_pack(parameters: Dict) -> Dict:
    """
    Get a previously assembled context pack by request_id.

    Parameters:
        request_id (str, required): The context pack request ID

    Returns:
        Cached context pack or error
    """
    engine = get_engine()

    request_id = parameters.get('request_id')
    if not request_id:
        raise ValueError("request_id parameter is required")

    t1 = engine.tiers.get_tier('t1')
    pack = t1.get(f"context_pack:{request_id}")

    if not pack:
        raise ValueError(f"Context pack '{request_id}' not found or expired")

    return pack


# =============================================================================
# Versioning Actions
# =============================================================================

def action_version(parameters: Dict) -> Dict:
    """
    memory.version - Create a new version of an object.

    Parameters:
        object_id (str, required): Object to version
        new_content (str, required): New content
        metadata (dict, optional): Additional metadata
        change_reason (str, optional): Why the change was made

    Returns:
        success: bool
        old_version_id: Previous version ID
        new_version_id: New version ID
        version: Version number
    """
    engine = get_engine()

    object_id = parameters.get('object_id')
    if not object_id:
        raise ValueError("object_id parameter is required")

    new_content = parameters.get('new_content')
    if new_content is None:
        raise ValueError("new_content parameter is required")

    metadata = parameters.get('metadata')
    change_reason = parameters.get('change_reason')

    return engine.update_with_version(
        object_id=object_id,
        new_content=new_content,
        metadata=metadata,
        change_reason=change_reason
    )


def action_get_versions(parameters: Dict) -> Dict:
    """
    Get version history for an object.

    Parameters:
        object_id (str, required): Object ID
        include_content (bool, optional): Include content in response

    Returns:
        versions: List of version info
    """
    engine = get_engine()

    object_id = parameters.get('object_id')
    if not object_id:
        raise ValueError("object_id parameter is required")

    include_content = parameters.get('include_content', False)

    versions = engine.get_version_history(object_id, include_content)
    return {'versions': versions, 'count': len(versions)}


def action_resolve_conflict(parameters: Dict) -> Dict:
    """
    Resolve conflicts between multiple versions/objects.

    Parameters:
        object_ids (list, required): List of conflicting object IDs
        resolution (str, optional): Strategy - latest_valid, highest_trust, merge, manual

    Returns:
        Resolved object or candidates for manual resolution
    """
    engine = get_engine()

    object_ids = parameters.get('object_ids')
    if not object_ids or not isinstance(object_ids, list):
        raise ValueError("object_ids parameter must be a list")

    resolution = parameters.get('resolution', 'latest_valid')

    return engine.resolve_conflict(object_ids, resolution)


# =============================================================================
# Training Export Actions
# =============================================================================

def action_export_training_batch(parameters: Dict) -> Dict:
    """
    memory.export_training_batch - Export data for continual learning.

    Parameters (as 'criteria' dict):
        batch_type (str): episodic, semantic, procedural, replay, mixed
        time_start (str, optional): ISO timestamp
        time_end (str, optional): ISO timestamp
        domain_tags (list, optional): Filter by tags
        include_replay (bool, optional): Include replay samples (default True)

    Returns:
        Training batch manifest
    """
    engine = get_engine()

    criteria = parameters.get('criteria', parameters)

    # Parse timestamps
    if 'time_start' in criteria and isinstance(criteria['time_start'], str):
        criteria['time_start'] = datetime.fromisoformat(criteria['time_start'])
    if 'time_end' in criteria and isinstance(criteria['time_end'], str):
        criteria['time_end'] = datetime.fromisoformat(criteria['time_end'])

    return engine.export_training_batch(criteria)


# =============================================================================
# Administration Actions
# =============================================================================

def action_stats(parameters: Dict) -> Dict:
    """
    memory.stats - Get memory system statistics.

    Returns:
        Stats for all tiers, active sessions, etc.
    """
    engine = get_engine()
    return engine.tiers.stats()


def action_maintenance(parameters: Dict) -> Dict:
    """
    memory.maintenance - Run maintenance tasks.

    Triggers promotion/demotion evaluation, cleanup, etc.

    Returns:
        status: complete/already_running
        demoted_count: Number of objects demoted
    """
    engine = get_engine()
    return engine.run_maintenance()


# =============================================================================
# Legacy Compatibility Actions
# =============================================================================

def action_set_legacy(parameters: Dict) -> Dict:
    """
    Legacy set action - wraps write_event for backwards compatibility.
    """
    key = parameters.get('key')
    value = parameters.get('value')
    metadata = parameters.get('metadata', {})

    return action_write_event({
        'event_type': 'set',
        'payload': {'key': key, 'value': value},
        'metadata': {
            'source_id': key,
            **metadata
        }
    })


def action_delete_legacy(parameters: Dict) -> Dict:
    """
    Legacy delete - marks object as archived.
    """
    engine = get_engine()
    key = parameters.get('key')
    if not key:
        raise ValueError("key parameter is required")

    # Get and archive
    obj = engine.get(key, view='raw')
    if not obj:
        raise ValueError(f"Object '{key}' not found")

    # Move to T4 (archive)
    t4 = engine.tiers.get_tier('t4')
    t4.append({
        'event_type': 'archive',
        'object_id': key,
        'object_snapshot': obj
    })

    # Remove from other tiers
    for tier_name in ['t1', 't2', 't3']:
        tier = engine.tiers.get_tier(tier_name)
        tier.delete(key)

    return {'success': True, 'message': f'Object {key} archived'}


def action_list_legacy(parameters: Dict) -> Dict:
    """
    Legacy list action - searches with filters.
    """
    filter_key = parameters.get('filterKey', '*')
    limit = int(parameters.get('limit', 100))

    engine = get_engine()
    t2 = engine.tiers.get_tier('t2')
    keys = t2.scan(pattern=filter_key, limit=limit)

    items = []
    for key in keys:
        obj = t2.get(key)
        if obj:
            items.append({
                'id': obj.get('id'),
                'summary': obj.get('summary'),
                'current_tier': obj.get('current_tier')
            })

    return {
        'items': items,
        'total': len(items),
        'limit': limit
    }


# =============================================================================
# Flask Routes (Direct API Access)
# =============================================================================

@tiered_memory_routes.route('/search', methods=['POST'])
def api_search():
    """API endpoint for memory search."""
    try:
        data = request.get_json() or {}
        result = action_search(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/get/<object_id>', methods=['GET'])
def api_get(object_id):
    """API endpoint for getting a memory object."""
    try:
        view = request.args.get('view', 'summary')
        result = action_get({'object_id': object_id, 'view': view})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/write', methods=['POST'])
def api_write_event():
    """API endpoint for writing an event."""
    try:
        data = request.get_json() or {}
        result = action_write_event(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/pin/<object_id>', methods=['POST'])
def api_pin(object_id):
    """API endpoint for pinning an object."""
    try:
        data = request.get_json() or {}
        data['object_id'] = object_id
        result = action_pin(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/unpin/<object_id>', methods=['POST'])
def api_unpin(object_id):
    """API endpoint for unpinning an object."""
    try:
        result = action_unpin({'object_id': object_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/context_pack', methods=['POST'])
def api_context_pack():
    """API endpoint for assembling a context pack."""
    try:
        data = request.get_json() or {}
        result = action_context_pack(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/context_pack/<request_id>', methods=['GET'])
def api_get_context_pack(request_id):
    """API endpoint for getting a cached context pack."""
    try:
        result = action_get_context_pack({'request_id': request_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/version', methods=['POST'])
def api_version():
    """API endpoint for creating a new version."""
    try:
        data = request.get_json() or {}
        result = action_version(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/versions/<object_id>', methods=['GET'])
def api_get_versions(object_id):
    """API endpoint for getting version history."""
    try:
        include_content = request.args.get('include_content', 'false').lower() == 'true'
        result = action_get_versions({
            'object_id': object_id,
            'include_content': include_content
        })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/export_training', methods=['POST'])
def api_export_training():
    """API endpoint for exporting training batch."""
    try:
        data = request.get_json() or {}
        result = action_export_training_batch(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/stats', methods=['GET'])
def api_stats():
    """API endpoint for getting stats."""
    try:
        result = action_stats({})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tiered_memory_routes.route('/maintenance', methods=['POST'])
def api_maintenance():
    """API endpoint for running maintenance."""
    try:
        result = action_maintenance({})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# =============================================================================
# MCP Resources (via URL pattern)
# =============================================================================

@tiered_memory_routes.route('/resource/<path:resource_path>', methods=['GET'])
def api_resource(resource_path):
    """
    MCP Resource endpoint.

    Supports:
    - context_pack/<request_id>
    - schema/<project>
    - object/<object_id>
    """
    try:
        parts = resource_path.split('/')

        if parts[0] == 'context_pack' and len(parts) > 1:
            result = action_get_context_pack({'request_id': parts[1]})
            return jsonify(result)

        elif parts[0] == 'object' and len(parts) > 1:
            view = request.args.get('view', 'summary')
            result = action_get({'object_id': parts[1], 'view': view})
            return jsonify(result)

        elif parts[0] == 'schema':
            project = parts[1] if len(parts) > 1 else 'default'
            return jsonify(get_schema(project))

        else:
            return jsonify({'error': f'Unknown resource: {resource_path}'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 400


def get_schema(project: str) -> Dict:
    """
    Get project-specific retrieval schema.

    Describes what sources exist and how to query them.
    """
    return {
        'project': project,
        'version': '1.0',
        'tiers': {
            't0': {'type': 'session', 'description': 'In-context session cache'},
            't1': {'type': 'hot_cache', 'description': 'Hot cache with TTL'},
            't2': {'type': 'warm_index', 'description': 'Searchable index with vectors'},
            't3': {'type': 'cold_lake', 'description': 'Object storage for archives'},
            't4': {'type': 'audit_log', 'description': 'Immutable audit trail'},
        },
        'object_types': ['semantic', 'episodic', 'procedural', 'meta'],
        'trust_levels': ['verified', 'user_input', 'external', 'inferred'],
        'available_tools': [
            'memory.search', 'memory.get', 'memory.write_event',
            'memory.pin', 'memory.unpin', 'memory.context_pack',
            'memory.version', 'memory.export_training_batch',
            'memory.stats', 'memory.maintenance'
        ],
        'domain_hints': {
            'finance': 'Always cite filing date and version',
            'engineering': 'Cite spec version and deprecation status',
            'code': 'Include file path and commit reference'
        }
    }


# =============================================================================
# MCP Prompts
# =============================================================================

def get_prompts() -> Dict:
    """
    Get available MCP prompts for memory usage.
    """
    return {
        'memory_usage_finance': {
            'name': 'memory_usage_finance',
            'description': 'How to use project memory safely for finance domain',
            'template': """When using memory for finance data:
1. Always check validity windows (valid_from, valid_to)
2. Prefer verified trust level over inferred
3. Cite filing date and document version in responses
4. If multiple versions exist, present the most recent valid one
5. Note any temporal caveats in your response"""
        },
        'memory_usage_engineering': {
            'name': 'memory_usage_engineering',
            'description': 'How to use project memory safely for engineering domain',
            'template': """When using memory for engineering specs:
1. Check spec version and deprecation status
2. Prefer source documents over derived summaries
3. Note any breaking changes between versions
4. Cross-reference with implementation code where available
5. Flag any temporal validity concerns"""
        },
        'memory_usage_code': {
            'name': 'memory_usage_code',
            'description': 'How to use project memory for code context',
            'template': """When using memory for code context:
1. Include file paths and line numbers
2. Check for recent changes (commit references)
3. Verify against current codebase state
4. Note any deprecated patterns or APIs
5. Cross-reference with tests and documentation"""
        }
    }


@tiered_memory_routes.route('/prompts', methods=['GET'])
def api_prompts():
    """API endpoint for getting available prompts."""
    return jsonify(get_prompts())


@tiered_memory_routes.route('/prompts/<prompt_name>', methods=['GET'])
def api_get_prompt(prompt_name):
    """API endpoint for getting a specific prompt."""
    prompts = get_prompts()
    if prompt_name in prompts:
        return jsonify(prompts[prompt_name])
    return jsonify({'error': f'Prompt not found: {prompt_name}'}), 404
