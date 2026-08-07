# import hashlib
# import logging
# import urllib.parse
# from typing import Optional, Dict, Any
# from decimal import Decimal
# from datetime import datetime

# from src.config import settings
# from src.db.models import OrderStatus
# from src.db.repositories.payment_repository import PaymentRepository
# from src.utils.sentry import SentryStub

# logger = logging.getLogger(__name__)


# class RobokassaService:
#     """Сервис интеграции с Robokassa"""

#     @staticmethod
#     def is_configured() -> bool:
#         return bool(
#             settings.ROBOKASSA_LOGIN and
#             settings.ROBOKASSA_PASSWORD1 and
#             settings.ROBOKASSA_PASSWORD2
#         )

#     @staticmethod
#     def _calculate_signature(*args) -> str:
#         """Вычисляет MD5 подпись для Robokassa"""
#         return hashlib.md5(':'.join(str(arg) for arg in args).encode()).hexdigest()

#     @staticmethod
#     def _get_base_url() -> str:
#         """Возвращает базовый URL Robokassa (тестовый или боевой)"""
#         if settings.ROBOKASSA_TEST_MODE:
#             return "https://auth.robokassa.ru/Merchant/Index.aspx"
#         return "https://auth.robokassa.ru/Merchant/Index.aspx"

#     @classmethod
#     async def create_payment(
#         cls,
#         user_id: int,
#         amount: Optional[float] = None,
#         description: Optional[str] = None,
#     ) -> Optional[Dict[str, Any]]:
#         """Создает платеж в Robokassa и возвращает ссылку на оплату"""
#         if not cls.is_configured():
#             logger.warning("Robokassa не настроена")
#             return None

#         try:
#             effective_amount = amount if amount is not None else settings.SUBSCRIPTION_PRICE
#             effective_description = description or f"Подписка SafeSaverX на {settings.SUBSCRIPTION_DAYS} дней"

#             # Инвойс номер (используем время для уникальности)
#             import time
#             inv_id = int(time.time() * 1000) % 1000000

#             # Формируем подпись для ссылки
#             signature = cls._calculate_signature(
#                 settings.ROBOKASSA_LOGIN,
#                 effective_amount,
#                 inv_id,
#                 settings.ROBOKASSA_PASSWORD1
#             )

#             # Параметры для ссылки
#             params = {
#                 "MerchantLogin": settings.ROBOKASSA_LOGIN,
#                 "OutSum": f"{effective_amount:.2f}",
#                 "InvId": inv_id,
#                 "Description": effective_description,
#                 "SignatureValue": signature,
#                 "Culture": "ru",
#                 "Email": "",
#                 "Encoding": "utf-8",
#                 "IsTest": 1 if settings.ROBOKASSA_TEST_MODE else 0,
#             }

#             # Добавляем URL для возврата
#             if settings.ROBOKASSA_RESULT_URL:
#                 params["ResultURL"] = settings.ROBOKASSA_RESULT_URL
#             if settings.ROBOKASSA_SUCCESS_URL:
#                 params["SuccessURL"] = settings.ROBOKASSA_SUCCESS_URL
#             if settings.ROBOKASSA_FAIL_URL:
#                 params["FailURL"] = settings.ROBOKASSA_FAIL_URL

#             payment_url = f"{cls._get_base_url()}?{urllib.parse.urlencode(params)}"

#             # Сохраняем платеж в БД
#             await PaymentRepository.create(
#                 user_id=user_id,
#                 payment_id=str(inv_id),
#                 amount=effective_amount,
#                 status=OrderStatus.PENDING,
#                 provider=PaymentProvider.ROBOKASSA,
#                 currency="RUB",
#                 description=effective_description,
#                 provider_raw={
#                     "inv_id": inv_id,
#                     "signature": signature,
#                     "is_test": settings.ROBOKASSA_TEST_MODE,
#                 }
#             )

#             logger.info(f"💳 Создан платеж в Robokassa: inv_id={inv_id}, user={user_id}")

#             return {
#                 "payment_id": str(inv_id),
#                 "payment_url": payment_url,
#                 "inv_id": inv_id,
#                 "amount": effective_amount,
#                 "order_status": OrderStatus.PENDING.value,
#             }

#         except Exception as e:
#             SentryStub.capture_exception(e, context="RobokassaService.create_payment", user_id=user_id)
#             logger.exception(f"❌ Ошибка создания платежа в Robokassa: {e}")
#             return None

#     @classmethod
#     async def check_payment(cls, inv_id: int) -> Optional[Dict[str, Any]]:
#         """Проверяет статус платежа в Robokassa через OpStateExt"""
#         if not cls.is_configured():
#             return None

#         try:
#             # Формируем подпись для запроса статуса (используем пароль #2)
#             signature = cls._calculate_signature(
#                 settings.ROBOKASSA_LOGIN,
#                 inv_id,
#                 settings.ROBOKASSA_PASSWORD2
#             )

#             # TODO: Реализовать запрос к OpStateExt API
#             # Пока используем данные из БД
#             payment_db = await PaymentRepository.get_by_payment_id(str(inv_id))
#             if not payment_db:
#                 return None

#             return {
#                 "payment_id": str(inv_id),
#                 "order_status": payment_db.status.value if payment_db else OrderStatus.PENDING.value,
#                 "paid": payment_db.status == OrderStatus.PAID if payment_db else False,
#                 "amount": float(payment_db.amount) if payment_db else 0,
#             }

#         except Exception as e:
#             SentryStub.capture_exception(e, context="RobokassaService.check_payment", inv_id=inv_id)
#             logger.exception(f"❌ Ошибка проверки платежа: {e}")
#             return None

#     @classmethod
#     async def handle_result_url(cls, request_data: Dict[str, str]) -> str:
#         """Обрабатывает Result URL от Robokassa (уведомление об оплате)"""
#         try:
#             merchant_login = request_data.get("MerchantLogin")
#             out_sum = request_data.get("OutSum")
#             inv_id = request_data.get("InvId")
#             signature = request_data.get("SignatureValue")

#             if not all([merchant_login, out_sum, inv_id, signature]):
#                 logger.error("❌ Неполные данные в Result URL")
#                 return f"ERROR: incomplete data"

#             # Проверяем подпись
#             expected_signature = cls._calculate_signature(
#                 merchant_login,
#                 out_sum,
#                 inv_id,
#                 settings.ROBOKASSA_PASSWORD2
#             )

#             if expected_signature.lower() != signature.lower():
#                 logger.error(f"❌ Неверная подпись в Result URL: {signature} vs {expected_signature}")
#                 return f"ERROR: bad signature"

#             # Обрабатываем успешную оплату
#             payment = await PaymentRepository.mark_as_paid(
#                 payment_id=inv_id,
#                 provider_raw={"webhook": request_data}
#             )

#             if payment:
#                 logger.info(f"✅ Платеж {inv_id} успешно оплачен через Result URL")
#                 return f"OK{inv_id}"
#             else:
#                 return f"ERROR: payment not found"

#         except Exception as e:
#             SentryStub.capture_exception(e, context="RobokassaService.handle_result_url")
#             logger.exception(f"❌ Ошибка обработки Result URL: {e}")
#             return f"ERROR: {str(e)}"

#     @classmethod
#     async def handle_success_url(cls, request_data: Dict[str, str]) -> Dict[str, Any]:
#         """Обрабатывает Success URL (перенаправление пользователя после оплаты)"""
#         return {
#             "success": True,
#             "message": "Платеж успешно выполнен! Подписка активирована.",
#         }

#     @classmethod
#     async def handle_fail_url(cls, request_data: Dict[str, str]) -> Dict[str, Any]:
#         """Обрабатывает Fail URL (перенаправление при ошибке)"""
#         return {
#             "success": False,
#             "message": "Платеж отменен или не выполнен. Попробуйте снова.",
#         }

#     @classmethod
#     async def verify_signature(cls, request_data: Dict[str, str]) -> bool:
#         """Проверяет подпись запроса от Robokassa"""
#         try:
#             merchant_login = request_data.get("MerchantLogin")
#             out_sum = request_data.get("OutSum")
#             inv_id = request_data.get("InvId")
#             signature = request_data.get("SignatureValue")

#             if not all([merchant_login, out_sum, inv_id, signature]):
#                 return False

#             expected_signature = cls._calculate_signature(
#                 merchant_login,
#                 out_sum,
#                 inv_id,
#                 settings.ROBOKASSA_PASSWORD2
#             )

#             return expected_signature.lower() == signature.lower()

#         except Exception as e:
#             SentryStub.capture_exception(e, context="RobokassaService.verify_signature")
#             return False