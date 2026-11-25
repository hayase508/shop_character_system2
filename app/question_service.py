from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from .config import Settings


logger = logging.getLogger(__name__)


LOCAL_VOICE_LINES: dict[str, str] = {
    "assistance-prompt": (
        "何かお困りでしょうか？"
        "タッチパネルから私に質問してくださいね。"
    ),
    "discount-eligible": "はい。QRコードを精算機にかざすと、豚汁たまご定食が500円になります。",
    "discount-ineligible": "本日は60日以内の特典対象ではないようです。詳しくはスタッフにお尋ねください。",
    "pork-soup-refill": "はい。豚汁はお代わり自由です。",
    "egg-refill": "たまごもお代わり自由です。",
    "rice-refill": "ご飯もお代わり自由です。",
    "drink-refill": "飲み物もお代わり自由です。",
    "drink-price": "コーヒーやお茶などのお飲み物は500円です。",
    "meal-price": "豚汁たまご定食は1,200円です。",
    "repeat-benefit": (
        "前回の来店で定食を注文するとQRコードが発行されます。"
        "60日以内に再びご来店いただき、メニューを注文する際に"
        "QRコードをかざすと定食が500円になります。"
    ),
    "payment-method": (
        "こちらの画面からメニューを選択し、"
        "下の精算機に現金を投入してください。"
    ),
    "meal-refills": (
        "当店ではお代わり自由の豚汁たまご定食とドリンクバーがございます。"
    ),
    "self-service": "配膳はセルフサービスです。よろしくお願いいたします。",
    "ask-staff": "お答えできません。詳しくはスタッフにお尋ねください。",
    "transcription-failed": "申し訳ございません。うまく聞き取れませんでした。もう一度お話しください。",
    "gemini-unavailable": "申し訳ございません。現在、難しい質問にはお答えできません。詳しくはスタッフにお尋ねください。",
    "gemini-limit": "難しい質問への回答はここまでです。詳しくはスタッフにお尋ねください。",
}


GEMINI_SYSTEM_INSTRUCTION = """「いちごうカフェ」の親しみやすい鬼店員として日本語で答える。
すべての回答を丁寧な「です・ます調」に統一する。「じゃ」「じゃぞ」「だぞ」などの尊大な語尾は禁止。
音声用の回答本文一文だけを原則50文字以内、最長80文字で返す。前置き、引用符、箇条書き、注釈、文字数報告は禁止。
確定情報：豚汁たまご定食1,200円。豚汁・たまご・ご飯はお代わり自由。飲み物は500円でお代わり自由。2回目以降かつ前回来店から60日以内は、配布済みQRコードを精算機にかざすと定食500円。配膳はセルフサービス。
料金・割引条件を変更しない。不明な営業時間、定休日、アレルギー、原材料、支払い、在庫、駐車場は推測せず「スタッフにお尋ねください」と答える。顔・顧客・来店履歴は推測しない。"""


@dataclass(frozen=True, slots=True)
class QuestionContext:
    discount_eligible: bool
    days_since_last_visit: int | None


@dataclass(frozen=True, slots=True)
class AnswerResult:
    text: str
    source: str
    gemini_attempted: bool = False
    audio_key: str | None = None


@dataclass(frozen=True, slots=True)
class LocalAnswer:
    text: str
    audio_key: str


@dataclass(frozen=True, slots=True)
class TouchQuestion:
    question_id: str
    label: str
    audio_key: str
    category: str
    category_label: str
    display_image_url: str | None = None
    display_image_layout: str | None = None
    display_image_alt: str | None = None
    language: str = "ja"
    answer_text: str | None = None

    @property
    def answer(self) -> str:
        return self.answer_text or LOCAL_VOICE_LINES[self.audio_key]


TOUCH_QUESTIONS: tuple[TouchQuestion, ...] = (
    TouchQuestion(
        "payment-method",
        "支払方法を知りたい",
        "payment-method",
        "payment",
        "支払方法",
        "/static/images/checkout-machine.png",
        "landscape",
        "精算機の操作画面",
    ),
    TouchQuestion(
        "repeat-benefit",
        "再来店特典とは",
        "repeat-benefit",
        "benefit",
        "再来店特典",
        "/static/images/revisit-benefit.png",
        "portrait",
        "60日以内の再来店特典のご案内",
    ),
    TouchQuestion("meal-info", "お食事", "meal-refills", "food", "お食事"),
)
TOUCH_QUESTION_BY_ID = {question.question_id: question for question in TOUCH_QUESTIONS}

SUPPORTED_TOUCH_LANGUAGES = ("ja", "en", "zh", "ko")
TOUCH_QUESTION_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "payment-method": {
            "label": "How do I pay?",
            "category_label": "Payment",
            "answer": "Please select your item on this screen, then insert cash into the payment machine below.",
            "display_image_alt": "Payment machine screen",
        },
        "repeat-benefit": {
            "label": "What is the return-visit discount?",
            "category_label": "Return-visit discount",
            "answer": "When you order a set meal, you receive a QR code. Return within 60 days and scan it when ordering to get the set meal for 500 yen.",
            "display_image_alt": "Return-visit discount within 60 days",
        },
        "meal-info": {
            "label": "Meals",
            "category_label": "Meals",
            "answer": "We offer a tonjiru and egg set meal with unlimited refills, as well as a drink bar.",
        },
    },
    "zh": {
        "payment-method": {
            "label": "如何付款？",
            "category_label": "付款方式",
            "answer": "请在此屏幕选择餐点，然后将现金投入下方的结算机。",
            "display_image_alt": "结算机操作画面",
        },
        "repeat-benefit": {
            "label": "什么是再次来店优惠？",
            "category_label": "再次来店优惠",
            "answer": "点套餐后会获得二维码。60天内再次来店，点餐时扫描二维码，套餐即可享受500日元优惠价。",
            "display_image_alt": "60天内再次来店优惠说明",
        },
        "meal-info": {
            "label": "餐饮",
            "category_label": "餐饮",
            "answer": "本店提供可免费续加的猪肉味噌汤鸡蛋套餐和饮料吧。",
        },
    },
    "ko": {
        "payment-method": {
            "label": "결제 방법을 알고 싶어요",
            "category_label": "결제 방법",
            "answer": "이 화면에서 메뉴를 선택한 후 아래 결제기에 현금을 넣어 주세요.",
            "display_image_alt": "결제기 조작 화면",
        },
        "repeat-benefit": {
            "label": "재방문 혜택이란?",
            "category_label": "재방문 혜택",
            "answer": "정식을 주문하면 QR 코드를 드립니다. 60일 이내에 다시 방문하여 주문할 때 QR 코드를 스캔하면 정식을 500엔에 이용할 수 있습니다.",
            "display_image_alt": "60일 이내 재방문 혜택 안내",
        },
        "meal-info": {
            "label": "식사",
            "category_label": "식사",
            "answer": "저희 가게에는 리필이 자유로운 돼지고기 된장국 달걀 정식과 드링크 바가 있습니다.",
        },
    },
}


def normalize_touch_language(language: str | None) -> str:
    value = (language or "ja").strip().lower().replace("_", "-")
    base = value.split("-", 1)[0]
    return base if base in SUPPORTED_TOUCH_LANGUAGES else "ja"


def touch_question_catalog(language: str = "ja") -> list[dict[str, str]]:
    normalized = normalize_touch_language(language)
    return [
        {
            "id": question.question_id,
            "label": question.label,
            "category": question.category,
            "category_label": question.category_label,
            "language": question.language,
        }
        for question in (
            get_touch_question(item.question_id, normalized)
            for item in TOUCH_QUESTIONS
        )
        if question is not None
    ]


def get_touch_question(question_id: str, language: str = "ja") -> TouchQuestion | None:
    question = TOUCH_QUESTION_BY_ID.get(question_id)
    if question is None:
        return None
    normalized = normalize_touch_language(language)
    if normalized == "ja":
        return question
    translation = TOUCH_QUESTION_TRANSLATIONS[normalized][question_id]
    return TouchQuestion(
        question_id=question.question_id,
        label=translation["label"],
        audio_key=question.audio_key,
        category=question.category,
        category_label=translation["category_label"],
        language=normalized,
        answer_text=translation["answer"],
        display_image_url=question.display_image_url,
        display_image_layout=question.display_image_layout,
        display_image_alt=translation.get(
            "display_image_alt", question.display_image_alt or ""
        ),
    )


def local_answer(audio_key: str) -> LocalAnswer:
    return LocalAnswer(LOCAL_VOICE_LINES[audio_key], audio_key)


def normalize_question(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower().strip()
    return re.sub(r"[\s、。,.!?！？・「」『』（）()]+", "", normalized)


def is_meaningful_question(text: str) -> bool:
    compact = normalize_question(text)
    if compact in {"卵", "玉子", "茶"}:
        return True
    return len(compact) >= 2 and bool(re.search(r"[0-9a-zぁ-んァ-ヶ一-龠]", compact))


def is_likely_spoken_question(text: str) -> bool:
    """Reject Whisper prose/hallucinations that do not look like a question.

    This intentionally runs after speech recognition and before FAQ/Gemini.
    Known terse shop questions are accepted, while background audio decoded as
    an ordinary statement is silently ignored.
    """
    if not is_meaningful_question(text):
        return False
    compact = normalize_question(text)
    shop_or_addressee_cues = (
        "鬼", "店員", "いちごうカフェ", "店", "メニュー", "おすすめ",
        "豚汁", "たまご", "卵", "ご飯", "定食", "飲み物", "ドリンク",
        "コーヒー", "お茶", "おかわり", "お代わり", "qrコード", "精算機",
        "料金", "値段", "特典", "配膳", "セルフサービス", "営業時間",
        "定休日", "アレルギー", "原材料", "支払い", "カード", "現金",
        "電子マネー", "在庫", "売り切れ", "駐車場", "トイレ",
    )
    has_shop_context = any(cue in compact for cue in shop_or_addressee_cues)
    question_cues = (
        "いくら", "何円", "なんえん", "何時", "いつ", "どこ", "どれ",
        "どちら", "誰", "だれ", "なぜ", "どう", "何個", "なんこ",
        "できます", "できる", "あります", "あるの", "でしょうか",
        "ですか", "ますか", "教えて", "おしえて", "知りたい",
        "おかわり", "お代わり", "もう一杯", "もういっぱい",
    )
    # Whisper can misrecognize the product name even when the sentence ending is
    # clearly interrogative. Accept explicit question forms without requiring a
    # shop keyword, then let the FAQ-only policy return the safe staff guidance
    # when no local FAQ matches.
    if any(mark in text for mark in ("?", "？")) or any(
        cue in compact for cue in question_cues
    ):
        return True
    if has_shop_context and compact.endswith(("は", "の")) and len(compact) >= 3:
        return True
    terse_shop_questions = (
        "営業時間", "定休日", "アレルギー", "原材料", "支払い方法", "駐車場",
    )
    if compact in terse_shop_questions:
        return True
    return "今日" in compact and any(cue in compact for cue in ("500円", "五百円", "特典"))


class LocalFaqService:
    _refill_words = (
        "おかわり", "お代わり", "お変わり", "お替わり",
        "もう一杯", "もういっぱい", "追加",
    )
    _price_words = ("いくら", "値段", "価格", "何円", "なんえん")

    def answer(self, question: str, context: QuestionContext) -> LocalAnswer | None:
        text = normalize_question(question)
        has_refill = any(word in text for word in self._refill_words)
        has_price = any(word in text for word in self._price_words)

        if "今日" in text and any(word in text for word in ("500円", "五百円", "安く", "特典")):
            if context.discount_eligible:
                return local_answer("discount-eligible")
            return local_answer("discount-ineligible")

        if any(
            word in text for word in ("豚汁", "とん汁", "とんじる", "トン汁", "トンジル")
        ) and has_refill:
            return local_answer("pork-soup-refill")
        if any(word in text for word in ("たまご", "卵", "玉子")) and (
            has_refill or "何個" in text or "なんこ" in text
        ):
            return local_answer("egg-refill")
        if "ご飯" in text and has_refill:
            return local_answer("rice-refill")

        drink_words = ("飲み物", "ドリンク", "コーヒー", "珈琲", "お茶", "紅茶")
        if any(word in text for word in drink_words) and has_refill:
            return local_answer("drink-refill")
        if any(word in text for word in drink_words) and has_price:
            return local_answer("drink-price")

        meal_words = ("定食", "たまご定食", "豚汁たまご", "ご飯")
        if any(word in text for word in meal_words) and has_price:
            return local_answer("meal-price")

        if any(word in text for word in ("再来店", "特典", "2回目", "二回目", "60日", "六十日")):
            return local_answer("repeat-benefit")

        if any(word in text for word in ("配膳", "運ぶ", "セルフサービス", "受け取り", "片付け")):
            return local_answer("self-service")

        unknown_shop_topics = (
            "営業時間", "何時", "定休日", "店の休み", "お店の休み", "アレルギー", "原材料",
            "支払い", "カード", "現金", "電子マネー", "在庫", "売り切れ", "駐車場",
        )
        if any(word in text for word in unknown_shop_topics):
            return local_answer("ask-staff")
        return None


class GeminiService:
    """Text-only Gemini access. No customer or biometric data is accepted here."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any | None = None
        self._types: Any | None = None
        self._client_lock = threading.Lock()
        self._lock = asyncio.Lock()
        self._connection_warmed = False
        self._cache: dict[str, tuple[float, str]] = {}

    @property
    def available(self) -> bool:
        return bool(
            self.settings.gemini_enabled
            and self.settings.gemini_api_key
            and self.settings.gemini_model
        )

    def cached_answer(self, question: str) -> str | None:
        key = normalize_question(question)
        cached = self._cache.get(key)
        if cached is None:
            return None
        expires_at, answer = cached
        if expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return answer

    async def answer_uncached(self, question: str) -> str:
        if not self.available:
            raise RuntimeError("Gemini is disabled or its API key is not configured")
        async with self._lock:
            cached = self.cached_answer(question)
            if cached is not None:
                return cached
            response_text = await asyncio.wait_for(
                self._generate(question),
                timeout=self.settings.gemini_timeout_seconds,
            )
            answer = self._sanitize_answer(response_text)
            self._cache[normalize_question(question)] = (
                time.monotonic() + self.settings.gemini_cache_ttl_seconds,
                answer,
            )
            return answer

    async def _generate(self, question: str) -> str:
        client, types = await asyncio.to_thread(self._ensure_client)
        started_at = time.perf_counter()
        first_chunk_seconds: float | None = None
        chunks: list[str] = []
        try:
            stream = await client.aio.models.generate_content_stream(
                model=self.settings.gemini_model,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                    max_output_tokens=self.settings.gemini_max_output_tokens,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                    thinking_config=types.ThinkingConfig(
                        thinking_level=self.settings.gemini_thinking_level,
                    ),
                ),
            )
            async for chunk in stream:
                chunk_text = getattr(chunk, "text", None)
                if isinstance(chunk_text, str) and chunk_text:
                    if first_chunk_seconds is None:
                        first_chunk_seconds = time.perf_counter() - started_at
                    chunks.append(chunk_text)
        finally:
            logger.info(
                "[PERFORMANCE] Gemini: first_chunk=%s total=%.3fs model=%s",
                (
                    f"{first_chunk_seconds:.3f}s"
                    if first_chunk_seconds is not None
                    else "none"
                ),
                time.perf_counter() - started_at,
                self.settings.gemini_model,
            )
        text = "".join(chunks)
        if not text.strip():
            raise RuntimeError("Gemini returned no text")
        return text

    def prepare(self) -> None:
        """Import the SDK and create its reusable HTTP client before the first question."""
        started_at = time.perf_counter()
        self._ensure_client()
        logger.info(
            "[GEMINI] Client prepared in %.3fs model=%s",
            time.perf_counter() - started_at,
            self.settings.gemini_model,
        )

    async def warm_connection(self) -> None:
        """Warm DNS/TLS with model metadata, without generating billable content."""
        if not self.available or self._connection_warmed:
            return
        async with self._lock:
            if self._connection_warmed:
                return
            client, _ = await asyncio.to_thread(self._ensure_client)
            started_at = time.perf_counter()
            await asyncio.wait_for(
                client.aio.models.get(model=self.settings.gemini_model),
                timeout=self.settings.gemini_timeout_seconds,
            )
            self._connection_warmed = True
            logger.info(
                "[GEMINI] Connection warmed in %.3fs without content generation",
                time.perf_counter() - started_at,
            )

    def _ensure_client(self) -> tuple[Any, Any]:
        if self._client is not None and self._types is not None:
            return self._client, self._types
        with self._client_lock:
            if self._client is not None and self._types is not None:
                return self._client, self._types
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise RuntimeError("google-genai is not installed") from exc
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
            self._types = types
            return self._client, self._types

    @staticmethod
    def _sanitize_answer(text: str) -> str:
        answer = re.sub(r"\s+", " ", text).strip().strip('"「」')
        count_suffixes = (
            r"\s*[（(【\[]\s*(?:合計|全|約)?\s*\d+\s*文字(?:以内)?\s*[）)】\]]\s*$",
            r"\s*(?:文字数|字数)\s*[:：]\s*(?:約)?\s*\d+\s*文字?\s*$",
            r"\s*(?:合計|全|約)\s*\d+\s*文字\s*$",
        )
        for pattern in count_suffixes:
            answer = re.sub(pattern, "", answer).rstrip()
        if not answer:
            raise RuntimeError("Gemini returned an empty answer")
        if len(answer) > 80:
            answer = answer[:79].rstrip("、。 ") + "。"
        return answer

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aio.aclose()
        except Exception:
            logger.debug("[GEMINI] Failed to close async client", exc_info=True)
        try:
            self._client.close()
        except Exception:
            logger.debug("[GEMINI] Failed to close sync client", exc_info=True)


class QuestionAnswerService:
    def __init__(self, settings: Settings, gemini: GeminiService | None = None) -> None:
        self.settings = settings
        self.faq = LocalFaqService()
        self.gemini = gemini or GeminiService(settings)

    async def answer(
        self,
        question: str,
        context: QuestionContext,
        gemini_requests_used: int,
        force_gemini: bool = False,
    ) -> AnswerResult:
        local = self.faq.answer(question, context)
        if local is not None:
            return AnswerResult(local.text, "faq", audio_key=local.audio_key)

        if self.settings.question_unknown_policy == "staff" and not force_gemini:
            return AnswerResult(
                LOCAL_VOICE_LINES["ask-staff"],
                "unsupported_question",
                audio_key="ask-staff",
            )

        cached = self.gemini.cached_answer(question)
        if cached is not None:
            return AnswerResult(cached, "gemini_cache")

        if not self.gemini.available:
            return AnswerResult(
                LOCAL_VOICE_LINES["gemini-unavailable"],
                "gemini_disabled",
                audio_key="gemini-unavailable",
            )
        if gemini_requests_used >= self.settings.gemini_max_requests_per_session:
            return AnswerResult(
                LOCAL_VOICE_LINES["gemini-limit"],
                "gemini_limit",
                audio_key="gemini-limit",
            )

        safe_question = question[: self.settings.gemini_max_question_chars]
        try:
            return AnswerResult(
                await self.gemini.answer_uncached(safe_question),
                "gemini",
                gemini_attempted=True,
            )
        except Exception as exc:
            logger.warning("[GEMINI] Request failed: %s", type(exc).__name__)
            return AnswerResult(
                LOCAL_VOICE_LINES["gemini-unavailable"],
                "gemini_error",
                gemini_attempted=True,
                audio_key="gemini-unavailable",
            )
