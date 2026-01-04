# tiered_memory/models.py
"""
Memory Object Schema and Data Models for Tiered Memory System

Memory Object Types:
- semantic: Facts, documents, embeddings (e.g., "AAPL earnings")
- episodic: Events, conversations, tool traces
- procedural: Skills, code patches, verified workflows
- meta: System state, user preferences, model config

Tiers:
- T0: In-context (current session, in-memory)
- T1: Hot cache (Redis-like, TTL-heavy, session summaries)
- T2: Warm index (vector + keyword search, Postgres/pgvector)
- T3: Cold lake (S3/MinIO object store)
- T4: Audit log (immutable append-only)
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime,
    JSON, Float, Boolean, Enum, ForeignKey, Index, LargeBinary
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import enum
import uuid
import json
import hashlib

Base = declarative_base()


class MemoryType(enum.Enum):
    """Types of memory objects"""
    SEMANTIC = "semantic"      # Facts, documents, embeddings
    EPISODIC = "episodic"      # Events, conversations, tool traces
    PROCEDURAL = "procedural"  # Skills, code patches, workflows
    META = "meta"              # System state, preferences


class Tier(enum.Enum):
    """Storage tiers with different performance/cost characteristics"""
    T0 = "t0"  # In-context (session)
    T1 = "t1"  # Hot cache
    T2 = "t2"  # Warm index
    T3 = "t3"  # Cold lake
    T4 = "t4"  # Audit log (immutable)


class TrustLevel(enum.Enum):
    """Trust levels for provenance tracking"""
    VERIFIED = "verified"      # Human-verified or authoritative source
    INFERRED = "inferred"      # Model-generated or derived
    USER_INPUT = "user_input"  # Direct user input
    EXTERNAL = "external"      # External API or system


class MemoryObject(Base):
    """
    Core memory object schema with full provenance and versioning support.

    This is the canonical representation stored in T2/T3.
    T1 stores summaries/hot data, T4 stores immutable audit log.
    """
    __tablename__ = 'memory_objects'

    # Primary identification
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    object_type = Column(Enum(MemoryType), nullable=False, default=MemoryType.SEMANTIC)

    # Content storage
    content = Column(Text, nullable=True)  # Raw content
    summary = Column(Text, nullable=True)  # Compacted summary for T1/T2
    embedding = Column(LargeBinary, nullable=True)  # Vector embedding (serialized)
    embedding_model = Column(String(100), nullable=True)  # Model used for embedding

    # Structural metadata
    domain_tags = Column(JSON, default=list)  # e.g., ["finance", "code", "engineering"]
    source_type = Column(String(50), nullable=True)  # e.g., "github", "confluence", "chat"
    source_id = Column(String(255), nullable=True)  # External reference ID

    # Tier management
    current_tier = Column(Enum(Tier), nullable=False, default=Tier.T2)
    is_pinned = Column(Boolean, default=False)
    pinned_tier = Column(Enum(Tier), nullable=True)  # If pinned, which tier

    # Heat scoring for promotion/demotion
    heat_score = Column(Float, default=0.0)  # Access frequency weighted by recency
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime, nullable=True)
    decay_rate = Column(Float, default=0.1)  # Heat decay per day

    # Validity and provenance
    valid_from = Column(DateTime, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)  # NULL means currently valid
    trust_level = Column(Enum(TrustLevel), default=TrustLevel.INFERRED)
    provenance = Column(JSON, default=dict)  # Source chain, citations

    # Versioning (don't overwrite, version instead)
    version = Column(Integer, default=1)
    parent_version_id = Column(String(64), nullable=True)  # Previous version's ID
    is_current = Column(Boolean, default=True)  # Is this the current version?

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)  # When moved to T4

    # Content hash for deduplication
    content_hash = Column(String(64), nullable=True)

    # Relationships
    versions = relationship("MemoryVersion", back_populates="memory_object",
                          foreign_keys="MemoryVersion.object_id")
    access_logs = relationship("AccessLog", back_populates="memory_object")

    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_tier_heat', 'current_tier', 'heat_score'),
        Index('idx_domain_tags', 'domain_tags', postgresql_using='gin'),
        Index('idx_valid_range', 'valid_from', 'valid_to'),
        Index('idx_content_hash', 'content_hash'),
        Index('idx_source', 'source_type', 'source_id'),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.content and not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    def to_dict(self, view="summary"):
        """
        Convert to dictionary with view-based filtering.

        Views:
        - snippet: Minimal data for context pack
        - summary: Summary + key metadata
        - raw: Full content and metadata
        """
        base = {
            'id': self.id,
            'object_type': self.object_type.value if self.object_type else None,
            'current_tier': self.current_tier.value if self.current_tier else None,
            'domain_tags': self.domain_tags or [],
            'trust_level': self.trust_level.value if self.trust_level else None,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'version': self.version,
            'is_current': self.is_current,
        }

        if view == "snippet":
            base['summary'] = self.summary[:500] if self.summary else None
            base['provenance'] = {'source_type': self.source_type}
        elif view == "summary":
            base['summary'] = self.summary
            base['provenance'] = self.provenance
            base['heat_score'] = self.heat_score
            base['access_count'] = self.access_count
        elif view == "raw":
            base['content'] = self.content
            base['summary'] = self.summary
            base['provenance'] = self.provenance
            base['heat_score'] = self.heat_score
            base['access_count'] = self.access_count
            base['source_id'] = self.source_id
            base['source_type'] = self.source_type
            base['created_at'] = self.created_at.isoformat() if self.created_at else None
            base['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
            base['is_pinned'] = self.is_pinned
            base['pinned_tier'] = self.pinned_tier.value if self.pinned_tier else None
            base['parent_version_id'] = self.parent_version_id
            base['content_hash'] = self.content_hash

        return base

    def update_heat(self, access_type="read", weight=1.0):
        """
        Update heat score based on access.

        Heat formula: heat = heat * decay^(days_since_last) + weight
        """
        now = datetime.utcnow()
        if self.last_accessed_at:
            days_elapsed = (now - self.last_accessed_at).total_seconds() / 86400
            self.heat_score = self.heat_score * (1 - self.decay_rate) ** days_elapsed

        self.heat_score += weight
        self.access_count += 1
        self.last_accessed_at = now

    def create_new_version(self, new_content, new_metadata=None):
        """Create a new version of this memory object (don't overwrite)."""
        new_obj = MemoryObject(
            object_type=self.object_type,
            content=new_content,
            domain_tags=self.domain_tags,
            source_type=self.source_type,
            source_id=self.source_id,
            current_tier=self.current_tier,
            trust_level=self.trust_level,
            provenance=new_metadata.get('provenance', self.provenance) if new_metadata else self.provenance,
            version=self.version + 1,
            parent_version_id=self.id,
            is_current=True,
            valid_from=datetime.utcnow(),
        )
        # Mark this version as no longer current
        self.is_current = False
        self.valid_to = datetime.utcnow()
        return new_obj


class MemoryVersion(Base):
    """
    Tracks version history for memory objects.
    Enables conflict resolution by keeping both old/new facts.
    """
    __tablename__ = 'memory_versions'

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    object_id = Column(String(64), ForeignKey('memory_objects.id'), nullable=False)
    version_number = Column(Integer, nullable=False)

    # Snapshot of content at this version
    content_snapshot = Column(Text, nullable=True)
    summary_snapshot = Column(Text, nullable=True)
    metadata_snapshot = Column(JSON, default=dict)

    # Change tracking
    change_type = Column(String(50))  # create, update, merge, correction
    change_reason = Column(Text, nullable=True)
    changed_by = Column(String(100), nullable=True)  # user/system identifier

    # Validity window at this version
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    memory_object = relationship("MemoryObject", back_populates="versions",
                                foreign_keys=[object_id])

    def to_dict(self):
        return {
            'id': self.id,
            'object_id': self.object_id,
            'version_number': self.version_number,
            'change_type': self.change_type,
            'change_reason': self.change_reason,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AccessLog(Base):
    """
    Tracks access patterns for heat scoring and analytics.
    Used for promotion/demotion decisions.
    """
    __tablename__ = 'access_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(String(64), ForeignKey('memory_objects.id'), nullable=False)

    access_type = Column(String(20))  # read, search_hit, write, pin
    access_source = Column(String(50))  # which tool/endpoint triggered access
    session_id = Column(String(64), nullable=True)

    # Context about the access
    query_context = Column(JSON, nullable=True)  # What query led to this access
    latency_ms = Column(Integer, nullable=True)  # Response time
    tier_at_access = Column(Enum(Tier), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    memory_object = relationship("MemoryObject", back_populates="access_logs")

    __table_args__ = (
        Index('idx_access_time', 'created_at'),
        Index('idx_session', 'session_id'),
    )


class AuditEvent(Base):
    """
    Immutable audit log for T4 tier.
    Append-only, never modified or deleted.
    Used for compliance, training data, and recovery.
    """
    __tablename__ = 'audit_events'

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    sequence_number = Column(Integer, autoincrement=True, unique=True)

    # Event identification
    event_type = Column(String(50), nullable=False)  # write, correction, archive, etc.
    event_source = Column(String(100))  # Which system/user triggered

    # Related objects
    object_id = Column(String(64), nullable=True)  # Related memory object
    object_snapshot = Column(JSON, nullable=True)  # Full state at event time

    # Event payload
    payload = Column(JSON, nullable=False)

    # Metadata
    session_id = Column(String(64), nullable=True)
    user_id = Column(String(100), nullable=True)

    # Immutability proof
    previous_hash = Column(String(64), nullable=True)  # Hash of previous event
    event_hash = Column(String(64), nullable=True)  # Hash of this event

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_audit_time', 'created_at'),
        Index('idx_audit_type', 'event_type'),
        Index('idx_audit_object', 'object_id'),
    )

    def compute_hash(self, previous_hash=None):
        """Compute hash for immutability chain."""
        data = json.dumps({
            'id': self.id,
            'event_type': self.event_type,
            'payload': self.payload,
            'previous_hash': previous_hash,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }, sort_keys=True)
        self.previous_hash = previous_hash
        self.event_hash = hashlib.sha256(data.encode()).hexdigest()
        return self.event_hash


class ContextPack(Base):
    """
    Pre-assembled context bundles for efficient retrieval.
    Token-budgeted, provenance-rich, conflict-aware.
    """
    __tablename__ = 'context_packs'

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(String(64), unique=True, nullable=False)

    # Content structure
    summary = Column(Text, nullable=True)  # "What you need to know" summary
    snippets = Column(JSON, default=list)  # Ranked snippets with citations
    structured_facts = Column(JSON, default=list)  # Extracted facts
    validity_notes = Column(JSON, default=list)  # Finance/engineering safety notes
    pointers = Column(JSON, default=list)  # IDs for deeper fetch

    # Token budgeting
    token_count = Column(Integer, default=0)
    token_budget = Column(Integer, default=4000)

    # Query context
    original_query = Column(Text, nullable=True)
    scope = Column(JSON, default=dict)  # Filters applied

    # Caching
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'request_id': self.request_id,
            'summary': self.summary,
            'snippets': self.snippets,
            'structured_facts': self.structured_facts,
            'validity_notes': self.validity_notes,
            'pointers': self.pointers,
            'token_count': self.token_count,
            'token_budget': self.token_budget,
            'original_query': self.original_query,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TrainingBatch(Base):
    """
    Training data manifests for continual learning.
    Aggregates deltas from event log for PEFT training.
    """
    __tablename__ = 'training_batches'

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Batch metadata
    batch_type = Column(String(50))  # episodic, semantic, procedural, replay
    status = Column(String(20), default="pending")  # pending, processing, complete, failed

    # Content references
    event_ids = Column(JSON, default=list)  # Audit events included
    object_ids = Column(JSON, default=list)  # Memory objects included

    # Training criteria
    criteria = Column(JSON, default=dict)  # Filters used to select data
    time_range_start = Column(DateTime, nullable=True)
    time_range_end = Column(DateTime, nullable=True)

    # Stats
    total_examples = Column(Integer, default=0)
    token_count = Column(Integer, default=0)

    # Output
    manifest_path = Column(String(500), nullable=True)  # Path to training manifest

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'batch_type': self.batch_type,
            'status': self.status,
            'total_examples': self.total_examples,
            'token_count': self.token_count,
            'criteria': self.criteria,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


# Session-level cache for T0 (in-memory only, not persisted)
class SessionCache:
    """
    T0 tier: In-context session memory.
    Purely in-memory, cleared on session end.
    Stores recent tool outputs, conversation summaries, active context.
    """

    def __init__(self, session_id, max_items=100, max_tokens=8000):
        self.session_id = session_id
        self.max_items = max_items
        self.max_tokens = max_tokens
        self.items = {}  # key -> value
        self.order = []  # LRU order
        self.token_count = 0
        self.created_at = datetime.utcnow()
        self.last_accessed = datetime.utcnow()

    def get(self, key):
        if key in self.items:
            # Move to end of LRU
            self.order.remove(key)
            self.order.append(key)
            self.last_accessed = datetime.utcnow()
            return self.items[key]
        return None

    def set(self, key, value, estimated_tokens=0):
        if key in self.items:
            self.order.remove(key)

        self.items[key] = value
        self.order.append(key)
        self.token_count += estimated_tokens
        self.last_accessed = datetime.utcnow()

        # Evict if over limits
        while len(self.order) > self.max_items or self.token_count > self.max_tokens:
            if not self.order:
                break
            evicted_key = self.order.pop(0)
            del self.items[evicted_key]

    def clear(self):
        self.items.clear()
        self.order.clear()
        self.token_count = 0

    def to_summary(self):
        """Create a summary for T1 promotion before session ends."""
        return {
            'session_id': self.session_id,
            'item_count': len(self.items),
            'token_count': self.token_count,
            'duration_seconds': (datetime.utcnow() - self.created_at).total_seconds(),
            'keys': list(self.items.keys())[:20],  # Sample of keys
        }
