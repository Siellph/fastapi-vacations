from typing import List, Optional  # Импорт типов для аннотаций

import orjson  # Импорт библиотеки для сериализации/десериализации JSON
from fastapi import Depends, HTTPException, Query, status  # Импорт классов и функций FastAPI
from fastapi.responses import ORJSONResponse  # Импорт класса для создания JSON-ответов
from redis.asyncio import Redis  # Импорт асинхронного клиента Redis
from sqlalchemy.ext.asyncio import AsyncSession  # Импорт асинхронной сессии SQLAlchemy

from conf.config import settings  # Импорт настроек приложения
from webapp.api.vacation.router import vacation_router  # Импорт роутера для отпусков
from webapp.cache.key_builder import (  # Импорт функций для построения ключей кэша
    MAIN_KEY,
    get_vacation_cache_key,
    get_vacation_list_cache_key,
    get_vacation_pending_list_cache_key,
)
from webapp.crud.vacation import (  # Импорт функций для выполнения операций CRUD с отпусками
    create_vacation,
    delete_vacation,
    get_pending_vacations,
    get_vacation,
    get_vacations,
    update_vacation_approval,
)
from webapp.db.postgres import get_session  # Импорт функции для получения асинхронной сессии PostgreSQL
from webapp.db.redis import get_redis  # Импорт функции для получения асинхронного клиента Redis
from webapp.schema.login.user import User  # Импорт модели пользователя
from webapp.schema.vacation.vacation import (  # Импорт моделей отпусков
    Vacation,
    VacationCreate,
    VacationRequst,
)
from webapp.utils.auth.user import get_current_user  # Импорт функции для получения текущего пользователя
from webapp.utils.decorator import measure_integration_latency  # Импорт декоратора для измерения времени выполнения


# Получение списка всех отпусков с учетом фильтров
# При отсутствии кэша - запрос к базе данных и сохранение результатов в кэше
@measure_integration_latency(
    method_name='get_vacations_endpoint', integration_point='endpoint'
)
@vacation_router.get(
    '/',
    response_model=List[Vacation],
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def get_vacations_endpoint(
    approved: Optional[bool] = None,
    skip: int = Query(0, alias='offset'),
    limit: int = Query(10, alias='limit'),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> List[Vacation]:
    # Генерация ключа кэша на основе параметров запроса
    cache_key = get_vacation_list_cache_key(
        approved=approved, skip=skip, limit=limit
    )

    # Проверка наличия данных в кэше
    cached_data = await redis.get(cache_key)
    if cached_data:
        # Возврат данных из кэша
        return orjson.loads(cached_data)

    # Запрос данных из базы данных
    vacations = await get_vacations(
        session=session, approved=approved, skip=skip, limit=limit
    )

    # Сохранение результатов запроса в кэше
    await redis.hset(
        MAIN_KEY,
        cache_key,
        orjson.dumps([vac.model_dump() for vac in vacations]),
    )
    await redis.expire(MAIN_KEY, settings.CACHE_EXPIRATION_TIME)
    return vacations


# Получение списка отпусков, ожидающих рассмотрения
# При отсутствии кэша - запрос к базе данных и сохранение результатов в кэше
@measure_integration_latency(
    method_name='get_pending_vacations_endpoint', integration_point='endpoint'
)
@vacation_router.get(
    '/pending',
    response_model=List[Vacation],
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def get_pending_vacations_endpoint(
    skip: int = Query(0, alias='offset'),
    limit: int = Query(10, alias='limit'),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> List[Vacation]:
    cache_key = get_vacation_pending_list_cache_key(skip=skip, limit=limit)
    cached_data = await redis.get(cache_key)

    if cached_data:
        return orjson.loads(cached_data)

    pending_vacations = await get_pending_vacations(session, skip, limit)
    await redis.hset(
        MAIN_KEY,
        cache_key,
        orjson.dumps([vac.model_dump() for vac in pending_vacations]),
    )
    await redis.expire(MAIN_KEY, settings.CACHE_EXPIRATION_TIME)
    return pending_vacations


# Получение деталей отпуска по его идентификатору
# При отсутствии кэша - запрос к базе данных и сохранение результатов в кэше
@measure_integration_latency(
    method_name='get_vacation_endpoint', integration_point='endpoint'
)
@vacation_router.get(
    '/{vacation_id}',
    response_model=Vacation,
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def get_vacation_endpoint(
    vacation_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Vacation:
    cache_key = get_vacation_cache_key(vacation_id=vacation_id)
    cached_vacation = await redis.get(cache_key)

    if cached_vacation:
        return orjson.loads(cached_vacation)

    vacation = await get_vacation(session, vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail='Vacation not found')
    await redis.hset(
        MAIN_KEY,
        cache_key,
        orjson.dumps(vacation.model_dump()),
    )
    await redis.expire(MAIN_KEY, settings.CACHE_EXPIRATION_TIME)
    return vacation


# Создание нового отпуска администратором
# После создания отпуска - инвалидация кэша
@measure_integration_latency(
    method_name='create_vacation_endpoint', integration_point='endpoint'
)
@vacation_router.post(
    '/',
    response_model=Vacation,
    status_code=status.HTTP_201_CREATED,
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def create_vacation_endpoint(
    vacation_data: VacationCreate,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Vacation:
    new_vacation = await create_vacation(session, vacation_data.model_dump())
    await redis.delete(MAIN_KEY)
    return new_vacation


# Запрос на отпуск от сотрудника
# После создания отпуска - инвалидация кэша
@measure_integration_latency(
    method_name='vacation_request_endpoint', integration_point='endpoint'
)
@vacation_router.post(
    '/vacation-requests',
    response_model=Vacation,
    status_code=status.HTTP_201_CREATED,
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def vacation_request_endpoint(
    vacation_request: VacationRequst,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Vacation:
    vacation_data = vacation_request.model_dump()
    vacation_data['employee_id'] = current_user.id
    vacation_data['approved'] = None

    new_vacation = await create_vacation(session, vacation_data)
    await redis.delete(MAIN_KEY)
    return new_vacation


# Подтверждение/отклонение отпуска администратором
# После обновления статуса отпуска - инвалидация кэша для данного отпуска
@measure_integration_latency(
    method_name='update_vacation_approval_endpoint',
    integration_point='endpoint',
)
@vacation_router.put(
    '/{vacation_id}/approval',
    response_model=Vacation,
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def update_vacation_approval_endpoint(
    vacation_id: int,
    approved: bool,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> (Vacation | None):
    updated_vacation = await update_vacation_approval(
        session, vacation_id, approved
    )
    # Инвалидируем кэш для этого отпуска
    cache_key = get_vacation_cache_key(vacation_id)
    await redis.delete(cache_key)
    return updated_vacation


# Удаление отпуска
# После удаления отпуска - инвалидация кэша для данного отпуска
@measure_integration_latency(
    method_name='delete_vacation_endpoint', integration_point='endpoint'
)
@vacation_router.delete(
    '/{vacation_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    tags=['Vacation'],
    response_class=ORJSONResponse,
)
async def delete_vacation_endpoint(
    vacation_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> None:
    await delete_vacation(session, vacation_id)
    # Инвалидируем кэш для этого отпуска
    cache_key = get_vacation_cache_key(vacation_id)
    await redis.delete(cache_key)
    return None
