# Triển khai Normalizer LLM-Only

## 1. Tổng quan

Chuyển Normalizer từ hybrid (rule + LLM) sang **LLM-only**: mọi query đều qua LLM, không còn rule-based path. Fallback tối thiểu khi LLM lỗi.

---

## 2. Thay đổi chính

| Hiện tại | LLM-Only |
|----------|-----------|
| `normalizer_use_llm=False` → rule path | Luôn LLM |
| `normalizer_use_llm=True` → LLM, fallback rule | Luôn LLM, fallback minimal |
| SKIP_RETRIEVAL_PATTERN pre-check | LLM quyết định social |
| Rule: INTENT_PATTERNS, _infer_* | Bỏ, LLM output đủ |

---

## 3. Flow mới

```
normalize(query, conversation_history, source_lang)
    │
    ▼
_normalize_llm(query, conversation_history, source_lang)
    │
    ├─► Success → return QuerySpec
    │
    └─► Fail (exception, invalid JSON)
            │
            ▼
        _build_minimal_fallback(query, source_lang)
            → QuerySpec mặc định (informational, generic_profile)
```

---

## 4. Chi tiết triển khai

### 4.1 Sửa `normalize()` trong `normalizer.py`

```python
async def normalize(
    query: str,
    conversation_history: list[dict[str, str]] | None = None,
    locale: str | None = None,
    source_lang: str | None = None,
) -> QuerySpec:
    """Produce QuerySpec from raw query. LLM-only; minimal fallback on error."""
    q_stripped = query.strip()
    spec = await _normalize_llm(q_stripped, conversation_history, source_lang)
    if spec is not None:
        return spec
    logger.warning("normalizer_llm_fallback", reason="llm_failed", query_preview=q_stripped[:80])
    return _build_minimal_fallback(q_stripped, source_lang)
```

### 4.2 Thêm `_build_minimal_fallback()`

```python
def _build_minimal_fallback(query: str, source_lang: str | None = None) -> QuerySpec:
    """Minimal QuerySpec when LLM fails. Ensures pipeline continues."""
    q = query.strip()
    lang = (source_lang or "en").strip().lower() or "en"
    return QuerySpec(
        intent="informational",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[q],
        semantic_queries=[q],
        clarifying_questions=[],
        is_ambiguous=False,
        skip_retrieval=False,
        canned_response=None,
        original_query=q,
        source_lang=lang,
        translation_needed=False,
        user_goal="general_info",
        resolved_slots={},
        missing_slots=[],
        answerable_without_clarification=True,
        hard_requirements=[],
        soft_requirements=[],
        retrieval_profile="generic_profile",
        rewrite_candidates=[q],
        answer_mode_hint="strong",
        extraction_mode="llm_fallback",
        config_overrides_applied=[],
    )
```

### 4.3 Mở rộng prompt LLM (optional, tăng chất lượng)

Thêm vào output schema trong prompt:

```json
{
  ...
  "user_goal": "price_lookup|order_link|refund_policy|setup_steps|feature_compare|general_info",
  "retrieval_profile": "pricing_profile|policy_profile|troubleshooting_profile|comparison_profile|account_profile|generic_profile"
}
```

Nếu LLM trả thêm 2 field này, dùng trực tiếp; không thì giữ logic `_infer_user_goal`, `_infer_retrieval_profile` trong `_build_query_spec`.

### 4.4 Giữ `_normalize_llm()` và `_build_query_spec()`

- `_normalize_llm()`: giữ nguyên logic gọi LLM, parse JSON, validate.
- `_build_query_spec()`: giữ để điền các field phái sinh (user_goal, hard/soft requirements, rewrite_candidates, ...) từ output LLM.
- Các helper `_infer_user_goal`, `_split_requirements`, `_build_rewrite_candidates`, ...: giữ để `_build_query_spec` dùng khi LLM không trả đủ.

### 4.5 Xóa / deprecate

| Item | Hành động |
|------|------------|
| `SKIP_RETRIEVAL_PATTERN` pre-check trong `normalize()` | Xóa |
| `_normalize_rule_based()` | Xóa hoặc đổi tên thành `_normalize_rule_based_deprecated` (chỉ dùng khi cần rollback) |
| `normalizer_use_llm` config | Deprecate hoặc bỏ (luôn True) |
| `INTENT_PATTERNS`, `_infer_intent`, `_infer_minimal_required_evidence` (dùng cho rule path) | Giữ nếu `_build_query_spec` còn dùng khi LLM thiếu field; nếu không thì xóa |

---

## 5. Config

### 5.1 `app/core/config.py`

```python
# Deprecate hoặc đổi ý nghĩa
normalizer_use_llm: bool = Field(
    default=True,  # Đổi default thành True
    description="[Deprecated] Normalizer is now LLM-only. Kept for config compatibility.",
)
```

Hoặc xóa `normalizer_use_llm` nếu không cần tương thích.

### 5.2 Env

```
# Không cần thay đổi nếu giữ config
NORMALIZER_USE_LLM=true   # hoặc bỏ biến
```

---

## 6. Fallback khi LLM lỗi

| Lỗi | Hành động |
|-----|-----------|
| LLM timeout / network | Retry 1 lần → fail → `_build_minimal_fallback()` |
| JSON invalid | `_build_minimal_fallback()` |
| Thiếu field bắt buộc | Điền default trong `_normalize_llm` (intent=informational, ...) |

---

## 7. Test

### 7.1 Cập nhật test hiện tại

- `tests/test_normalizer.py`: bỏ test rule path, thêm mock LLM cho LLM-only.
- Test fallback: mock LLM raise → assert `extraction_mode="llm_fallback"`.

### 7.2 Test cases

| Case | Input | Expected |
|------|-------|----------|
| Social | "hi" | skip_retrieval=True, intent=social |
| Transactional | "VPS price" | intent=transactional, retrieval_profile=pricing_profile |
| Policy | "refund policy" | intent=policy, required_evidence có policy_language |
| Tiếng Việt | "giá VPS bao nhiêu" | canonical_query_en có bản dịch |
| LLM fail | (mock raise) | extraction_mode=llm_fallback, intent=informational |

---

## 8. Thứ tự triển khai

1. Thêm `_build_minimal_fallback()`.
2. Sửa `normalize()` thành LLM-only + fallback.
3. Xóa SKIP_RETRIEVAL_PATTERN pre-check.
4. Xóa hoặc deprecate `_normalize_rule_based()`.
5. Cập nhật config `normalizer_use_llm` default=True hoặc bỏ.
6. Cập nhật test.
7. (Optional) Mở rộng prompt với user_goal, retrieval_profile.

---

## 9. Rollback

Nếu cần rollback:

1. Khôi phục `normalize()` cũ (có branch rule/LLM).
2. Set `normalizer_use_llm=false` trong env.
3. Giữ `_normalize_rule_based()` nếu chưa xóa hẳn.

---

## 10. Tóm tắt

| Thay đổi | File |
|----------|------|
| `normalize()` → LLM-only | normalizer.py |
| `_build_minimal_fallback()` | normalizer.py |
| Xóa pre-check, rule path | normalizer.py |
| Config normalizer_use_llm | config.py |
| Test | tests/test_normalizer.py |

Ước lượng: 1–2 ngày triển khai + test.
