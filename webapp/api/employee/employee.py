from typing import List, Sequence  # Импорт типов для аннотаций

import orjson  # Импорт библиотеки для сериализации/десериализации JSON
from fastapi import Depends, HTTPException, Query, status  # Импорт классов и функций FastAPI
from fastapi.responses import ORJSONResponse  # Импорт класса для создания JSON-ответов
from redis.asyncio import Redis  # Импорт асинхронного клиента Redis
from sqlalchemy.ext.asyncio import AsyncSession  # Импорт асинхронной сессии SQLAlchemy

from conf.config import settings  # Импорт настроек приложения
from webapp.api.employee.router import employee_router  # Импорт роутера для сотрудников
from webapp.cache.key_builder import get_employee_cache_key  # Импорт функции для получения ключа кэша сотрудника
from webapp.crud.employee import (  # Импорт функций для выполнения операций CRUD с сотрудниками
    create_employee,
    delete_employee,
    get_employee,
    get_employees,
    get_vacations_for_employee,
    update_employee,
)
from webapp.db.postgres import get_session  # Импорт функции для получения асинхронной сессии PostgreSQL
from webapp.db.redis import get_redis  # Импорт функции для получения асинхронного клиента Redis
from webapp.schema.employee.employee import (  # Импорт моделей сотрудников
    Employee,
    EmployeeCreate,
    EmployeeUpdate,
)
from webapp.schema.vacation.vacation import Vacation  # Импорт модели отпусков
from webapp.utils.decorator import measure_integration_latency  # Импорт декоратора для измерения времени выполнения


# Создание учетной записи нового сотрудника
# После создания сотрудника - его данные могут быть сохранены в кэше (не реализовано в данном коде)
@measure_integration_latency(
    method_name='create_employee_endpoint', integration_point='endpoint'
)
@employee_router.post(
    '/',
    response_model=EmployeeCreate,
    status_code=status.HTTP_201_CREATED,
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def create_employee_endpoint(
    employee_data: EmployeeCreate,
    session: AsyncSession = Depends(get_session),
) -> EmployeeCreate:
    created_employee = await create_employee(
        session=session, employee_data=employee_data
    )
    return created_employee


# Получение списка всех сотрудников
# При наличии кэшированных данных возвращает их, иначе делает запрос к базе данных
@measure_integration_latency(
    method_name='get_employees_endpoint', integration_point='endpoint'
)
@employee_router.get(
    '/',
    response_model=List[Employee],
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def get_employees_endpoint(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, alias='offset'),
    limit: int = Query(10, alias='limit'),
    redis: Redis = Depends(get_redis),
) -> List[Employee]:
    # Генерация ключа кэша для списка сотрудников
    cache_key = f'employee_{skip}_{limit}'
    # Проверка наличия данных в кэше
    cached_data = await redis.get(cache_key)

    if cached_data:
        # Возврат данных из кэша, если они есть
        return orjson.loads(cached_data)

    # Запрос данных из базы данных
    employees = await get_employees(session=session, skip=skip, limit=limit)
    # Сохранение данных в кэше
    await redis.set(
        cache_key,
        orjson.dumps([emp.model_dump() for emp in employees]),
        ex=settings.CACHE_EXPIRATION_TIME,
    )

    return employees


# Частичное обновление данных о сотруднике
# После обновления сотрудника, его данные могут быть обновлены в кэше (не реализовано в данном коде)
@measure_integration_latency(
    method_name='patch_employee_endpoint', integration_point='endpoint'
)
@employee_router.patch(
    '/{employee_id}',
    response_model=Employee,
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def patch_employee_endpoint(
    employee_id: int,
    employee_data: EmployeeUpdate,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),  # Добавляем зависимость от Redis
) -> Employee:
    # Очистка кэша сотрудника, так как его данные обновляются
    cache_key = get_employee_cache_key(employee_id)
    await redis.delete(cache_key)

    return await update_employee(
        session=session,
        employee_id=employee_id,
        update_data=employee_data.model_dump(exclude_unset=True),
    )


# Получение списка отпусков для конкретного сотрудника
@measure_integration_latency(
    method_name='get_vacations_for_employee_endpoint',
    integration_point='endpoint',
)
@employee_router.get(
    '/{employee_id}/vacations',
    response_model=List[Vacation],
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def get_vacations_for_employee_endpoint(
    employee_id: int,
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, alias='offset'),
    limit: int = Query(10, alias='limit'),
) -> Sequence[Vacation]:
    return await get_vacations_for_employee(
        session=session, employee_id=employee_id, skip=skip, limit=limit
    )


# Получение информации о конкретном сотруднике
# Если данные о сотруднике находятся в кэше, возвращаются они, иначе делается запрос к базе данных
@measure_integration_latency(
    method_name='get_employee_endpoint', integration_point='endpoint'
)
@employee_router.get(
    '/{employee_id}',
    response_model=Employee,
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def get_employee_endpoint(
    employee_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),  # Добавляем зависимость от Redis
) -> Employee:
    # Генерация ключа кэша для сотрудника
    cache_key = get_employee_cache_key(employee_id)
    # Проверка наличия данных о сотруднике в кэше
    cached_data = await redis.get(cache_key)

    if cached_data:
        # Возврат данных о сотруднике из кэша, если они есть
        return orjson.loads(cached_data)

    # Запрос данных о сотруднике из базы данных
    employee = await get_employee(session=session, employee_id=employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail='Employee not found')

    # Сохранение данных о сотруднике в кэше
    await redis.set(
        cache_key,
        employee.model_dump_json(),
        ex=settings.CACHE_EXPIRATION_TIME,
    )

    return employee


# Удаление сотрудника
# После удаления сотрудника, его данные могут быть удалены из кэша (не реализовано в данном коде)
@measure_integration_latency(
    method_name='delete_employee_endpoint', integration_point='endpoint'
)
@employee_router.delete(
    '/{employee_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    tags=['Employee'],
    response_class=ORJSONResponse,
)
async def delete_employee_endpoint(
    employee_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),  # Добавляем зависимость от Redis
) -> None:
    # Очистка кэша сотрудника перед удалением
    cache_key = get_employee_cache_key(employee_id)
    await redis.delete(cache_key)

    employee = await delete_employee(session=session, employee_id=employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail='Employee not found')

    # Возврат статуса 204 No Content в случае успешного удаления
    return None
