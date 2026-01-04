# tiered_memory/tiers.py
"""
Tier Storage Backends for Tiered Memory System

Tier Architecture:
- T0: In-context (SessionCache, in-memory)
- T1: Hot cache (Redis or in-memory fallback, TTL-heavy)
- T2: Warm index (Postgres + pgvector, or SQLite for dev)
- T3: Cold lake (S3/MinIO or filesystem fallback)
- T4: Audit log (Append-only, immutable)

Configuration Profiles:
- Profile S: Single machine (in-memory/SQLite/filesystem)
- Profile C: Small cluster (Redis/Postgres/MinIO)
- Profile E: Enterprise (WORM storage, full RBAC)
"""

import os
import json
import hashlib
import pickle
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import OrderedDict
import threading
import logging

logger = logging.getLogger(__name__)


class TierBackend(ABC):
    """Abstract base class for tier storage backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[Dict]:
        """Retrieve an item by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """Store an item with optional TTL (seconds)."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete an item by key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        """Scan for keys matching pattern."""
        pass

    @abstractmethod
    def stats(self) -> Dict:
        """Return storage statistics."""
        pass


class InMemoryBackend(TierBackend):
    """
    In-memory storage backend for T0/T1 in Profile S.
    Thread-safe with TTL support and LRU eviction.
    """

    def __init__(self, max_items: int = 10000, default_ttl: int = 3600):
        self.max_items = max_items
        self.default_ttl = default_ttl
        self._store: OrderedDict = OrderedDict()
        self._ttls: Dict[str, datetime] = {}
        self._lock = threading.RLock()

    def _cleanup_expired(self):
        """Remove expired items."""
        now = datetime.utcnow()
        expired = [k for k, exp in self._ttls.items() if exp <= now]
        for key in expired:
            self._store.pop(key, None)
            self._ttls.pop(key, None)

    def _evict_if_needed(self):
        """Evict oldest items if over capacity."""
        while len(self._store) >= self.max_items:
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key, None)
            self._ttls.pop(oldest_key, None)

    def get(self, key: str) -> Optional[Dict]:
        with self._lock:
            self._cleanup_expired()
            if key in self._store:
                # Move to end (most recently used)
                self._store.move_to_end(key)
                return self._store[key]
            return None

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        with self._lock:
            self._cleanup_expired()
            self._evict_if_needed()

            self._store[key] = value
            self._store.move_to_end(key)

            ttl = ttl or self.default_ttl
            if ttl > 0:
                self._ttls[key] = datetime.utcnow() + timedelta(seconds=ttl)

            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                self._ttls.pop(key, None)
                return True
            return False

    def exists(self, key: str) -> bool:
        with self._lock:
            self._cleanup_expired()
            return key in self._store

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        with self._lock:
            self._cleanup_expired()
            import fnmatch
            keys = [k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)]
            return keys[:limit]

    def stats(self) -> Dict:
        with self._lock:
            return {
                'backend': 'in_memory',
                'item_count': len(self._store),
                'max_items': self.max_items,
                'ttl_count': len(self._ttls),
            }


class RedisBackend(TierBackend):
    """
    Redis storage backend for T1 in Profile C/E.
    Requires redis-py package.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 prefix: str = "tmem:", default_ttl: int = 3600):
        self.prefix = prefix
        self.default_ttl = default_ttl
        self._client = None
        self._redis_url = redis_url

    @property
    def client(self):
        if self._client is None:
            try:
                import redis
                self._client = redis.from_url(self._redis_url, decode_responses=False)
            except ImportError:
                logger.warning("redis package not installed, falling back to in-memory")
                return None
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def get(self, key: str) -> Optional[Dict]:
        if not self.client:
            return None
        data = self.client.get(self._key(key))
        if data:
            return json.loads(data)
        return None

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        if not self.client:
            return False
        ttl = ttl or self.default_ttl
        data = json.dumps(value)
        if ttl > 0:
            self.client.setex(self._key(key), ttl, data)
        else:
            self.client.set(self._key(key), data)
        return True

    def delete(self, key: str) -> bool:
        if not self.client:
            return False
        return bool(self.client.delete(self._key(key)))

    def exists(self, key: str) -> bool:
        if not self.client:
            return False
        return bool(self.client.exists(self._key(key)))

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        if not self.client:
            return []
        cursor = 0
        keys = []
        while len(keys) < limit:
            cursor, batch = self.client.scan(cursor, match=self._key(pattern), count=limit)
            keys.extend([k.decode().replace(self.prefix, '', 1) for k in batch])
            if cursor == 0:
                break
        return keys[:limit]

    def stats(self) -> Dict:
        if not self.client:
            return {'backend': 'redis', 'status': 'disconnected'}
        info = self.client.info('memory')
        return {
            'backend': 'redis',
            'used_memory': info.get('used_memory_human'),
            'connected_clients': info.get('connected_clients'),
        }


class SQLiteVectorBackend(TierBackend):
    """
    SQLite-based storage for T2 in Profile S.
    Uses SQLite with JSON storage for simple deployments.
    For production, use PostgresVectorBackend with pgvector.
    """

    def __init__(self, db_path: str = "memory_t2.db"):
        self.db_path = db_path
        self._engine = None
        self._Session = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from .models import Base

        self._engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        self._initialized = True

    def get(self, key: str) -> Optional[Dict]:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            obj = session.query(MemoryObject).filter_by(id=key).first()
            return obj.to_dict("raw") if obj else None
        finally:
            session.close()

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject, MemoryType, Tier, TrustLevel
        session = self._Session()
        try:
            obj = session.query(MemoryObject).filter_by(id=key).first()
            if obj:
                obj.content = value.get('content')
                obj.summary = value.get('summary')
                obj.domain_tags = value.get('domain_tags', [])
                obj.updated_at = datetime.utcnow()
            else:
                obj = MemoryObject(
                    id=key,
                    content=value.get('content'),
                    summary=value.get('summary'),
                    domain_tags=value.get('domain_tags', []),
                    object_type=MemoryType(value.get('object_type', 'semantic')),
                    current_tier=Tier(value.get('current_tier', 't2')),
                    source_type=value.get('source_type'),
                    source_id=value.get('source_id'),
                    provenance=value.get('provenance', {}),
                )
                session.add(obj)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"SQLite set error: {e}")
            return False
        finally:
            session.close()

    def delete(self, key: str) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            obj = session.query(MemoryObject).filter_by(id=key).first()
            if obj:
                session.delete(obj)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def exists(self, key: str) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            return session.query(MemoryObject).filter_by(id=key).count() > 0
        finally:
            session.close()

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            query = session.query(MemoryObject.id)
            if pattern != "*":
                # Convert glob pattern to SQL LIKE
                like_pattern = pattern.replace("*", "%").replace("?", "_")
                query = query.filter(MemoryObject.id.like(like_pattern))
            results = query.limit(limit).all()
            return [r[0] for r in results]
        finally:
            session.close()

    def stats(self) -> Dict:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            count = session.query(MemoryObject).count()
            return {
                'backend': 'sqlite',
                'db_path': self.db_path,
                'item_count': count,
            }
        finally:
            session.close()

    def search_vector(self, embedding: bytes, k: int = 10,
                      filters: Optional[Dict] = None) -> List[Tuple[str, float]]:
        """
        Vector similarity search (simplified for SQLite).
        For production, use pgvector or dedicated vector DB.
        """
        self._ensure_initialized()
        from .models import MemoryObject
        import numpy as np

        session = self._Session()
        try:
            query = session.query(MemoryObject).filter(
                MemoryObject.embedding.isnot(None)
            )

            if filters:
                if 'domain_tags' in filters:
                    # JSON containment (simplified)
                    for tag in filters['domain_tags']:
                        query = query.filter(
                            MemoryObject.domain_tags.contains(tag)
                        )

            results = []
            target = np.frombuffer(embedding, dtype=np.float32)

            for obj in query.all():
                if obj.embedding:
                    stored = np.frombuffer(obj.embedding, dtype=np.float32)
                    if len(stored) == len(target):
                        # Cosine similarity
                        similarity = np.dot(target, stored) / (
                            np.linalg.norm(target) * np.linalg.norm(stored)
                        )
                        results.append((obj.id, float(similarity)))

            # Sort by similarity descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

        finally:
            session.close()

    def search_keyword(self, query: str, k: int = 10,
                       filters: Optional[Dict] = None) -> List[str]:
        """Full-text search (simplified for SQLite)."""
        self._ensure_initialized()
        from .models import MemoryObject

        session = self._Session()
        try:
            q = session.query(MemoryObject).filter(
                MemoryObject.content.like(f"%{query}%") |
                MemoryObject.summary.like(f"%{query}%")
            )

            if filters:
                if 'domain_tags' in filters:
                    for tag in filters['domain_tags']:
                        q = q.filter(MemoryObject.domain_tags.contains(tag))
                if 'valid_at' in filters:
                    valid_at = filters['valid_at']
                    q = q.filter(
                        MemoryObject.valid_from <= valid_at,
                        (MemoryObject.valid_to >= valid_at) |
                        (MemoryObject.valid_to.is_(None))
                    )

            results = q.limit(k).all()
            return [obj.id for obj in results]

        finally:
            session.close()


class PostgresVectorBackend(TierBackend):
    """
    PostgreSQL + pgvector storage for T2 in Profile C/E.
    Provides full vector similarity search and full-text search.
    """

    def __init__(self, db_url: str, pool_size: int = 5):
        self.db_url = db_url
        self.pool_size = pool_size
        self._engine = None
        self._Session = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from .models import Base

        self._engine = create_engine(
            self.db_url,
            pool_size=self.pool_size,
            pool_recycle=3600
        )

        # Enable pgvector extension if available
        with self._engine.connect() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            except Exception:
                logger.warning("pgvector extension not available")

        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        self._initialized = True

    def get(self, key: str) -> Optional[Dict]:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            obj = session.query(MemoryObject).filter_by(id=key).first()
            return obj.to_dict("raw") if obj else None
        finally:
            session.close()

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject, MemoryType, Tier
        session = self._Session()
        try:
            obj = session.query(MemoryObject).filter_by(id=key).first()
            if obj:
                for k, v in value.items():
                    if hasattr(obj, k) and k not in ('id', 'created_at'):
                        setattr(obj, k, v)
                obj.updated_at = datetime.utcnow()
            else:
                obj = MemoryObject(id=key, **value)
                session.add(obj)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Postgres set error: {e}")
            return False
        finally:
            session.close()

    def delete(self, key: str) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            result = session.query(MemoryObject).filter_by(id=key).delete()
            session.commit()
            return result > 0
        finally:
            session.close()

    def exists(self, key: str) -> bool:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            return session.query(MemoryObject).filter_by(id=key).count() > 0
        finally:
            session.close()

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            query = session.query(MemoryObject.id)
            if pattern != "*":
                like_pattern = pattern.replace("*", "%").replace("?", "_")
                query = query.filter(MemoryObject.id.like(like_pattern))
            results = query.limit(limit).all()
            return [r[0] for r in results]
        finally:
            session.close()

    def stats(self) -> Dict:
        self._ensure_initialized()
        from .models import MemoryObject
        session = self._Session()
        try:
            count = session.query(MemoryObject).count()
            return {
                'backend': 'postgres',
                'item_count': count,
            }
        finally:
            session.close()


class FileSystemBackend(TierBackend):
    """
    Filesystem storage for T3 in Profile S.
    Stores objects as JSON files with directory sharding.
    """

    def __init__(self, base_path: str = "./data/t3"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _path(self, key: str) -> str:
        # Shard by first 2 chars of key hash
        h = hashlib.md5(key.encode()).hexdigest()
        shard_dir = os.path.join(self.base_path, h[:2])
        os.makedirs(shard_dir, exist_ok=True)
        return os.path.join(shard_dir, f"{key}.json")

    def get(self, key: str) -> Optional[Dict]:
        path = self._path(key)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return None

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        path = self._path(key)
        # Add metadata
        value['_stored_at'] = datetime.utcnow().isoformat()
        if ttl:
            value['_expires_at'] = (
                datetime.utcnow() + timedelta(seconds=ttl)
            ).isoformat()
        with open(path, 'w') as f:
            json.dump(value, f, indent=2, default=str)
        return True

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        import fnmatch
        keys = []
        for root, dirs, files in os.walk(self.base_path):
            for f in files:
                if f.endswith('.json'):
                    key = f[:-5]  # Remove .json
                    if fnmatch.fnmatch(key, pattern):
                        keys.append(key)
                        if len(keys) >= limit:
                            return keys
        return keys

    def stats(self) -> Dict:
        total_files = 0
        total_size = 0
        for root, dirs, files in os.walk(self.base_path):
            for f in files:
                if f.endswith('.json'):
                    total_files += 1
                    total_size += os.path.getsize(os.path.join(root, f))
        return {
            'backend': 'filesystem',
            'base_path': self.base_path,
            'item_count': total_files,
            'total_size_bytes': total_size,
        }


class S3Backend(TierBackend):
    """
    S3/MinIO storage for T3 in Profile C/E.
    Requires boto3 package.
    """

    def __init__(self, bucket: str, prefix: str = "memory/",
                 endpoint_url: Optional[str] = None,
                 region: str = "us-east-1"):
        self.bucket = bucket
        self.prefix = prefix
        self.endpoint_url = endpoint_url
        self.region = region
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url,
                    region_name=self.region
                )
            except ImportError:
                logger.warning("boto3 not installed, S3 backend unavailable")
                return None
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}.json"

    def get(self, key: str) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            return json.loads(response['Body'].read().decode())
        except Exception as e:
            logger.debug(f"S3 get error: {e}")
            return None

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        if not self.client:
            return False
        try:
            value['_stored_at'] = datetime.utcnow().isoformat()
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(key),
                Body=json.dumps(value, default=str),
                ContentType='application/json'
            )
            return True
        except Exception as e:
            logger.error(f"S3 set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception as e:
            logger.error(f"S3 delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        if not self.client:
            return []
        import fnmatch
        keys = []
        paginator = self.client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get('Contents', []):
                key = obj['Key'].replace(self.prefix, '').replace('.json', '')
                if fnmatch.fnmatch(key, pattern):
                    keys.append(key)
                    if len(keys) >= limit:
                        return keys
        return keys

    def stats(self) -> Dict:
        if not self.client:
            return {'backend': 's3', 'status': 'unavailable'}
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
            count = response.get('KeyCount', 0)
            return {
                'backend': 's3',
                'bucket': self.bucket,
                'prefix': self.prefix,
                'item_count': count,
            }
        except Exception as e:
            return {'backend': 's3', 'error': str(e)}


class AuditLogBackend(TierBackend):
    """
    Append-only audit log for T4.
    Immutable storage with hash chain for integrity.
    Uses filesystem by default, can be configured for WORM storage.
    """

    def __init__(self, base_path: str = "./data/audit", worm_enabled: bool = False):
        self.base_path = base_path
        self.worm_enabled = worm_enabled
        self._sequence = 0
        self._last_hash = None
        self._lock = threading.Lock()
        os.makedirs(base_path, exist_ok=True)
        self._load_sequence()

    def _load_sequence(self):
        """Load the current sequence number from the latest log file."""
        seq_file = os.path.join(self.base_path, ".sequence")
        if os.path.exists(seq_file):
            with open(seq_file, 'r') as f:
                data = json.load(f)
                self._sequence = data.get('sequence', 0)
                self._last_hash = data.get('last_hash')

    def _save_sequence(self):
        """Save the current sequence state."""
        seq_file = os.path.join(self.base_path, ".sequence")
        with open(seq_file, 'w') as f:
            json.dump({
                'sequence': self._sequence,
                'last_hash': self._last_hash
            }, f)

    def _log_path(self, date: datetime) -> str:
        """Get log file path for a given date."""
        return os.path.join(self.base_path, f"audit_{date.strftime('%Y%m%d')}.jsonl")

    def get(self, key: str) -> Optional[Dict]:
        """Get is expensive on audit log - search through files."""
        for root, dirs, files in os.walk(self.base_path):
            for f in sorted(files, reverse=True):  # Most recent first
                if f.startswith('audit_') and f.endswith('.jsonl'):
                    with open(os.path.join(root, f), 'r') as log:
                        for line in log:
                            try:
                                entry = json.loads(line)
                                if entry.get('id') == key:
                                    return entry
                            except json.JSONDecodeError:
                                continue
        return None

    def set(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """Append to audit log (ignores key, auto-assigns)."""
        return self.append(value)

    def append(self, event: Dict) -> bool:
        """Append an event to the audit log."""
        with self._lock:
            self._sequence += 1
            now = datetime.utcnow()

            # Build the audit entry
            entry = {
                'id': event.get('id', str(self._sequence)),
                'sequence': self._sequence,
                'timestamp': now.isoformat(),
                'previous_hash': self._last_hash,
                **event
            }

            # Compute hash chain
            entry_str = json.dumps(entry, sort_keys=True, default=str)
            entry['hash'] = hashlib.sha256(entry_str.encode()).hexdigest()
            self._last_hash = entry['hash']

            # Append to log file
            log_path = self._log_path(now)
            with open(log_path, 'a') as f:
                f.write(json.dumps(entry, default=str) + '\n')

            self._save_sequence()

            # Make immutable if WORM enabled
            if self.worm_enabled:
                os.chmod(log_path, 0o444)

            return True

    def delete(self, key: str) -> bool:
        """Audit logs are immutable - delete is not allowed."""
        logger.warning("Attempted to delete from audit log - operation not permitted")
        return False

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def scan(self, pattern: str = "*", limit: int = 100) -> List[str]:
        """Scan recent audit entries."""
        import fnmatch
        keys = []
        for root, dirs, files in os.walk(self.base_path):
            for f in sorted(files, reverse=True):
                if f.startswith('audit_') and f.endswith('.jsonl'):
                    with open(os.path.join(root, f), 'r') as log:
                        for line in log:
                            try:
                                entry = json.loads(line)
                                key = entry.get('id', '')
                                if fnmatch.fnmatch(key, pattern):
                                    keys.append(key)
                                    if len(keys) >= limit:
                                        return keys
                            except json.JSONDecodeError:
                                continue
        return keys

    def stats(self) -> Dict:
        total_entries = 0
        total_size = 0
        for root, dirs, files in os.walk(self.base_path):
            for f in files:
                if f.startswith('audit_') and f.endswith('.jsonl'):
                    path = os.path.join(root, f)
                    total_size += os.path.getsize(path)
                    with open(path, 'r') as log:
                        total_entries += sum(1 for _ in log)
        return {
            'backend': 'audit_log',
            'base_path': self.base_path,
            'entry_count': total_entries,
            'total_size_bytes': total_size,
            'current_sequence': self._sequence,
            'worm_enabled': self.worm_enabled,
        }

    def verify_chain(self, start_seq: int = 1, end_seq: Optional[int] = None) -> Dict:
        """Verify the integrity of the hash chain."""
        end_seq = end_seq or self._sequence
        entries = []
        errors = []

        # Collect all entries in sequence order
        for root, dirs, files in os.walk(self.base_path):
            for f in sorted(files):
                if f.startswith('audit_') and f.endswith('.jsonl'):
                    with open(os.path.join(root, f), 'r') as log:
                        for line in log:
                            try:
                                entry = json.loads(line)
                                seq = entry.get('sequence', 0)
                                if start_seq <= seq <= end_seq:
                                    entries.append(entry)
                            except json.JSONDecodeError:
                                continue

        entries.sort(key=lambda x: x.get('sequence', 0))

        # Verify chain
        prev_hash = None
        for entry in entries:
            if entry.get('previous_hash') != prev_hash:
                errors.append({
                    'sequence': entry.get('sequence'),
                    'error': 'previous_hash mismatch'
                })
            prev_hash = entry.get('hash')

        return {
            'verified_count': len(entries),
            'error_count': len(errors),
            'errors': errors[:10],  # First 10 errors
            'chain_valid': len(errors) == 0,
        }


class TierManager:
    """
    Manages the tier storage backends and provides unified access.
    Configurable for different deployment profiles.
    """

    def __init__(self, profile: str = "S", config: Optional[Dict] = None):
        """
        Initialize tier manager with deployment profile.

        Profiles:
        - S: Single machine (in-memory, SQLite, filesystem)
        - C: Cluster (Redis, Postgres, S3)
        - E: Enterprise (like C, with WORM and enhanced audit)
        """
        self.profile = profile
        self.config = config or {}
        self._backends: Dict[str, TierBackend] = {}
        self._session_caches: Dict[str, 'SessionCache'] = {}
        self._lock = threading.Lock()

        self._initialize_backends()

    def _initialize_backends(self):
        """Initialize tier backends based on profile."""
        from .models import SessionCache

        if self.profile == "S":
            # Single machine profile
            self._backends['t1'] = InMemoryBackend(
                max_items=self.config.get('t1_max_items', 10000),
                default_ttl=self.config.get('t1_ttl', 3600)
            )
            self._backends['t2'] = SQLiteVectorBackend(
                db_path=self.config.get('t2_db_path', 'data/memory_t2.db')
            )
            self._backends['t3'] = FileSystemBackend(
                base_path=self.config.get('t3_path', 'data/t3')
            )
            self._backends['t4'] = AuditLogBackend(
                base_path=self.config.get('t4_path', 'data/audit'),
                worm_enabled=False
            )

        elif self.profile == "C":
            # Cluster profile
            self._backends['t1'] = RedisBackend(
                redis_url=self.config.get('redis_url', 'redis://localhost:6379/0'),
                default_ttl=self.config.get('t1_ttl', 3600)
            )
            self._backends['t2'] = PostgresVectorBackend(
                db_url=self.config.get('postgres_url', 'postgresql://localhost/memory'),
                pool_size=self.config.get('pg_pool_size', 5)
            )
            self._backends['t3'] = S3Backend(
                bucket=self.config.get('s3_bucket', 'memory-lake'),
                endpoint_url=self.config.get('s3_endpoint'),
                prefix=self.config.get('s3_prefix', 'memory/')
            )
            self._backends['t4'] = AuditLogBackend(
                base_path=self.config.get('t4_path', 'data/audit'),
                worm_enabled=False
            )

        elif self.profile == "E":
            # Enterprise profile
            self._backends['t1'] = RedisBackend(
                redis_url=self.config.get('redis_url', 'redis://localhost:6379/0'),
                default_ttl=self.config.get('t1_ttl', 3600)
            )
            self._backends['t2'] = PostgresVectorBackend(
                db_url=self.config.get('postgres_url', 'postgresql://localhost/memory'),
                pool_size=self.config.get('pg_pool_size', 10)
            )
            self._backends['t3'] = S3Backend(
                bucket=self.config.get('s3_bucket', 'memory-lake'),
                endpoint_url=self.config.get('s3_endpoint'),
                prefix=self.config.get('s3_prefix', 'memory/')
            )
            self._backends['t4'] = AuditLogBackend(
                base_path=self.config.get('t4_path', 'data/audit'),
                worm_enabled=self.config.get('worm_enabled', True)
            )

    def get_session(self, session_id: str) -> 'SessionCache':
        """Get or create a T0 session cache."""
        from .models import SessionCache
        with self._lock:
            if session_id not in self._session_caches:
                self._session_caches[session_id] = SessionCache(
                    session_id=session_id,
                    max_items=self.config.get('t0_max_items', 100),
                    max_tokens=self.config.get('t0_max_tokens', 8000)
                )
            return self._session_caches[session_id]

    def close_session(self, session_id: str) -> Optional[Dict]:
        """
        Close a session and return its summary for T1 promotion.
        """
        with self._lock:
            if session_id in self._session_caches:
                session = self._session_caches.pop(session_id)
                return session.to_summary()
        return None

    def get_tier(self, tier: str) -> TierBackend:
        """Get a specific tier backend."""
        if tier not in self._backends:
            raise ValueError(f"Unknown tier: {tier}")
        return self._backends[tier]

    def stats(self) -> Dict:
        """Get statistics for all tiers."""
        stats = {
            'profile': self.profile,
            'active_sessions': len(self._session_caches),
        }
        for tier, backend in self._backends.items():
            stats[tier] = backend.stats()
        return stats
