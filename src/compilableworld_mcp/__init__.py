"""Read-only Model Context Protocol adapter for CompilableWorld.

The core service has no dependency on the MCP SDK.  ``server.py`` adds the
optional FastMCP transport adapter when the ``mcp`` extra is installed.
"""

from .contracts import (
    MCP_READONLY_CONTRACT,
    MCPWorldError,
    RUNTIME_REHYDRATION_CONTRACT,
    SESSION_REHYDRATION_CONTRACT,
)
from .audit import MCP_AUDIT_ENVELOPE_CONTRACT, MCPAuditEnvelope, build_audit_envelope
from .audit_store import AUDIT_ANCHOR_CONTRACT, AUDIT_STORE_CONTRACT, AuditAnchor, AuditRecord, AuditStore, AuditStoreError
from .acl import WorldACL, WorldAccessGrant
from .asgi_middleware import ASGIAuthMiddleware, ASGI_MIDDLEWARE_CONTRACT
from .action_gateway import ACTION_RESULT_CONTRACT, SecureActionMCPGateway, receipt_projection
from .action_ledger import (
    ACTION_RESERVATION_CONTRACT,
    ActionReservationError,
    ActionReservationRecord,
    ActionReservationStore,
    RESERVATION_STATUS_COMPLETED,
    RESERVATION_STATUS_FAILED,
    RESERVATION_STATUS_RESERVED,
)
from .action_journal import (
    ACTION_COMMIT_JOURNAL_CONTRACT,
    ActionCommitJournalError,
    ActionCommitJournalRecord,
    ActionCommitJournalStore,
    JOURNAL_STATUS_FAILED,
    JOURNAL_STATUS_OUTBOX_ENQUEUED,
    JOURNAL_STATUS_PREPARED,
    JOURNAL_STATUS_RUNTIME_COMMITTED,
)
from .auth_pipeline import (
    AuthenticatedRequest,
    MCP_AUTHENTICATED_REQUEST_CONTRACT,
    RequestSecurityPipeline,
)
from .http_transport import (
    DEFAULT_SESSION_TOKEN_HEADER,
    HTTP_REQUEST_CONTEXT_CONTRACT,
    HTTPRequestContextAdapter,
)
from .fastmcp_transport import FASTMCP_CONTEXT_TRANSPORT_CONTRACT, FastMCPContextAdapter
from .secure_gateway import (
    DEFAULT_TIMELINE_ID,
    SECURE_READONLY_GATEWAY_CONTRACT,
    SecureReadOnlyMCPGateway,
)
from .secure_host import (
    SECURE_HOST_CONTRACT,
    SecureHostConfigError,
    SecureMCPHostSettings,
    serve_secure_mcp_streamable_http,
)
from .request_security import (
    MCP_REQUEST_SECURITY_CONTRACT,
    RequestAuthContext,
    RequestContextProvider,
    RequestSecurityError,
)
from .revocation import PrincipalJTIRevocationStore, RevocationCheckingPrincipalResolver
from .outbox import (
    OUTBOX_CONTRACT,
    OUTBOX_STATUS_ACKED,
    OUTBOX_STATUS_CLAIMED,
    OUTBOX_STATUS_PENDING,
    OutboxError,
    OutboxRecord,
    TransactionalOutbox,
)
from .oidc import OIDC_ALGORITHM, OIDC_CONTRACT, OIDCDiscoveryClient, OIDCDiscoveryDocument, OIDCPrincipalResolver
from .rate_limit import RateLimitDecision, SlidingWindowRateLimiter
from .migration_registry import (
    MCP_MIGRATION_CONTRACT,
    MigrationRegistry,
    MigrationRegistryError,
    MigrationStep,
)
from .runtime_ownership import (
    LEASE_STATUS_ACTIVE,
    LEASE_STATUS_EXPIRED,
    LEASE_STATUS_RELEASED,
    RUNTIME_OWNERSHIP_CONTRACT,
    RuntimeLeaseGrant,
    RuntimeOwnershipHeartbeat,
    RuntimeOwnershipError,
    RuntimeOwnershipLeaseStore,
    RuntimeOwnershipRecord,
)
from .runtime_bindings import (
    RUNTIME_BINDING_CONTRACT,
    RuntimeBindingError,
    RuntimeBindingRecord,
    RuntimeBindingStore,
)
from .runtime_coordination import (
    RUNTIME_COORDINATION_CONTRACT,
    RUNTIME_COORDINATION_LEADER_INSTANCE_ID,
    RUNTIME_COORDINATION_LEADER_WORLD_ID,
    RUNTIME_COORDINATION_PATH_PREFIX,
    RuntimeCoordinationASGIApp,
    RuntimeCoordinationGateway,
    build_runtime_coordination_asgi_app,
)
from .runtime_event_outbox import RUNTIME_EVENT_OUTBOX_CONTRACT, RuntimeEventOutboxBridge
from .runtime_durability import (
    RUNTIME_DURABILITY_CONTRACT,
    RuntimeCommitProjection,
    RuntimeDurabilityError,
    RuntimeDurabilityStore,
)
from .runtime_quorum import RUNTIME_QUORUM_CONTRACT, RuntimeQuorumError, RuntimeQuorumGate, RuntimeQuorumTerm
from .security import (
    BearerPrincipalResolver,
    HMACKeyRing,
    PrincipalTokenCodec,
    SessionGrant,
    SessionTokenCodec,
    TrustedPrincipal,
)
from .session_store import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_CLOSED,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    SESSION_STATUS_ROTATED,
    SessionLifecycleRecord,
    SessionLifecycleStore,
)
from .service import ReadOnlyWorldService
from .stdio_transport import STDIO_TRANSPORT_CONTRACT, StdioContextAdapter

__all__ = [
    "MCP_READONLY_CONTRACT",
    "MCP_AUDIT_ENVELOPE_CONTRACT",
    "MCPAuditEnvelope",
    "build_audit_envelope",
    "AUDIT_STORE_CONTRACT",
    "AUDIT_ANCHOR_CONTRACT",
    "AuditAnchor",
    "AuditRecord",
    "AuditStore",
    "AuditStoreError",
    "MCP_REQUEST_SECURITY_CONTRACT",
    "MCP_AUTHENTICATED_REQUEST_CONTRACT",
    "MCPWorldError",
    "SESSION_REHYDRATION_CONTRACT",
    "RUNTIME_REHYDRATION_CONTRACT",
    "ReadOnlyWorldService",
    "STDIO_TRANSPORT_CONTRACT",
    "StdioContextAdapter",
    "WorldACL",
    "WorldAccessGrant",
    "ASGIAuthMiddleware",
    "ASGI_MIDDLEWARE_CONTRACT",
    "ACTION_RESULT_CONTRACT",
    "SecureActionMCPGateway",
    "receipt_projection",
    "ACTION_RESERVATION_CONTRACT",
    "ActionReservationError",
    "ActionReservationRecord",
    "ActionReservationStore",
    "RESERVATION_STATUS_COMPLETED",
    "RESERVATION_STATUS_FAILED",
    "RESERVATION_STATUS_RESERVED",
    "ACTION_COMMIT_JOURNAL_CONTRACT",
    "ActionCommitJournalError",
    "ActionCommitJournalRecord",
    "ActionCommitJournalStore",
    "JOURNAL_STATUS_FAILED",
    "JOURNAL_STATUS_OUTBOX_ENQUEUED",
    "JOURNAL_STATUS_PREPARED",
    "JOURNAL_STATUS_RUNTIME_COMMITTED",
    "AuthenticatedRequest",
    "RequestSecurityPipeline",
    "DEFAULT_SESSION_TOKEN_HEADER",
    "HTTP_REQUEST_CONTEXT_CONTRACT",
    "HTTPRequestContextAdapter",
    "FASTMCP_CONTEXT_TRANSPORT_CONTRACT",
    "FastMCPContextAdapter",
    "DEFAULT_TIMELINE_ID",
    "SECURE_READONLY_GATEWAY_CONTRACT",
    "SecureReadOnlyMCPGateway",
    "SECURE_HOST_CONTRACT",
    "SecureHostConfigError",
    "SecureMCPHostSettings",
    "serve_secure_mcp_streamable_http",
    "BearerPrincipalResolver",
    "HMACKeyRing",
    "PrincipalTokenCodec",
    "RequestAuthContext",
    "RequestContextProvider",
    "RequestSecurityError",
    "PrincipalJTIRevocationStore",
    "RevocationCheckingPrincipalResolver",
    "OUTBOX_CONTRACT",
    "OUTBOX_STATUS_ACKED",
    "OUTBOX_STATUS_CLAIMED",
    "OUTBOX_STATUS_PENDING",
    "OutboxError",
    "OutboxRecord",
    "TransactionalOutbox",
    "OIDC_ALGORITHM",
    "OIDC_CONTRACT",
    "OIDCDiscoveryClient",
    "OIDCDiscoveryDocument",
    "OIDCPrincipalResolver",
    "RateLimitDecision",
    "SlidingWindowRateLimiter",
    "MCP_MIGRATION_CONTRACT",
    "MigrationRegistry",
    "MigrationRegistryError",
    "MigrationStep",
    "LEASE_STATUS_ACTIVE",
    "LEASE_STATUS_EXPIRED",
    "LEASE_STATUS_RELEASED",
    "RUNTIME_OWNERSHIP_CONTRACT",
    "RuntimeLeaseGrant",
    "RuntimeOwnershipHeartbeat",
    "RuntimeOwnershipError",
    "RuntimeOwnershipLeaseStore",
    "RuntimeOwnershipRecord",
    "RUNTIME_BINDING_CONTRACT",
    "RuntimeBindingError",
    "RuntimeBindingRecord",
    "RuntimeBindingStore",
    "RUNTIME_COORDINATION_CONTRACT",
    "RUNTIME_COORDINATION_LEADER_INSTANCE_ID",
    "RUNTIME_COORDINATION_LEADER_WORLD_ID",
    "RUNTIME_COORDINATION_PATH_PREFIX",
    "RuntimeCoordinationASGIApp",
    "RuntimeCoordinationGateway",
    "build_runtime_coordination_asgi_app",
    "RUNTIME_EVENT_OUTBOX_CONTRACT",
    "RuntimeEventOutboxBridge",
    "RUNTIME_DURABILITY_CONTRACT",
    "RuntimeCommitProjection",
    "RuntimeDurabilityError",
    "RuntimeDurabilityStore",
    "RUNTIME_QUORUM_CONTRACT",
    "RuntimeQuorumError",
    "RuntimeQuorumGate",
    "RuntimeQuorumTerm",
    "SessionGrant",
    "SessionTokenCodec",
    "TrustedPrincipal",
    "SESSION_STATUS_ACTIVE",
    "SESSION_STATUS_CLOSED",
    "SESSION_STATUS_EXPIRED",
    "SESSION_STATUS_REVOKED",
    "SESSION_STATUS_ROTATED",
    "SessionLifecycleRecord",
    "SessionLifecycleStore",
]
