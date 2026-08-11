"""Human labels kept separate from domain enums and machine-readable codes."""

from __future__ import annotations

from .contracts import (
    ApplicationErrorCode,
    ConversationTurnStatus,
    ModelAvailabilityCode,
)


ERROR_LABELS = {
    ApplicationErrorCode.MODEL_UNAVAILABLE: "Локальная модель недоступна",
    ApplicationErrorCode.MODEL_TIMEOUT: "Локальная модель не успела ответить",
    ApplicationErrorCode.CONVERSATION_FAILED: "Не удалось завершить сообщение",
    ApplicationErrorCode.CONVERSATION_NOT_FOUND: "Разговор не найден",
    ApplicationErrorCode.PROFILE_NOT_FOUND: "Профиль модели не найден",
    ApplicationErrorCode.PROFILE_DISABLED: "Профиль модели отключён",
    ApplicationErrorCode.PROVIDER_NOT_FOUND: "Локальный провайдер модели не настроен",
    ApplicationErrorCode.PROVIDER_UNAVAILABLE: "Локальный провайдер модели недоступен",
    ApplicationErrorCode.MODEL_NOT_CONFIGURED: "Для профиля не выбрана модель",
    ApplicationErrorCode.MODEL_CHECK_UNAVAILABLE: "Нельзя проверить наличие модели",
    ApplicationErrorCode.VISUAL_ASSET_NOT_FOUND: "Образ Маши не найден",
    ApplicationErrorCode.VISUAL_ASSET_INTEGRITY_FAILED: "Целостность образа Маши нарушена",
}

TURN_STATUS_LABELS = {
    ConversationTurnStatus.COMPLETED: "Ответ готов",
    ConversationTurnStatus.MODEL_UNAVAILABLE: "Модель недоступна",
    ConversationTurnStatus.TIMEOUT: "Ответ занял слишком много времени",
    ConversationTurnStatus.FAILED: "Сообщение не завершено",
}

MODEL_AVAILABILITY_LABELS = {
    ModelAvailabilityCode.AVAILABLE: "Доступна",
    ModelAvailabilityCode.DISABLED: "Отключена",
    ModelAvailabilityCode.PROVIDER_NOT_FOUND: "Провайдер не настроен",
    ModelAvailabilityCode.PROVIDER_UNAVAILABLE: "Локальный провайдер недоступен",
    ModelAvailabilityCode.MODEL_NOT_CONFIGURED: "Модель не задана",
    ModelAvailabilityCode.MODEL_UNAVAILABLE: "Модель не установлена или недоступна",
    ModelAvailabilityCode.MODEL_CHECK_UNAVAILABLE: "Проверка модели не поддерживается",
}

RUNTIME_STATUS_LABELS = {
    "ready": "Маша готова",
    "degraded": "Маша работает с ограничениями",
    "unavailable": "Masha Home недоступна",
}

PROACTIVE_REASON_LABELS = {
    "authorised": "Контакт разрешён настройками",
    "proactive_disabled": "Инициативность выключена",
    "level_below_reminder": "Уровень инициативности ниже напоминаний",
    "level_below_checkin": "Уровень инициативности ниже check-in",
    "reminders_disabled": "Напоминания выключены",
    "checkins_disabled": "Check-in выключен",
    "quiet_hours": "Сейчас тихие часы",
    "cooldown": "Ещё действует пауза между сообщениями",
    "daily_limit": "Дневной лимит сообщений исчерпан",
    "absence_threshold_not_reached": "Порог отсутствия ещё не достигнут",
    "higher_priority_reminder": "Сначала обрабатывается важное напоминание",
    "awaiting_user_response": "Маша уже ждёт ответа",
    "cycle_delivery_limit": "В этом цикле сообщение уже было отправлено",
    "local_model_unavailable": "Локальная модель недоступна",
    "background_disabled": "Фоновый режим выключен",
    "emergency_stop_engaged": "Включена аварийная остановка",
    "no_events": "Нет событий для сообщения",
}


def error_label(code: ApplicationErrorCode) -> str:
    return ERROR_LABELS[code]


def model_availability_label(code: ModelAvailabilityCode) -> str:
    return MODEL_AVAILABILITY_LABELS[code]


def proactive_reason_label(reason: str) -> str:
    if reason.startswith("terminal_or_delivered:"):
        return "Событие уже обработано"
    return PROACTIVE_REASON_LABELS.get(reason, "Причина пока не переведена")
