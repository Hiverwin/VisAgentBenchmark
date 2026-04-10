"""Public host integration contracts for widget SDK."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


def new_request_id(prefix: str = "req") -> str:
    """Create a stable-looking request id for tracing."""
    return f"{prefix}_{uuid4().hex[:12]}"


def new_session_id(prefix: str = "sess") -> str:
    """Create a stable-looking session id for host runtime."""
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class AnalysisRequest:
    """Input contract for one widget analysis request."""

    query: str
    vega_spec: Dict[str, Any]
    model_name: Optional[str] = None
    input_mode: str = "text_and_image"
    max_iterations: int = 6
    chart_type: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=new_request_id)


@dataclass
class AnalysisResult:
    """Output contract returned to host VA systems."""

    request_id: str
    query: str
    success: bool
    answer: str
    tool_calls: List[Dict[str, Any]]
    final_observation: Dict[str, Any]
    chart_type: str
    mode: str = "protocol"
    error: str = ""
    stop_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_result: Optional[Dict[str, Any]] = None


@dataclass
class SessionStartRequest:
    """Input contract for starting a persistent analysis session."""

    vega_spec: Dict[str, Any]
    model_name: Optional[str] = None
    input_mode: str = "text_and_image"
    max_iterations: int = 6
    chart_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=new_session_id)


@dataclass
class SessionContinueRequest:
    """Input contract for continuing a started analysis session."""

    session_id: str
    query: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=new_request_id)
    model_name: Optional[str] = None
    input_mode: Optional[str] = None
    max_iterations: Optional[int] = None

