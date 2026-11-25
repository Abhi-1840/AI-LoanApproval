"""
AI Engine & Token Usage Monitoring Module for AI Loan Approval System.

Responsibilities:
- Extract exact token counts from LangChain / Gemini response metadata without estimation.
- Classify every user turn across 4 clear processing paths:
    1. local_rules          -> Processed entirely by deterministic Python rules
    2. gemini_primary       -> Successfully handled by primary Gemini model
    3. gemini_secondary     -> Successfully handled by secondary Gemini fallback model
    4. local_error_fallback -> Fell back to local processing after Gemini error or unavailability
- Track session-level and cumulative project-level counters with unique request_id idempotency.
- Persist telemetry cleanly to Firebase RTDB (when configured) with an atomic local JSON store.
- Never log API keys, Firebase secrets, full prompts, or customer PII/KYC/financial data.
- Never fabricate remaining API quota or billing/cost figures.
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

import requests

MAX_RECENT_REQUESTS = 25
MAX_PROCESSED_REQUEST_IDS = 300

ENGINE_LABELS = {
    "local_rules": "Local Python Rules",
    "gemini_primary": "Primary Gemini Model",
    "gemini_secondary": "Secondary Gemini Model",
    "local_error_fallback": "Local Error Fallback",
}


def sanitize_firebase_key(key):
    """Replace Firebase RTDB forbidden key characters (. $ # [ ] /)."""
    if not key:
        return "default_session"
    return re.sub(r"[.$#\[\]/\s]+", "_", str(key).strip())[:120]


def sanitize_error_reason(raw_error):
    """Return a concise, secret-free failure reason safe for telemetry & UI display."""
    if not raw_error:
        return None
    msg = str(raw_error)
    # Redact URL query keys / bearer tokens / Google API keys
    msg = re.sub(r"AIza[0-9A-Za-z\-_]{20,}", "[REDACTED_KEY]", msg)
    msg = re.sub(r"([?&](?:key|auth|api_key)=)[^&\s]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)
    msg = re.sub(r"\s+", " ", msg).strip()

    lower = msg.lower()
    if any(tok in lower for tok in ("429", "resourceexhausted", "quota", "rate limit", "rate_limit", "exhausted")):
        return "Gemini API quota / rate limit exceeded"
    if any(tok in lower for tok in ("timed out", "timeout", "deadlineexceeded", "deadline exceeded")):
        return "Gemini API request timed out"
    if any(tok in lower for tok in ("api key not valid", "permissiondenied", "unauthenticated", "401", "403")):
        return "Gemini API authentication / permission error"
    if any(tok in lower for tok in ("notfound", "not found", "404", "is not found for api version")):
        return "Configured Gemini model unavailable / not found"
    if any(tok in lower for tok in ("connection", "dns", "name resolution", "network", "unreachable", "503", "500")):
        return "Gemini API network or service unreachable"

    # Generic truncated message (safe ASCII/UTF-8 summary)
    return msg[:140] + ("..." if len(msg) > 140 else "")


def classify_intent_category(user_input, routing_flags=None):
    """
    Derive a privacy-safe coarse intent category without storing raw user text or PII.
    """
    flags = routing_flags or {}
    if flags.get("is_onboarding_active") or flags.get("is_onboarding_trigger"):
        return "onboarding"
    if flags.get("is_cust_id"):
        return "kyc_lookup"
    if flags.get("is_verified_and_amount"):
        return "loan_amount_underwrite"
    if flags.get("is_logout"):
        return "session_reset"
    if flags.get("is_structured_query"):
        t = (user_input or "").lower()
        if "emi" in t:
            return "emi_inquiry"
        if "document" in t or "doc" in t:
            return "documents_inquiry"
        if "limit" in t or "profile" in t:
            return "profile_limit_check"
        return "eligibility_inquiry"
    return "general_conversation"


def extract_gemini_token_usage(ai_message):
    """
    Extract exact actual token usage from a LangChain AIMessage / Gemini response.
    Priority:
      1. ai_message.usage_metadata (populated by langchain-google-genai _response_to_result)
      2. ai_message.response_metadata fallback keys if present
    Never fabricates or estimates token counts when unavailable.
    """
    if ai_message is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "metadata_available": False,
        }

    usage = getattr(ai_message, "usage_metadata", None)
    resp_meta = getattr(ai_message, "response_metadata", None) or {}

    def _to_int(val):
        try:
            v = int(val)
            return v if v > 0 else 0
        except (TypeError, ValueError):
            return 0

    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cache_read_tokens = 0
    found = False

    if isinstance(usage, dict):
        input_tokens = _to_int(usage.get("input_tokens") or usage.get("prompt_token_count"))
        output_tokens = _to_int(usage.get("output_tokens") or usage.get("candidates_token_count"))
        total_tokens = _to_int(usage.get("total_tokens") or usage.get("total_token_count"))
        details = usage.get("input_token_details")
        if isinstance(details, dict):
            cache_read_tokens = _to_int(details.get("cache_read"))
        found = (input_tokens + output_tokens + total_tokens) > 0
    elif usage is not None:
        input_tokens = _to_int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_token_count", 0))
        output_tokens = _to_int(getattr(usage, "output_tokens", 0) or getattr(usage, "candidates_token_count", 0))
        total_tokens = _to_int(getattr(usage, "total_tokens", 0) or getattr(usage, "total_token_count", 0))
        details = getattr(usage, "input_token_details", None)
        if isinstance(details, dict):
            cache_read_tokens = _to_int(details.get("cache_read"))
        found = (input_tokens + output_tokens + total_tokens) > 0

    if not found and isinstance(resp_meta, dict):
        # Inspect alternative response_metadata wrappers if usage_metadata was absent
        candidate = (
            resp_meta.get("usage_metadata")
            or resp_meta.get("token_usage")
            or resp_meta
        )
        if isinstance(candidate, dict):
            input_tokens = _to_int(
                candidate.get("input_tokens")
                or candidate.get("prompt_token_count")
                or candidate.get("prompt_tokens")
            )
            output_tokens = _to_int(
                candidate.get("output_tokens")
                or candidate.get("candidates_token_count")
                or candidate.get("completion_tokens")
            )
            total_tokens = _to_int(
                candidate.get("total_tokens")
                or candidate.get("total_token_count")
            )
            cache_read_tokens = _to_int(candidate.get("cached_content_token_count"))
            found = (input_tokens + output_tokens + total_tokens) > 0

    if total_tokens == 0 and (input_tokens + output_tokens) > 0:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": cache_read_tokens,
        "metadata_available": found,
    }


def _empty_metrics_bucket():
    """Create a fresh metrics bucket for either global or single-session scope."""
    return {
        "tokens": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
        },
        "requests": {
            "total_user_messages": 0,
            "gemini_api_requests": 0,
            "gemini_success_count": 0,
            "gemini_failure_count": 0,
        },
        "breakdown": {
            "local_rules": 0,
            "gemini_primary": 0,
            "gemini_secondary": 0,
            "local_error_fallback": 0,
        },
        "latency": {
            "total_ms": 0.0,
            "count": 0,
            "latest_ms": 0.0,
            "gemini_total_ms": 0.0,
            "gemini_count": 0,
            "local_total_ms": 0.0,
            "local_count": 0,
        },
        "last_engine": None,
        "last_engine_label": "No requests yet",
        "last_model_used": None,
        "last_gemini_success_at": None,
        "fallback_reason": None,
        "recent_requests": [],
    }


def _ensure_bucket_shape(bucket):
    """Safely normalize any loaded dict into expected bucket schema."""
    base = _empty_metrics_bucket()
    if not isinstance(bucket, dict):
        return base
    for section in ("tokens", "requests", "breakdown", "latency"):
        if isinstance(bucket.get(section), dict):
            base[section].update(bucket[section])
    for key in (
        "last_engine",
        "last_engine_label",
        "last_model_used",
        "last_gemini_success_at",
        "fallback_reason",
    ):
        if key in bucket:
            base[key] = bucket[key]
    if isinstance(bucket.get("recent_requests"), list):
        base["recent_requests"] = bucket["recent_requests"][:MAX_RECENT_REQUESTS]
    return base


def _compute_view_summary(bucket):
    """Build derived percentages and averages for frontend rendering."""
    b = _ensure_bucket_shape(bucket)
    reqs = b["requests"]
    brk = b["breakdown"]
    lat = b["latency"]

    total_msgs = int(reqs.get("total_user_messages", 0) or 0)
    gemini_msgs = int(brk.get("gemini_primary", 0)) + int(brk.get("gemini_secondary", 0))
    local_msgs = int(brk.get("local_rules", 0)) + int(brk.get("local_error_fallback", 0))

    if total_msgs > 0:
        gemini_pct = round((gemini_msgs / total_msgs) * 100.0, 1)
        local_pct = round((local_msgs / total_msgs) * 100.0, 1)
        dist_pct = {
            "local_rules": round((brk["local_rules"] / total_msgs) * 100.0, 1),
            "gemini_primary": round((brk["gemini_primary"] / total_msgs) * 100.0, 1),
            "gemini_secondary": round((brk["gemini_secondary"] / total_msgs) * 100.0, 1),
            "local_error_fallback": round((brk["local_error_fallback"] / total_msgs) * 100.0, 1),
        }
    else:
        gemini_pct = 0.0
        local_pct = 0.0
        dist_pct = {
            "local_rules": 0.0,
            "gemini_primary": 0.0,
            "gemini_secondary": 0.0,
            "local_error_fallback": 0.0,
        }

    avg_ms = round(lat["total_ms"] / lat["count"], 1) if lat["count"] > 0 else 0.0
    gemini_avg_ms = round(lat["gemini_total_ms"] / lat["gemini_count"], 1) if lat["gemini_count"] > 0 else 0.0
    local_avg_ms = round(lat["local_total_ms"] / lat["local_count"], 1) if lat["local_count"] > 0 else 0.0

    return {
        "tokens": dict(b["tokens"]),
        "requests": dict(reqs),
        "breakdown": dict(brk),
        "percentages": {
            "gemini_pct": gemini_pct,
            "local_pct": local_pct,
            "distribution": dist_pct,
        },
        "latency": {
            "latest_ms": round(float(lat.get("latest_ms", 0.0) or 0.0), 1),
            "avg_ms": avg_ms,
            "gemini_avg_ms": gemini_avg_ms,
            "local_avg_ms": local_avg_ms,
        },
        "last_engine": b.get("last_engine"),
        "last_engine_label": b.get("last_engine_label"),
        "last_model_used": b.get("last_model_used"),
        "last_gemini_success_at": b.get("last_gemini_success_at"),
        "fallback_reason": b.get("fallback_reason"),
        "recent_requests": list(b.get("recent_requests", [])),
    }


class AIMonitoringStore:
    """
    Thread-safe monitoring store supporting:
    - Session-level & all-time telemetry aggregation
    - Unique request_id deduplication (idempotent writes)
    - Hybrid persistence: Firebase RTDB (when configured) + atomic local JSON cache
    """

    def __init__(
        self,
        local_path="monitoring_stats.json",
        firebase_db_url="",
        firebase_api_key="",
        configured_model="",
        active_model="",
        secondary_model="gemini-3.5-flash-lite",
        llm_available=False,
        init_error=None,
    ):
        self._lock = threading.RLock()
        self.local_path = local_path
        self.firebase_db_url = (firebase_db_url or "").rstrip("/")
        self.firebase_api_key = firebase_api_key or ""

        self.configured_model = configured_model or active_model or "unconfigured"
        self.active_model = active_model or configured_model or "unconfigured"
        self.secondary_model = secondary_model
        self.llm_available = bool(llm_available)
        self.init_error = sanitize_error_reason(init_error)

        self.global_bucket = _empty_metrics_bucket()
        self.sessions = {}
        self.processed_request_ids = []

        # Live runtime engine status (updated cleanly from actual requests)
        self.gemini_status = "ACTIVE" if self.llm_available else ("ERROR" if self.init_error else "INACTIVE")
        self.local_fallback_status = "STANDBY" if self.llm_available else "ACTIVE"
        self.last_fallback_reason = (
            self.init_error if self.init_error else (None if self.llm_available else "Gemini API key not configured")
        )

        self.load()

    def has_processed(self, request_id):
        """Check whether a unique request_id has already been recorded."""
        if not request_id:
            return False
        with self._lock:
            return str(request_id) in self.processed_request_ids

    def update_runtime_config(
        self,
        firebase_db_url=None,
        firebase_api_key=None,
        configured_model=None,
        active_model=None,
        secondary_model=None,
        llm_available=None,
        init_error=None,
    ):
        """Sync runtime configuration changes (useful when config changes or in tests)."""
        with self._lock:
            if firebase_db_url is not None:
                self.firebase_db_url = firebase_db_url.rstrip("/")
            if firebase_api_key is not None:
                self.firebase_api_key = firebase_api_key
            if configured_model is not None:
                self.configured_model = configured_model
            if active_model is not None:
                self.active_model = active_model
            if secondary_model is not None:
                self.secondary_model = secondary_model
            if llm_available is not None:
                self.llm_available = bool(llm_available)
                self.init_error = sanitize_error_reason(init_error)
                if not self.llm_available:
                    self.gemini_status = "ERROR" if self.init_error else "INACTIVE"
                    self.local_fallback_status = "ACTIVE"
                    self.last_fallback_reason = self.init_error or "Gemini API key not configured / unavailable"
                elif self.gemini_status != "ERROR":
                    self.gemini_status = "ACTIVE"
                    self.local_fallback_status = "STANDBY"
                    if self.last_fallback_reason == "Gemini API key not configured / unavailable":
                        self.last_fallback_reason = None

    def _firebase_url(self, subpath):
        if not self.firebase_db_url:
            return None
        url = f"{self.firebase_db_url}/monitoring/{subpath}.json"
        if self.firebase_api_key:
            url += f"?auth={self.firebase_api_key}"
        return url

    def _apply_loaded_state(self, raw):
        if not isinstance(raw, dict):
            return False
        self.global_bucket = _ensure_bucket_shape(raw.get("global"))
        raw_sessions = raw.get("sessions")
        if isinstance(raw_sessions, dict):
            self.sessions = {
                k: _ensure_bucket_shape(v) for k, v in raw_sessions.items() if isinstance(v, dict)
            }
        ids = raw.get("processed_request_ids")
        if isinstance(ids, list):
            self.processed_request_ids = [str(x) for x in ids[-MAX_PROCESSED_REQUEST_IDS:]]
        return True

    def load(self):
        """Load persisted stats: try Firebase RTDB first (when configured), else local JSON."""
        with self._lock:
            loaded_from_firebase = False
            if self.firebase_db_url:
                try:
                    # Build exact root path without double slash
                    root_url = f"{self.firebase_db_url}/monitoring.json"
                    if self.firebase_api_key:
                        root_url += f"?auth={self.firebase_api_key}"
                    resp = requests.get(root_url, timeout=3)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict):
                            loaded_from_firebase = self._apply_loaded_state(data)
                except Exception:
                    loaded_from_firebase = False

            if not loaded_from_firebase and self.local_path and os.path.exists(self.local_path):
                try:
                    with open(self.local_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._apply_loaded_state(data)
                except Exception:
                    pass

            # Restore latest persisted timestamps/fallback reason if runtime has none yet
            if self.llm_available:
                # Startup health reflects live configured LLM state; historical errors shouldn't block fresh server start
                if self.global_bucket.get("last_engine") == "local_error_fallback":
                    # Preserve historical reason for inspection without marking live startup unhealthy unless latest failed
                    pass

    def _persist_local(self):
        if not self.local_path:
            return
        payload = {
            "global": self.global_bucket,
            "sessions": self.sessions,
            "processed_request_ids": self.processed_request_ids[-MAX_PROCESSED_REQUEST_IDS:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp_path = f"{self.local_path}.tmp.{os.getpid()}"
        try:
            parent = os.path.dirname(os.path.abspath(self.local_path))
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.local_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _persist_firebase(self, safe_session_id):
        if not self.firebase_db_url:
            return
        try:
            global_url = self._firebase_url("global")
            if global_url:
                requests.put(global_url, json=self.global_bucket, timeout=3)
            if safe_session_id and safe_session_id in self.sessions:
                sess_url = self._firebase_url(f"sessions/{safe_session_id}")
                if sess_url:
                    requests.put(sess_url, json=self.sessions[safe_session_id], timeout=3)
            ids_url = self._firebase_url("processed_request_ids")
            if ids_url:
                requests.put(ids_url, json=self.processed_request_ids[-MAX_PROCESSED_REQUEST_IDS:], timeout=3)
        except Exception:
            # Never crash chat flow if Firebase RTDB is temporarily unreachable
            pass

    def record_event(
        self,
        session_id,
        engine_category,
        latency_ms,
        request_id=None,
        intent_category="general_conversation",
        model_used=None,
        token_usage=None,
        gemini_attempts=0,
        gemini_failures=0,
        gemini_successes=0,
        fallback_reason=None,
    ):
        """
        Idempotently record a single user-request monitoring event across session & global scopes.
        Returns True if recorded, False if request_id was already recorded (duplicate protection).
        """
        if engine_category not in ENGINE_LABELS:
            engine_category = "local_rules"

        req_id = str(request_id or uuid.uuid4())
        safe_sess_id = sanitize_firebase_key(session_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_reason = sanitize_error_reason(fallback_reason)
        lat_val = round(max(0.0, float(latency_ms or 0.0)), 1)

        tokens = token_usage or {}
        in_tok = int(tokens.get("input_tokens", 0) or 0)
        out_tok = int(tokens.get("output_tokens", 0) or 0)
        tot_tok = int(tokens.get("total_tokens", 0) or 0)
        cache_tok = int(tokens.get("cache_read_tokens", 0) or 0)

        # Strict guarantee: local processing NEVER counts as Gemini tokens
        is_gemini_engine = engine_category in ("gemini_primary", "gemini_secondary")
        if not is_gemini_engine:
            in_tok = 0
            out_tok = 0
            tot_tok = 0
            cache_tok = 0

        with self._lock:
            if req_id in self.processed_request_ids:
                return False

            self.processed_request_ids.append(req_id)
            if len(self.processed_request_ids) > MAX_PROCESSED_REQUEST_IDS:
                self.processed_request_ids = self.processed_request_ids[-MAX_PROCESSED_REQUEST_IDS:]

            # Update live engine status cleanly
            if engine_category in ("gemini_primary", "gemini_secondary"):
                self.gemini_status = "ACTIVE"
                self.local_fallback_status = "STANDBY"
                self.last_fallback_reason = (
                    f"Primary failed; served by secondary ({clean_reason})" if (engine_category == "gemini_secondary" and clean_reason) else None
                )
            elif engine_category == "local_error_fallback":
                self.local_fallback_status = "ACTIVE"
                if not self.llm_available and not clean_reason:
                    clean_reason = self.init_error or "Gemini API unavailable / not configured"
                if not self.llm_available and not self.init_error:
                    self.gemini_status = "INACTIVE"
                else:
                    self.gemini_status = "ERROR"
                self.last_fallback_reason = clean_reason or "Gemini API error; fell back to local processing"
            else:
                # Deterministic local_rules execution
                if not self.llm_available:
                    self.gemini_status = "ERROR" if self.init_error else "INACTIVE"
                    self.local_fallback_status = "ACTIVE"
                    self.last_fallback_reason = clean_reason or self.init_error or "Gemini API key not configured"
                else:
                    # Leave existing gemini error state untouched if last Gemini failed, otherwise ACTIVE/STANDBY
                    if self.gemini_status != "ERROR":
                        self.gemini_status = "ACTIVE"
                        self.local_fallback_status = "STANDBY"
                        self.last_fallback_reason = clean_reason

            entry = {
                "request_id": req_id,
                "timestamp": now_iso,
                "session_id": safe_sess_id,
                "intent_category": str(intent_category or "general_conversation"),
                "engine_category": engine_category,
                "engine_label": ENGINE_LABELS[engine_category],
                "model_used": model_used or ("local_master_agent" if not is_gemini_engine else self.active_model),
                "gemini_attempts": int(gemini_attempts or 0),
                "gemini_failures": int(gemini_failures or 0),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot_tok,
                "latency_ms": lat_val,
                "fallback_reason": clean_reason,
            }

            sess_bucket = self.sessions.setdefault(safe_sess_id, _empty_metrics_bucket())
            for bucket in (self.global_bucket, sess_bucket):
                bucket["tokens"]["input_tokens"] += in_tok
                bucket["tokens"]["output_tokens"] += out_tok
                bucket["tokens"]["total_tokens"] += tot_tok
                bucket["tokens"]["cache_read_tokens"] += cache_tok

                bucket["requests"]["total_user_messages"] += 1
                bucket["requests"]["gemini_api_requests"] += int(gemini_attempts or 0)
                bucket["requests"]["gemini_success_count"] += int(gemini_successes or 0)
                bucket["requests"]["gemini_failure_count"] += int(gemini_failures or 0)

                bucket["breakdown"][engine_category] += 1

                bucket["latency"]["total_ms"] = round(bucket["latency"]["total_ms"] + lat_val, 2)
                bucket["latency"]["count"] += 1
                bucket["latency"]["latest_ms"] = lat_val

                if is_gemini_engine:
                    bucket["latency"]["gemini_total_ms"] = round(bucket["latency"]["gemini_total_ms"] + lat_val, 2)
                    bucket["latency"]["gemini_count"] += 1
                    bucket["last_gemini_success_at"] = now_iso
                else:
                    bucket["latency"]["local_total_ms"] = round(bucket["latency"]["local_total_ms"] + lat_val, 2)
                    bucket["latency"]["local_count"] += 1

                bucket["last_engine"] = engine_category
                bucket["last_engine_label"] = ENGINE_LABELS[engine_category]
                bucket["last_model_used"] = entry["model_used"]
                bucket["fallback_reason"] = clean_reason

                bucket["recent_requests"].insert(0, entry)
                bucket["recent_requests"] = bucket["recent_requests"][:MAX_RECENT_REQUESTS]

            self._persist_local()
            self._persist_firebase(safe_sess_id)
            return True

    def get_snapshot(self, session_id=None):
        """Return safe, complete telemetry snapshot for both current session and all-time."""
        with self._lock:
            safe_sess_id = sanitize_firebase_key(session_id) if session_id else None
            sess_bucket = self.sessions.get(safe_sess_id) if safe_sess_id else None

            global_summary = _compute_view_summary(self.global_bucket)
            session_summary = _compute_view_summary(sess_bucket) if sess_bucket else _compute_view_summary(_empty_metrics_bucket())

            persistence_mode = "firebase+local" if self.firebase_db_url else "local_json"

            return {
                "engine_status": {
                    "gemini_status": self.gemini_status,
                    "local_fallback_status": self.local_fallback_status,
                    "active_model": self.active_model,
                    "configured_model": self.configured_model,
                    "secondary_model": self.secondary_model,
                    "last_engine": global_summary["last_engine"],
                    "last_engine_label": global_summary["last_engine_label"],
                    "last_model_used": global_summary["last_model_used"],
                    "last_gemini_success_at": global_summary["last_gemini_success_at"],
                    "latest_latency_ms": global_summary["latency"]["latest_ms"],
                    "fallback_reason": self.last_fallback_reason,
                    "persistence_mode": persistence_mode,
                    "quota_source_note": "Gemini API does not expose account quota. Check Google AI Studio for official RPM/TPM/RPD limits.",
                },
                "session_id": safe_sess_id,
                "session": session_summary,
                "all_time": global_summary,
            }
