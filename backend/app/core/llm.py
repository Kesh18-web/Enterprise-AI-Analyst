"""
LLM Factory — Direct dispatch using verified models (DeepSeek V4/V3, Groq Llama 3.3 70B, Gemini 2.5 Flash)
and content extraction utilities.
"""
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel

from backend.app.core.config import settings
from backend.app.core.logging import logger

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from langchain_openai import ChatOpenAI  # used for Groq and OpenRouter DeepSeek
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def extract_text_content(content: Any) -> str:
    """
    Safely extract plain text from an LLM response.content property.
    Handles plain strings as well as multi-part list-of-dicts.
    """
    if not content:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(item["text"])
                elif "text" in item:
                    text_parts.append(str(item["text"]))
            elif isinstance(item, str):
                text_parts.append(item)
        if text_parts:
            return "\n".join(text_parts).strip()
    return str(content).strip()


def _build_groq_70b_model(temperature: float = 0.0, max_tokens: Optional[int] = None) -> Optional[BaseChatModel]:
    """Helper to build Groq Llama 3.3 70B model instance."""
    if settings.GROQ_API_KEY and HAS_OPENAI:
        try:
            return ChatOpenAI(
                model="openai/gpt-oss-120b",
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=0,
            )
        except Exception as e:
            logger.error(f"[LLM Factory] Failed to build Groq 70B model: {e}")
    return None


def _build_deepseek_model(temperature: float = 0.0, max_tokens: Optional[int] = None) -> Optional[BaseChatModel]:
    """Helper to build DeepSeek V4 / V3 reasoning model instance via OpenRouter or DeepSeek Native API."""
    if not HAS_OPENAI:
        return None

    api_key = settings.DEEPSEEK_API_KEY or settings.OPENROUTER_API_KEY
    if api_key:
        # Try OpenRouter API endpoint first (supports DeepSeek V4 Flash / V3)
        try:
            return ChatOpenAI(
                model="deepseek/deepseek-chat",
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=0,
            )
        except Exception as e:
            logger.warning(f"[LLM Factory] OpenRouter DeepSeek build failed ({e}), trying native DeepSeek API...")
            try:
                return ChatOpenAI(
                    model="deepseek-chat",
                    api_key=api_key,
                    base_url="https://api.deepseek.com/v1",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=0,
                )
            except Exception as ex:
                logger.error(f"[LLM Factory] Failed to build DeepSeek model: {ex}")
    return None


def _build_gemini_flash_model(temperature: float = 0.0, max_tokens: Optional[int] = None) -> Optional[BaseChatModel]:
    """Helper to build Gemini 2.5 Flash model instance."""
    if settings.GEMINI_API_KEY and HAS_GEMINI:
        try:
            return ChatGoogleGenerativeAI(
                model="gemini-flash-lite-latest",
                google_api_key=settings.GEMINI_API_KEY,
                temperature=temperature,
                max_output_tokens=max_tokens,
                max_retries=0,
            )
        except Exception as e:
            logger.warning(f"[LLM Factory] Failed to build Gemini 2.5 Flash model: {e}")
    return None


def get_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> BaseChatModel:
    """
    Unified Flagship Production LLM Factory (DeepSeek V4/V3 + Groq Llama 3.3 70B + Gemini 2.5 Flash).
    Zero Cheap Model Compromises.
    Fallback Chain in Analysis Agent: DeepSeek -> Groq Llama 3.3 70B -> Gemini 2.5 Flash.
    """
    model = (model_name or "deepseek").lower()

    # Build Tier-1 Flagship Provider Instances
    # DeepSeek disabled — API key expired (401). Fallback chain: Groq → Gemini.
    # deepseek_model = _build_deepseek_model(temperature, max_tokens)
    deepseek_model = None
    groq_70b = _build_groq_70b_model(temperature, max_tokens)
    gemini_flash = _build_gemini_flash_model(temperature, max_tokens)

    def create_fallback_chain(primary: BaseChatModel, candidates: List[Optional[BaseChatModel]]) -> BaseChatModel:
        valid_fallbacks = [c for c in candidates if c is not None and c != primary]
        if valid_fallbacks:
            return primary.with_fallbacks(valid_fallbacks, exceptions_to_handle=(Exception,))
        return primary

    # ── 1. DeepSeek Selection (Default for Report Synthesis) ───────────────────
    if "deepseek" in model:
        if deepseek_model:
            logger.debug("[LLM Factory] Dispatching → DeepSeek V4/V3 (with Groq 70B & Gemini 2.5 Flash fallbacks)")
            return create_fallback_chain(deepseek_model, [groq_70b, gemini_flash])
        if groq_70b:
            logger.warning("[LLM Factory] DeepSeek requested but unavailable — falling back to Groq Llama 3.3 70B.")
            return create_fallback_chain(groq_70b, [gemini_flash])
        if gemini_flash:
            return gemini_flash

    # ── 2. Groq Llama 3.3 70B Selection (Planner & Router) ───────────────────
    if "groq" in model or "llama" in model or "70b" in model:
        if groq_70b:
            logger.debug("[LLM Factory] Dispatching → Groq / llama-3.3-70b-versatile (with DeepSeek & Gemini fallbacks)")
            return create_fallback_chain(groq_70b, [deepseek_model, gemini_flash])
        if deepseek_model:
            return create_fallback_chain(deepseek_model, [gemini_flash])
        if gemini_flash:
            return gemini_flash

    # ── 3. Gemini 2.5 Flash Selection (Reflection & Judge) ───────────────────
    if "flash" in model or "gemini" in model or "pro" in model:
        if gemini_flash:
            logger.debug("[LLM Factory] Dispatching → Gemini 2.5 Flash (with DeepSeek & Groq 70B fallbacks)")
            return create_fallback_chain(gemini_flash, [deepseek_model, groq_70b])
        if deepseek_model:
            return create_fallback_chain(deepseek_model, [groq_70b])
        if groq_70b:
            return groq_70b

    # Universal Fallback
    if deepseek_model:
        return create_fallback_chain(deepseek_model, [groq_70b, gemini_flash])
    if groq_70b:
        return create_fallback_chain(groq_70b, [gemini_flash])
    if gemini_flash:
        return gemini_flash

    raise RuntimeError("No active Tier-1 LLM provider found! Please verify DEEPSEEK_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY in backend/.env")
