
from enum import Enum


class Intent(str, Enum):
    WITHDRAWAL_ISSUE = "withdrawal_issue"
    DEPOSIT_ISSUE = "deposit_issue"
    LOGIN_ACCESS = "login_access"
    VERIFICATION_KYC = "verification_kyc"
    ACCOUNT_RESTRICTION = "account_restriction"
    PRODUCT_BEHAVIOR = "product_behavior"
    PRIVACY_REQUEST = "privacy_request"
    STATEMENT_EXPORT = "statement_export"
    API_SUPPORT = "api_support"
    OTHER = "other"


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Sentiment(str, Enum):
    CALM = "calm"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    NEUTRAL = "neutral"


class InternalQueue(str, Enum):
    GENERAL_SUPPORT = "General Support"
    PAYMENTS = "Payments"
    COMPLIANCE = "Compliance"
    RISK = "Risk"
    ENGINEERING = "Engineering"
    PRODUCT = "Product"
    PRIVACY = "Privacy"
    DEVELOPER_SUPPORT = "Developer Support"


class ReplySafetyLabel(str, Enum):
    SAFE_TO_SEND_AFTER_REVIEW = "safe_to_send_after_review"
    NEEDS_SPECIALIST_REVIEW = "needs_specialist_review"
    NEEDS_LEGAL_OR_COMPLIANCE_REVIEW = (
        "needs_legal_or_compliance_review"
    )


class PipelineState(str, Enum):
    INIT = "INIT"
    TICKETS_LOADED = "TICKETS_LOADED"
    PREPROCESSING_COMPLETE = "PREPROCESSING_COMPLETE"
    TICKETS_CLASSIFIED = "TICKETS_CLASSIFIED"
    KB_RETRIEVAL_COMPLETE = "KB_RETRIEVAL_COMPLETE"
    PRIORITY_SCORES_COMPUTED = "PRIORITY_SCORES_COMPUTED"
    ROUTING_COMPLETE = "ROUTING_COMPLETE"
    REPLY_DRAFTS_GENERATED = "REPLY_DRAFTS_GENERATED"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    RESULTS_FINALISED = "RESULTS_FINALISED"
