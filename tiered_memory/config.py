# tiered_memory/config.py
"""
Configuration Profiles for Tiered Memory System

Profiles:
- Profile S: Single machine lab (in-memory, SQLite, filesystem)
- Profile C: Small cluster (Valkey, Postgres, S3/MinIO)
- Profile E: Enterprise (WORM storage, RBAC, full audit)

Each profile defines:
- Tier backend configurations
- Promotion/demotion thresholds
- TTL and capacity settings
- Compaction policies
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TierConfig:
    """Configuration for a single tier."""
    backend: str  # Backend type: in_memory, redis, sqlite, postgres, filesystem, s3
    max_items: int = 10000
    default_ttl: int = 3600  # seconds
    connection_string: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromotionConfig:
    """Configuration for promotion policies."""
    heat_threshold_t3_t2: float = 5.0  # Heat score to promote cold→warm
    heat_threshold_t2_t1: float = 20.0  # Heat score to promote warm→hot
    session_repeat_window: int = 60  # Seconds for burst detection
    session_repeat_count: int = 3  # Accesses to trigger burst promotion


@dataclass
class DemotionConfig:
    """Configuration for demotion policies."""
    hours_t1_t2: int = 24  # Hours without access before T1→T2
    days_t2_t3: int = 7  # Days without access before T2→T3
    enable_auto_archive: bool = False  # Auto-archive to T4 based on age
    archive_after_days: int = 90  # Days before auto-archive


@dataclass
class CompactionConfig:
    """Configuration for compaction during tier transitions."""
    t1_summary_max_length: int = 500  # Max chars for T1 summaries
    t2_keep_raw_content: bool = True  # Keep raw content in T2
    t3_compress_content: bool = False  # Compress content in T3
    dedupe_on_compaction: bool = True  # Deduplicate by content hash


@dataclass
class MemoryProfile:
    """Complete configuration profile for the memory system."""
    name: str
    description: str

    # Tier configurations
    t0: TierConfig  # Session cache (always in-memory)
    t1: TierConfig  # Hot cache
    t2: TierConfig  # Warm index
    t3: TierConfig  # Cold lake
    t4: TierConfig  # Audit log

    # Policies
    promotion: PromotionConfig = field(default_factory=PromotionConfig)
    demotion: DemotionConfig = field(default_factory=DemotionConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)

    # Feature flags
    enable_vector_search: bool = True
    enable_keyword_search: bool = True
    enable_versioning: bool = True
    enable_audit_chain: bool = True
    worm_enabled: bool = False  # Write-Once-Read-Many for audit

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TierManager."""
        return {
            # T0 config
            't0_max_items': self.t0.max_items,
            't0_max_tokens': self.t0.extra.get('max_tokens', 8000),

            # T1 config
            't1_max_items': self.t1.max_items,
            't1_ttl': self.t1.default_ttl,
            'valkey_url': self.t1.connection_string,

            # T2 config
            't2_db_path': self.t2.connection_string or 'data/memory_t2.db',
            'postgres_url': self.t2.connection_string if 'postgres' in self.t2.backend else None,
            'pg_pool_size': self.t2.extra.get('pool_size', 5),

            # T3 config
            't3_path': self.t3.connection_string or 'data/t3',
            's3_bucket': self.t3.extra.get('bucket'),
            's3_endpoint': self.t3.extra.get('endpoint'),
            's3_prefix': self.t3.extra.get('prefix', 'memory/'),

            # T4 config
            't4_path': self.t4.connection_string or 'data/audit',
            'worm_enabled': self.worm_enabled,

            # Promotion thresholds
            'heat_threshold_t3_t2': self.promotion.heat_threshold_t3_t2,
            'heat_threshold_t2_t1': self.promotion.heat_threshold_t2_t1,

            # Demotion thresholds
            'demotion_hours_t1_t2': self.demotion.hours_t1_t2,
            'demotion_days_t2_t3': self.demotion.days_t2_t3,
        }


# =============================================================================
# Pre-defined Profiles
# =============================================================================

def get_profile_s(base_path: str = "data") -> MemoryProfile:
    """
    Profile S: Single machine lab environment.

    - T0: In-process session cache
    - T1: In-memory LRU cache with TTL
    - T2: SQLite with simple vector storage
    - T3: Local filesystem
    - T4: Local append-only log files

    Best for: Development, testing, single-user deployment
    """
    return MemoryProfile(
        name="S",
        description="Single machine profile for development and small deployments",

        t0=TierConfig(
            backend="in_memory",
            max_items=100,
            extra={'max_tokens': 8000}
        ),

        t1=TierConfig(
            backend="in_memory",
            max_items=10000,
            default_ttl=3600  # 1 hour
        ),

        t2=TierConfig(
            backend="sqlite",
            max_items=100000,
            connection_string=os.path.join(base_path, "memory_t2.db")
        ),

        t3=TierConfig(
            backend="filesystem",
            connection_string=os.path.join(base_path, "t3")
        ),

        t4=TierConfig(
            backend="audit_log",
            connection_string=os.path.join(base_path, "audit")
        ),

        promotion=PromotionConfig(
            heat_threshold_t3_t2=5.0,
            heat_threshold_t2_t1=20.0
        ),

        demotion=DemotionConfig(
            hours_t1_t2=24,
            days_t2_t3=7
        ),

        compaction=CompactionConfig(
            t1_summary_max_length=500,
            t2_keep_raw_content=True
        ),

        enable_vector_search=True,
        enable_keyword_search=True,
        enable_versioning=True,
        enable_audit_chain=True,
        worm_enabled=False
    )


def get_profile_c(
    valkey_url: str = "redis://localhost:6379/0",
    postgres_url: str = "postgresql://localhost/memory",
    s3_bucket: str = "memory-lake",
    s3_endpoint: Optional[str] = None,  # MinIO endpoint
    base_path: str = "data"
) -> MemoryProfile:
    """
    Profile C: Small cluster environment.

    - T0: In-process session cache
    - T1: Valkey cluster with TTL
    - T2: PostgreSQL + pgvector + full-text search
    - T3: S3/MinIO object storage
    - T4: Append-only audit logs

    Best for: Multi-user, multi-instance deployments
    """
    return MemoryProfile(
        name="C",
        description="Cluster profile for multi-instance deployments",

        t0=TierConfig(
            backend="in_memory",
            max_items=100,
            extra={'max_tokens': 8000}
        ),

        t1=TierConfig(
            backend="valkey",
            max_items=50000,
            default_ttl=3600,
            connection_string=valkey_url
        ),

        t2=TierConfig(
            backend="postgres",
            max_items=1000000,
            connection_string=postgres_url,
            extra={'pool_size': 5}
        ),

        t3=TierConfig(
            backend="s3",
            connection_string=s3_endpoint,
            extra={
                'bucket': s3_bucket,
                'endpoint': s3_endpoint,
                'prefix': 'memory/'
            }
        ),

        t4=TierConfig(
            backend="audit_log",
            connection_string=os.path.join(base_path, "audit")
        ),

        promotion=PromotionConfig(
            heat_threshold_t3_t2=3.0,  # More aggressive promotion
            heat_threshold_t2_t1=15.0
        ),

        demotion=DemotionConfig(
            hours_t1_t2=48,  # Larger warm tier
            days_t2_t3=14
        ),

        compaction=CompactionConfig(
            t1_summary_max_length=500,
            t2_keep_raw_content=True
        ),

        enable_vector_search=True,
        enable_keyword_search=True,
        enable_versioning=True,
        enable_audit_chain=True,
        worm_enabled=False
    )


def get_profile_e(
    valkey_url: str = "redis://localhost:6379/0",
    postgres_url: str = "postgresql://localhost/memory",
    s3_bucket: str = "memory-lake",
    s3_endpoint: Optional[str] = None,
    audit_path: str = "/var/log/memory-audit"
) -> MemoryProfile:
    """
    Profile E: Enterprise environment.

    - T0: In-process session cache
    - T1: Valkey cluster with TTL
    - T2: PostgreSQL + pgvector with connection pooling
    - T3: S3 with versioning enabled
    - T4: WORM-compliant audit logs with hash chain

    Best for: Compliance-heavy environments (finance, healthcare)
    """
    return MemoryProfile(
        name="E",
        description="Enterprise profile with full compliance and audit",

        t0=TierConfig(
            backend="in_memory",
            max_items=100,
            extra={'max_tokens': 8000}
        ),

        t1=TierConfig(
            backend="valkey",
            max_items=100000,
            default_ttl=7200,  # 2 hours
            connection_string=valkey_url
        ),

        t2=TierConfig(
            backend="postgres",
            max_items=5000000,
            connection_string=postgres_url,
            extra={'pool_size': 10}
        ),

        t3=TierConfig(
            backend="s3",
            connection_string=s3_endpoint,
            extra={
                'bucket': s3_bucket,
                'endpoint': s3_endpoint,
                'prefix': 'memory/',
                'versioning': True
            }
        ),

        t4=TierConfig(
            backend="audit_log",
            connection_string=audit_path,
            extra={'worm': True}
        ),

        promotion=PromotionConfig(
            heat_threshold_t3_t2=5.0,
            heat_threshold_t2_t1=25.0  # Higher bar for hot cache
        ),

        demotion=DemotionConfig(
            hours_t1_t2=72,  # Slower demotion
            days_t2_t3=30,  # Keep in warm longer
            enable_auto_archive=True,
            archive_after_days=365
        ),

        compaction=CompactionConfig(
            t1_summary_max_length=1000,
            t2_keep_raw_content=True,
            t3_compress_content=True
        ),

        enable_vector_search=True,
        enable_keyword_search=True,
        enable_versioning=True,
        enable_audit_chain=True,
        worm_enabled=True
    )


# =============================================================================
# Profile Factory
# =============================================================================

def get_profile(
    name: str = "S",
    **kwargs
) -> MemoryProfile:
    """
    Get a configuration profile by name.

    Args:
        name: Profile name (S, C, or E)
        **kwargs: Override parameters for the profile

    Returns:
        MemoryProfile configuration
    """
    profiles = {
        'S': get_profile_s,
        'C': get_profile_c,
        'E': get_profile_e
    }

    if name.upper() not in profiles:
        raise ValueError(f"Unknown profile: {name}. Available: S, C, E")

    return profiles[name.upper()](**kwargs)


def get_profile_from_env() -> MemoryProfile:
    """
    Get profile configuration from environment variables.

    Environment variables:
    - MEMORY_PROFILE: Profile name (S, C, E)
    - MEMORY_BASE_PATH: Base path for local storage
    - MEMORY_VALKEY_URL: Valkey connection URL (falls back to MEMORY_REDIS_URL)
    - MEMORY_POSTGRES_URL: PostgreSQL connection URL
    - MEMORY_S3_BUCKET: S3 bucket name
    - MEMORY_S3_ENDPOINT: S3/MinIO endpoint URL
    - MEMORY_AUDIT_PATH: Path for audit logs
    """
    profile_name = os.environ.get('MEMORY_PROFILE', 'S')
    base_path = os.environ.get('MEMORY_BASE_PATH', 'data')

    kwargs = {'base_path': base_path}

    if profile_name.upper() in ('C', 'E'):
        kwargs['valkey_url'] = os.environ.get(
            'MEMORY_VALKEY_URL',
            os.environ.get('MEMORY_REDIS_URL', 'redis://localhost:6379/0')
        )
        kwargs['postgres_url'] = os.environ.get(
            'MEMORY_POSTGRES_URL', 'postgresql://localhost/memory'
        )
        kwargs['s3_bucket'] = os.environ.get('MEMORY_S3_BUCKET', 'memory-lake')
        kwargs['s3_endpoint'] = os.environ.get('MEMORY_S3_ENDPOINT')

    if profile_name.upper() == 'E':
        kwargs['audit_path'] = os.environ.get(
            'MEMORY_AUDIT_PATH', '/var/log/memory-audit'
        )

    return get_profile(profile_name, **kwargs)
