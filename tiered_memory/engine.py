# tiered_memory/engine.py
"""
Memory Engine - Core orchestration for Tiered Memory System

Handles:
- Promotion/demotion between tiers
- Heat scoring and access tracking
- Conflict resolution with versioning
- Context pack assembly
- Hybrid search (vector + keyword)
- Training batch export
"""

import uuid
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class MemoryEngine:
    """
    Core memory engine that orchestrates tiered storage.

    Promotion Policy:
    - T3→T2: When heat crosses threshold OR repeated access in short window
    - T2→T1: When repeatedly used within a session

    Demotion Policy:
    - T1→T2: After TTL expires or not accessed for N hours
    - T2→T3: Not accessed for N days
    - T3→T4: Archive when retention rules require immutability

    Compaction:
    - T1→T2: Store summary + key snippets + embedding, drop raw chat turns
    - T2→T3: Keep raw canonical artifacts, drop redundant derived forms
    """

    # Default thresholds
    HEAT_THRESHOLD_T3_TO_T2 = 5.0  # Promote from cold to warm
    HEAT_THRESHOLD_T2_TO_T1 = 20.0  # Promote from warm to hot
    DEMOTION_DAYS_T2_TO_T3 = 7  # Days without access before demotion
    DEMOTION_HOURS_T1_TO_T2 = 24  # Hours without access before demotion
    SESSION_REPEAT_WINDOW = 60  # Seconds to consider "repeated access"
    SESSION_REPEAT_COUNT = 3  # Accesses in window to trigger promotion

    def __init__(self, tier_manager, config: Optional[Dict] = None):
        """
        Initialize the memory engine.

        Args:
            tier_manager: TierManager instance for storage access
            config: Optional configuration overrides
        """
        self.tiers = tier_manager
        self.config = config or {}

        # Apply config overrides
        self.heat_t3_t2 = self.config.get('heat_threshold_t3_t2', self.HEAT_THRESHOLD_T3_TO_T2)
        self.heat_t2_t1 = self.config.get('heat_threshold_t2_t1', self.HEAT_THRESHOLD_T2_TO_T1)
        self.demotion_days = self.config.get('demotion_days_t2_t3', self.DEMOTION_DAYS_T2_TO_T3)
        self.demotion_hours = self.config.get('demotion_hours_t1_t2', self.DEMOTION_HOURS_T1_TO_T2)

        # Access tracking for promotion decisions
        self._recent_accesses: Dict[str, List[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

        # Background task state
        self._maintenance_running = False

    # =========================================================================
    # Core Operations
    # =========================================================================

    def get(self, object_id: str, view: str = "summary",
            session_id: Optional[str] = None) -> Optional[Dict]:
        """
        Retrieve a memory object, checking tiers in order.

        Read path:
        1. Check T0 (session cache) if session_id provided
        2. Check T1 (hot cache)
        3. Check T2 (warm index)
        4. Check T3 (cold lake) and promote if found

        Args:
            object_id: The memory object ID
            view: One of "snippet", "summary", "raw"
            session_id: Optional session ID for T0 access

        Returns:
            Memory object dict or None if not found
        """
        result = None
        found_tier = None

        # T0: Session cache
        if session_id:
            session = self.tiers.get_session(session_id)
            result = session.get(object_id)
            if result:
                found_tier = 't0'

        # T1: Hot cache
        if not result:
            t1 = self.tiers.get_tier('t1')
            result = t1.get(object_id)
            if result:
                found_tier = 't1'

        # T2: Warm index
        if not result:
            t2 = self.tiers.get_tier('t2')
            result = t2.get(object_id)
            if result:
                found_tier = 't2'

        # T3: Cold lake (with promotion on hit)
        if not result:
            t3 = self.tiers.get_tier('t3')
            result = t3.get(object_id)
            if result:
                found_tier = 't3'
                # Promote to T2 on cold hit
                self._promote_t3_to_t2(object_id, result)

        if result:
            # Track access for heat scoring
            self._record_access(object_id, 'read', found_tier, session_id)

            # Filter view
            if view == "snippet":
                result = self._to_snippet(result)
            elif view == "summary":
                result = self._to_summary(result)
            # "raw" returns full result

            # Log to audit
            self._audit_event('read', object_id, {
                'view': view,
                'tier': found_tier,
                'session_id': session_id
            })

        return result

    def write_event(self, event_type: str, payload: Dict,
                    metadata: Optional[Dict] = None,
                    session_id: Optional[str] = None) -> Dict:
        """
        Write an event (episodic/procedural) into the memory system.

        Events are:
        1. Written to T1 (hot cache) for immediate access
        2. Appended to T4 (audit log) for immutability
        3. Indexed in T2 if they contain embeddings/searchable content

        Args:
            event_type: Type of event (e.g., "tool_call", "correction", "preference")
            payload: Event content
            metadata: Additional metadata (provenance, domain_tags, etc.)

        Returns:
            Created event with ID and tier placement
        """
        object_id = str(uuid.uuid4())
        now = datetime.utcnow()
        metadata = metadata or {}

        # Build memory object
        memory_obj = {
            'id': object_id,
            'object_type': metadata.get('object_type', 'episodic'),
            'content': json.dumps(payload) if isinstance(payload, dict) else str(payload),
            'summary': metadata.get('summary'),
            'domain_tags': metadata.get('domain_tags', []),
            'source_type': metadata.get('source_type', event_type),
            'source_id': metadata.get('source_id'),
            'current_tier': 't1',
            'trust_level': metadata.get('trust_level', 'user_input'),
            'provenance': {
                'event_type': event_type,
                'session_id': session_id,
                'timestamp': now.isoformat(),
                **metadata.get('provenance', {})
            },
            'valid_from': now.isoformat(),
            'version': 1,
            'is_current': True,
            'heat_score': 1.0,
            'access_count': 1,
            'last_accessed_at': now.isoformat(),
            'created_at': now.isoformat(),
        }

        # Write to T1 (hot cache)
        t1 = self.tiers.get_tier('t1')
        t1.set(object_id, memory_obj, ttl=self.demotion_hours * 3600)

        # Write to T4 (audit log) - immutable
        t4 = self.tiers.get_tier('t4')
        t4.append({
            'id': object_id,
            'event_type': f'write.{event_type}',
            'payload': payload,
            'metadata': metadata,
            'session_id': session_id
        })

        # If content is substantial, also index in T2
        if len(memory_obj.get('content', '')) > 100 or metadata.get('embedding'):
            t2 = self.tiers.get_tier('t2')
            t2.set(object_id, memory_obj)

        # Update session cache if active
        if session_id:
            session = self.tiers.get_session(session_id)
            session.set(object_id, memory_obj, estimated_tokens=len(str(payload)) // 4)

        return {
            'id': object_id,
            'status': 'created',
            'tier': 't1',
            'event_type': event_type,
            'created_at': now.isoformat()
        }

    def search(self, query: str, scope: Optional[Dict] = None,
               domain_tags: Optional[List[str]] = None,
               time_range: Optional[Tuple[datetime, datetime]] = None,
               k: int = 10, budget_ms: int = 500,
               session_id: Optional[str] = None) -> Dict:
        """
        Hybrid search across tiers.

        Search path:
        1. Check T0/T1 for recent hot data
        2. Query T2 hybrid index (vector + keyword + metadata)
        3. If recall low, query T3 and promote hot hits

        Args:
            query: Search query (natural language)
            scope: Filter scope (e.g., {"source_type": "github"})
            domain_tags: Filter by domain tags
            time_range: (start, end) datetime tuple
            k: Number of results
            budget_ms: Time budget in milliseconds
            session_id: Optional session for T0 access

        Returns:
            Search results with context pack references
        """
        import time
        start_time = time.time()
        results = []
        tiers_searched = []

        filters = self._build_filters(scope, domain_tags, time_range)

        # T0: Session cache (fast scan)
        if session_id:
            session = self.tiers.get_session(session_id)
            for key in session.order[-20:]:  # Recent items
                item = session.get(key)
                if item and self._matches_query(item, query, filters):
                    results.append({'id': key, 'score': 1.0, 'tier': 't0', **item})
            tiers_searched.append('t0')

        # T1: Hot cache (if time permits)
        elapsed = (time.time() - start_time) * 1000
        if elapsed < budget_ms * 0.3:
            t1 = self.tiers.get_tier('t1')
            t1_keys = t1.scan(limit=50)
            for key in t1_keys:
                item = t1.get(key)
                if item and self._matches_query(item, query, filters):
                    results.append({'id': key, 'score': 0.9, 'tier': 't1', **item})
            tiers_searched.append('t1')

        # T2: Warm index (primary search)
        elapsed = (time.time() - start_time) * 1000
        if elapsed < budget_ms * 0.7:
            t2 = self.tiers.get_tier('t2')

            # Keyword search
            if hasattr(t2, 'search_keyword'):
                keyword_hits = t2.search_keyword(query, k=k, filters=filters)
                for obj_id in keyword_hits:
                    if not any(r['id'] == obj_id for r in results):
                        item = t2.get(obj_id)
                        if item:
                            results.append({'id': obj_id, 'score': 0.7, 'tier': 't2', **item})

            # Vector search (if embedding available)
            if hasattr(t2, 'search_vector'):
                embedding = self._get_query_embedding(query)
                if embedding:
                    vector_hits = t2.search_vector(embedding, k=k, filters=filters)
                    for obj_id, score in vector_hits:
                        existing = next((r for r in results if r['id'] == obj_id), None)
                        if existing:
                            existing['score'] = max(existing['score'], score)
                        else:
                            item = t2.get(obj_id)
                            if item:
                                results.append({'id': obj_id, 'score': score, 'tier': 't2', **item})

            tiers_searched.append('t2')

        # T3: Cold lake (if recall is low and time permits)
        elapsed = (time.time() - start_time) * 1000
        if len(results) < k // 2 and elapsed < budget_ms:
            t3 = self.tiers.get_tier('t3')
            t3_keys = t3.scan(limit=20)
            for key in t3_keys:
                if not any(r['id'] == key for r in results):
                    item = t3.get(key)
                    if item and self._matches_query(item, query, filters):
                        results.append({'id': key, 'score': 0.5, 'tier': 't3', **item})
                        # Promote on search hit
                        self._record_access(key, 'search_hit', 't3', session_id)
            tiers_searched.append('t3')

        # Sort by score and limit
        results.sort(key=lambda x: x['score'], reverse=True)
        results = results[:k]

        # Record accesses for all results
        for r in results:
            self._record_access(r['id'], 'search_hit', r['tier'], session_id)

        # Audit the search
        self._audit_event('search', None, {
            'query': query,
            'scope': scope,
            'domain_tags': domain_tags,
            'result_count': len(results),
            'tiers_searched': tiers_searched,
            'latency_ms': int((time.time() - start_time) * 1000)
        })

        return {
            'results': results,
            'total': len(results),
            'query': query,
            'tiers_searched': tiers_searched,
            'latency_ms': int((time.time() - start_time) * 1000)
        }

    def pin(self, object_id: str, tier_target: str = 't1') -> Dict:
        """
        Pin an object to a specific tier (prevent demotion).

        Args:
            object_id: The memory object ID
            tier_target: Target tier to pin to (t1, t2)

        Returns:
            Pin status
        """
        # Get the object
        obj = self.get(object_id, view='raw')
        if not obj:
            return {'success': False, 'error': 'Object not found'}

        # Update pin status
        obj['is_pinned'] = True
        obj['pinned_tier'] = tier_target

        # Ensure it's in the target tier
        target = self.tiers.get_tier(tier_target)
        target.set(object_id, obj)

        # Audit
        self._audit_event('pin', object_id, {
            'tier_target': tier_target
        })

        return {
            'success': True,
            'id': object_id,
            'pinned_tier': tier_target
        }

    def unpin(self, object_id: str) -> Dict:
        """Remove pin from an object."""
        obj = self.get(object_id, view='raw')
        if not obj:
            return {'success': False, 'error': 'Object not found'}

        obj['is_pinned'] = False
        obj['pinned_tier'] = None

        # Update in current tier
        tier = obj.get('current_tier', 't2')
        self.tiers.get_tier(tier).set(object_id, obj)

        self._audit_event('unpin', object_id, {})

        return {'success': True, 'id': object_id}

    def export_training_batch(self, criteria: Dict) -> Dict:
        """
        Export a training batch for continual learning.

        Criteria can include:
        - batch_type: "episodic", "semantic", "procedural", "replay"
        - time_range: (start, end)
        - domain_tags: list
        - event_types: list
        - include_replay: bool (sample from older high-value memory)

        Returns:
            Training batch manifest
        """
        from .models import TrainingBatch

        batch_id = str(uuid.uuid4())
        batch_type = criteria.get('batch_type', 'mixed')
        time_start = criteria.get('time_start')
        time_end = criteria.get('time_end', datetime.utcnow())
        include_replay = criteria.get('include_replay', True)

        event_ids = []
        object_ids = []
        examples = []

        # Query T4 audit log for events
        t4 = self.tiers.get_tier('t4')
        audit_entries = t4.scan(limit=1000)

        for entry_id in audit_entries:
            entry = t4.get(entry_id)
            if not entry:
                continue

            # Filter by criteria
            entry_time = datetime.fromisoformat(entry.get('timestamp', '2000-01-01'))
            if time_start and entry_time < time_start:
                continue
            if time_end and entry_time > time_end:
                continue

            event_type = entry.get('event_type', '')

            # Select based on batch type
            if batch_type == 'episodic' and 'correction' in event_type:
                event_ids.append(entry_id)
                examples.append(self._format_training_example(entry, 'episodic'))
            elif batch_type == 'semantic' and 'write' in event_type:
                event_ids.append(entry_id)
                examples.append(self._format_training_example(entry, 'semantic'))
            elif batch_type == 'procedural' and 'tool_call' in event_type:
                event_ids.append(entry_id)
                examples.append(self._format_training_example(entry, 'procedural'))
            elif batch_type == 'mixed':
                event_ids.append(entry_id)
                examples.append(self._format_training_example(entry, 'mixed'))

        # Add replay set if requested (sample from high-value T2/T3 data)
        if include_replay:
            t2 = self.tiers.get_tier('t2')
            t2_keys = t2.scan(limit=100)
            import random
            replay_keys = random.sample(t2_keys, min(len(t2_keys), 20))
            for key in replay_keys:
                obj = t2.get(key)
                if obj and obj.get('heat_score', 0) > 5:
                    object_ids.append(key)
                    examples.append(self._format_training_example(obj, 'replay'))

        # Calculate token count (rough estimate)
        token_count = sum(len(str(e)) // 4 for e in examples)

        batch = {
            'id': batch_id,
            'batch_type': batch_type,
            'status': 'complete',
            'event_ids': event_ids[:100],  # Limit manifest size
            'object_ids': object_ids,
            'total_examples': len(examples),
            'token_count': token_count,
            'criteria': criteria,
            'created_at': datetime.utcnow().isoformat()
        }

        # Store manifest in T3
        t3 = self.tiers.get_tier('t3')
        t3.set(f"training_batch_{batch_id}", {
            **batch,
            'examples': examples
        })

        self._audit_event('export_training_batch', None, {
            'batch_id': batch_id,
            'example_count': len(examples)
        })

        return batch

    # =========================================================================
    # Context Pack Assembly
    # =========================================================================

    def assemble_context_pack(self, query: str,
                               scope: Optional[Dict] = None,
                               token_budget: int = 4000,
                               session_id: Optional[str] = None) -> Dict:
        """
        Assemble a token-budgeted context pack for model consumption.

        Structure:
        1. "What you need to know" summary (≤ N tokens)
        2. Key snippets (ranked) with citations/provenance
        3. Structured facts (optional)
        4. Safety/validity notes (finance/engineering)
        5. Pointers for deeper fetch

        Args:
            query: The query to build context for
            scope: Scope filters
            token_budget: Maximum tokens for the pack
            session_id: Session ID for T0 access

        Returns:
            Context pack dict
        """
        request_id = str(uuid.uuid4())

        # Search for relevant content
        search_results = self.search(
            query=query,
            scope=scope,
            k=20,
            budget_ms=300,
            session_id=session_id
        )

        snippets = []
        facts = []
        validity_notes = []
        pointers = []
        total_tokens = 0

        # Reserve tokens for summary
        summary_budget = min(500, token_budget // 4)
        content_budget = token_budget - summary_budget

        for result in search_results.get('results', []):
            # Estimate tokens
            content = result.get('summary') or result.get('content', '')
            content_tokens = len(content) // 4

            if total_tokens + content_tokens > content_budget:
                # Add as pointer for deeper fetch
                pointers.append(result['id'])
                continue

            # Build snippet with provenance
            snippet = {
                'id': result['id'],
                'content': content[:1000],  # Truncate long content
                'source_type': result.get('source_type'),
                'trust_level': result.get('trust_level'),
                'valid_from': result.get('valid_from'),
                'valid_to': result.get('valid_to'),
                'score': result.get('score', 0)
            }
            snippets.append(snippet)
            total_tokens += content_tokens

            # Check for validity concerns (finance/engineering)
            if result.get('valid_to'):
                validity_notes.append({
                    'id': result['id'],
                    'note': f"Valid until {result['valid_to']}",
                    'type': 'temporal_validity'
                })

            if result.get('trust_level') == 'inferred':
                validity_notes.append({
                    'id': result['id'],
                    'note': 'Model-inferred, may need verification',
                    'type': 'trust_level'
                })

        # Build summary
        summary = self._build_summary(query, snippets, summary_budget)

        context_pack = {
            'id': str(uuid.uuid4()),
            'request_id': request_id,
            'summary': summary,
            'snippets': snippets,
            'structured_facts': facts,
            'validity_notes': validity_notes,
            'pointers': pointers,
            'token_count': total_tokens + len(summary) // 4,
            'token_budget': token_budget,
            'original_query': query,
            'scope': scope,
            'created_at': datetime.utcnow().isoformat()
        }

        # Cache the pack
        t1 = self.tiers.get_tier('t1')
        t1.set(f"context_pack:{request_id}", context_pack, ttl=300)

        return context_pack

    # =========================================================================
    # Versioning and Conflict Resolution
    # =========================================================================

    def update_with_version(self, object_id: str, new_content: str,
                            metadata: Optional[Dict] = None,
                            change_reason: Optional[str] = None) -> Dict:
        """
        Update a memory object with versioning (don't overwrite).

        Creates a new version with validity window, preserving the old version.

        Args:
            object_id: The object to update
            new_content: New content
            metadata: Additional metadata
            change_reason: Why the change was made

        Returns:
            New version info
        """
        # Get current version
        current = self.get(object_id, view='raw')
        if not current:
            return {'success': False, 'error': 'Object not found'}

        now = datetime.utcnow()
        new_id = str(uuid.uuid4())

        # Create new version
        new_version = {
            **current,
            'id': new_id,
            'content': new_content,
            'version': current.get('version', 1) + 1,
            'parent_version_id': object_id,
            'is_current': True,
            'valid_from': now.isoformat(),
            'valid_to': None,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }

        if metadata:
            new_version.update(metadata)

        # Mark old version as superseded
        current['is_current'] = False
        current['valid_to'] = now.isoformat()

        # Store both versions
        tier_name = current.get('current_tier', 't2')
        tier = self.tiers.get_tier(tier_name)
        tier.set(object_id, current)
        tier.set(new_id, new_version)

        # Record version history
        self._audit_event('version', object_id, {
            'new_version_id': new_id,
            'version_number': new_version['version'],
            'change_reason': change_reason,
            'content_preview': new_content[:200]
        })

        return {
            'success': True,
            'old_version_id': object_id,
            'new_version_id': new_id,
            'version': new_version['version']
        }

    def get_version_history(self, object_id: str,
                            include_content: bool = False) -> List[Dict]:
        """Get all versions of a memory object."""
        versions = []
        current_id = object_id

        while current_id:
            obj = self.get(current_id, view='raw' if include_content else 'summary')
            if not obj:
                break

            version_info = {
                'id': obj.get('id'),
                'version': obj.get('version', 1),
                'valid_from': obj.get('valid_from'),
                'valid_to': obj.get('valid_to'),
                'is_current': obj.get('is_current', True)
            }

            if include_content:
                version_info['content'] = obj.get('content')

            versions.append(version_info)

            # Move to parent version
            current_id = obj.get('parent_version_id')

        return versions

    def resolve_conflict(self, object_ids: List[str],
                         resolution: str = "latest_valid") -> Dict:
        """
        Resolve conflicts between multiple versions/objects.

        Resolution strategies:
        - latest_valid: Prefer highest version number that's currently valid
        - highest_trust: Prefer highest trust level
        - merge: Combine content (returns both)
        - manual: Return all for user decision

        Args:
            object_ids: List of conflicting object IDs
            resolution: Resolution strategy

        Returns:
            Resolved object or list of candidates
        """
        objects = []
        for oid in object_ids:
            obj = self.get(oid, view='raw')
            if obj:
                objects.append(obj)

        if not objects:
            return {'success': False, 'error': 'No objects found'}

        if resolution == "latest_valid":
            # Filter to currently valid, sort by version
            valid = [o for o in objects if o.get('is_current', True)]
            if valid:
                valid.sort(key=lambda x: x.get('version', 0), reverse=True)
                return {'success': True, 'resolved': valid[0], 'strategy': 'latest_valid'}
            # Fall back to most recent
            objects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return {'success': True, 'resolved': objects[0], 'strategy': 'most_recent'}

        elif resolution == "highest_trust":
            trust_order = {'verified': 4, 'user_input': 3, 'external': 2, 'inferred': 1}
            objects.sort(
                key=lambda x: trust_order.get(x.get('trust_level', 'inferred'), 0),
                reverse=True
            )
            return {'success': True, 'resolved': objects[0], 'strategy': 'highest_trust'}

        elif resolution == "merge":
            return {
                'success': True,
                'resolved': objects,
                'strategy': 'merge',
                'note': 'Multiple versions returned for manual review'
            }

        else:  # manual
            return {
                'success': True,
                'candidates': objects,
                'strategy': 'manual',
                'note': 'Choose one or merge manually'
            }

    # =========================================================================
    # Promotion/Demotion Engine
    # =========================================================================

    def _record_access(self, object_id: str, access_type: str,
                       tier: str, session_id: Optional[str] = None):
        """Record an access for heat scoring and promotion decisions."""
        now = datetime.utcnow()

        with self._lock:
            # Track recent accesses for burst detection
            self._recent_accesses[object_id].append(now)

            # Clean old accesses
            cutoff = now - timedelta(seconds=self.SESSION_REPEAT_WINDOW)
            self._recent_accesses[object_id] = [
                t for t in self._recent_accesses[object_id] if t > cutoff
            ]

            # Check for promotion trigger
            if len(self._recent_accesses[object_id]) >= self.SESSION_REPEAT_COUNT:
                self._trigger_promotion(object_id, tier, 'burst_access')

    def _trigger_promotion(self, object_id: str, current_tier: str, reason: str):
        """Promote an object to a higher tier."""
        target_tier = None

        if current_tier == 't3':
            target_tier = 't2'
        elif current_tier == 't2':
            target_tier = 't1'
        else:
            return  # Already at T1 or T0

        # Get the object
        source = self.tiers.get_tier(current_tier)
        obj = source.get(object_id)
        if not obj:
            return

        # Don't promote if pinned elsewhere
        if obj.get('is_pinned') and obj.get('pinned_tier') != target_tier:
            return

        # Update tier info
        obj['current_tier'] = target_tier

        # Compact if moving to T1 (store summary, drop full content)
        if target_tier == 't1':
            if obj.get('content') and not obj.get('summary'):
                obj['summary'] = obj['content'][:500]
            # T1 only stores summary form
            compact_obj = {
                'id': obj['id'],
                'summary': obj.get('summary'),
                'domain_tags': obj.get('domain_tags', []),
                'source_type': obj.get('source_type'),
                'heat_score': obj.get('heat_score', 0) + 5,  # Boost for promotion
                'current_tier': 't1',
                'promoted_at': datetime.utcnow().isoformat(),
                'promoted_reason': reason
            }
            target = self.tiers.get_tier(target_tier)
            target.set(object_id, compact_obj, ttl=self.demotion_hours * 3600)
        else:
            # T2 keeps full object
            target = self.tiers.get_tier(target_tier)
            target.set(object_id, obj)

        logger.info(f"Promoted {object_id} from {current_tier} to {target_tier}: {reason}")

        self._audit_event('promote', object_id, {
            'from_tier': current_tier,
            'to_tier': target_tier,
            'reason': reason
        })

    def _promote_t3_to_t2(self, object_id: str, obj: Dict):
        """Promote from cold lake to warm index on access."""
        obj['current_tier'] = 't2'
        obj['heat_score'] = obj.get('heat_score', 0) + 1
        obj['last_accessed_at'] = datetime.utcnow().isoformat()

        t2 = self.tiers.get_tier('t2')
        t2.set(object_id, obj)

        self._audit_event('promote', object_id, {
            'from_tier': 't3',
            'to_tier': 't2',
            'reason': 'cold_access'
        })

    def run_maintenance(self):
        """
        Run maintenance tasks:
        - Demote stale T1→T2, T2→T3
        - Clean expired TTLs
        - Compact T2→T3 for old items
        """
        if self._maintenance_running:
            return {'status': 'already_running'}

        self._maintenance_running = True
        demoted_count = 0

        try:
            now = datetime.utcnow()

            # T1→T2 demotion (handled by TTL in most backends)
            # For in-memory backend, check explicitly
            t1 = self.tiers.get_tier('t1')
            if hasattr(t1, '_store'):
                # In-memory backend
                keys_to_demote = []
                for key in list(t1._store.keys()):
                    obj = t1.get(key)
                    if obj and not obj.get('is_pinned'):
                        last_access = obj.get('last_accessed_at')
                        if last_access:
                            last_dt = datetime.fromisoformat(last_access)
                            if now - last_dt > timedelta(hours=self.demotion_hours):
                                keys_to_demote.append(key)

                for key in keys_to_demote:
                    obj = t1.get(key)
                    if obj:
                        obj['current_tier'] = 't2'
                        t2 = self.tiers.get_tier('t2')
                        t2.set(key, obj)
                        t1.delete(key)
                        demoted_count += 1

            # T2→T3 demotion
            t2 = self.tiers.get_tier('t2')
            if hasattr(t2, '_Session'):
                # SQLite or Postgres backend
                from .models import MemoryObject, Tier
                session = t2._Session()
                try:
                    cutoff = now - timedelta(days=self.demotion_days)
                    stale = session.query(MemoryObject).filter(
                        MemoryObject.current_tier == Tier.T2,
                        MemoryObject.is_pinned == False,
                        MemoryObject.last_accessed_at < cutoff
                    ).limit(100).all()

                    t3 = self.tiers.get_tier('t3')
                    for obj in stale:
                        # Move to T3
                        t3.set(obj.id, obj.to_dict('raw'))
                        obj.current_tier = Tier.T3
                        demoted_count += 1

                    session.commit()
                finally:
                    session.close()

        finally:
            self._maintenance_running = False

        return {
            'status': 'complete',
            'demoted_count': demoted_count,
            'timestamp': datetime.utcnow().isoformat()
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _audit_event(self, event_type: str, object_id: Optional[str], data: Dict):
        """Append to audit log."""
        try:
            t4 = self.tiers.get_tier('t4')
            t4.append({
                'event_type': event_type,
                'object_id': object_id,
                **data
            })
        except Exception as e:
            logger.error(f"Audit log error: {e}")

    def _build_filters(self, scope: Optional[Dict],
                       domain_tags: Optional[List[str]],
                       time_range: Optional[Tuple]) -> Dict:
        """Build filter dict for search."""
        filters = {}
        if scope:
            filters.update(scope)
        if domain_tags:
            filters['domain_tags'] = domain_tags
        if time_range:
            filters['valid_at'] = time_range[0]  # Filter by start of range
        return filters

    def _matches_query(self, item: Dict, query: str, filters: Dict) -> bool:
        """Simple query matching for T0/T1 scans."""
        query_lower = query.lower()

        # Content match
        content = (item.get('content', '') or '').lower()
        summary = (item.get('summary', '') or '').lower()
        if query_lower not in content and query_lower not in summary:
            return False

        # Filter matches
        if 'domain_tags' in filters:
            item_tags = item.get('domain_tags', [])
            if not any(t in item_tags for t in filters['domain_tags']):
                return False

        if 'source_type' in filters:
            if item.get('source_type') != filters['source_type']:
                return False

        return True

    def _get_query_embedding(self, query: str) -> Optional[bytes]:
        """Get embedding for query (placeholder - integrate with embedding service)."""
        # In production, call embedding API (OpenAI, sentence-transformers, etc.)
        # For now, return None to skip vector search
        return None

    def _to_snippet(self, obj: Dict) -> Dict:
        """Convert to snippet view."""
        return {
            'id': obj.get('id'),
            'summary': (obj.get('summary') or obj.get('content', ''))[:500],
            'source_type': obj.get('source_type'),
            'valid_from': obj.get('valid_from')
        }

    def _to_summary(self, obj: Dict) -> Dict:
        """Convert to summary view."""
        return {
            'id': obj.get('id'),
            'summary': obj.get('summary') or obj.get('content', '')[:1000],
            'domain_tags': obj.get('domain_tags', []),
            'source_type': obj.get('source_type'),
            'trust_level': obj.get('trust_level'),
            'valid_from': obj.get('valid_from'),
            'valid_to': obj.get('valid_to'),
            'heat_score': obj.get('heat_score'),
            'current_tier': obj.get('current_tier')
        }

    def _build_summary(self, query: str, snippets: List[Dict],
                       token_budget: int) -> str:
        """Build a summary for context pack."""
        if not snippets:
            return f"No relevant context found for: {query}"

        summary_parts = [f"Context for: {query}"]
        summary_parts.append(f"Found {len(snippets)} relevant items:")

        for i, s in enumerate(snippets[:5], 1):
            source = s.get('source_type', 'unknown')
            trust = s.get('trust_level', 'unknown')
            summary_parts.append(f"{i}. [{source}/{trust}] {s.get('content', '')[:100]}...")

        summary = "\n".join(summary_parts)
        # Truncate to budget
        max_chars = token_budget * 4
        return summary[:max_chars]

    def _format_training_example(self, data: Dict, example_type: str) -> Dict:
        """Format data as a training example."""
        return {
            'type': example_type,
            'content': data.get('content') or data.get('payload', {}),
            'metadata': {
                'source_type': data.get('source_type') or data.get('event_type'),
                'timestamp': data.get('timestamp') or data.get('created_at'),
                'trust_level': data.get('trust_level')
            }
        }
