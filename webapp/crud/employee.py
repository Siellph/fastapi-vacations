from typing import List, Literal, Sequence  # Импорт типов данных

from sqlalchemy import select  # Импорт функции select из библиотеки SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession  # Импорт асинхронной сессии SQLAlchemy
from sqlalchemy.orm import selectinload  # Импорт функции selectinload для предзагрузки связанных данных

from webapp.models.sirius.employee import Employee  # Импорт модели Employee из модуля webapp.models.sirius.employee
from webapp.models.sirius.vacation import Vacation  # Импорт модели Vacation из модуля webapp.models.sirius.vacation
from webapp.schema.employee.employee import (  # Импорт Pydantic моделей Employee и EmployeeCreate
    Employee as EmployeePydantic,
    EmployeeCreate,
)
from webapp.utils.decorator import measure_integration_latency  # Импорт декоратора для измерения времени выполнения


# Получение сотрудника по его ID
# Функция делает запрос к базе данных для получения сотрудника по его ID,
# включая загрузку связанных отпусков.
@measure_integration_latency(
    method_name='get_employee', integration_point='database'
)
async def get_employee(
    session: AsyncSession, employee_id: int
) -> EmployeePydantic:
    result = await session.execute(
        select(Employee)
        .options(selectinload(Employee.vacations))
        .where(Employee.id == employee_id)
    )
    employee = result.unique().scalars().one_or_none()
    return EmployeePydantic.model_validate(employee)


# Получение списка всех сотрудников с возможностью пагинации
# Функция делает запрос к базе данных для получения всех сотрудников,
# включая загрузку связанных отпусков, с возможностью пропуска и ограничения для пагинации.
@measure_integration_latency(
    method_name='get_employees', integration_point='database'
)
async def get_employees(
    session: AsyncSession, skip: int, limit: int
) -> List[EmployeePydantic]:
    result = await session.execute(
        select(Employee)
        .options(selectinload(Employee.vacations))
        .offset(skip)
        .limit(limit)
    )
    employees = result.unique().scalars().all()
    return [EmployeePydantic.model_validate(emp) for emp in employees]


# Создание нового сотрудника
# Функция создает нового сотрудника в базе данных на основе переданных данных.
@measure_integration_latency(
    method_name='create_employee', integration_point='database'
)
async def create_employee(
    session: AsyncSession, employee_data: EmployeeCreate
) -> EmployeeCreate:
    new_employee = Employee(**employee_data.model_dump(exclude_unset=True))
    session.add(new_employee)
    await session.commit()
    await session.refresh(new_employee)
    return new_employee


# Обновление данных существующего сотрудника
# Функция обновляет данные существующего сотрудника в базе данных.
@measure_integration_latency(
    method_name='update_employee', integration_point='database'
)
async def update_employee(
    session: AsyncSession, employee_id: int, update_data: dict[str, bool]
) -> (Employee | None):
    result = await session.execute(
        select(Employee)
        .options(selectinload(Employee.vacations))
        .where(Employee.id == employee_id)
    )
    employee = result.unique().scalars().one_or_none()
    if employee:
        for key, value in update_data.items():
            setattr(employee, key, value)
        await session.commit()
        await session.refresh(employee, attribute_names=['vacations'])
    return employee


# Получение списка отпусков для конкретного сотрудника
# Функция делает запрос к базе данных для получения списка отпусков для конкретного сотрудника с возможностью пагинации.
@measure_integration_latency(
    method_name='get_vacations_for_employee', integration_point='database'
)
async def get_vacations_for_employee(
    session: AsyncSession, employee_id: int, skip: int, limit: int
) -> Sequence[Vacation]:
    result = await session.execute(
        select(Vacation)
        .where(Vacation.employee_id == employee_id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# Удаление сотрудника
# Функция удаляет сотрудника из базы данных по его ID.
@measure_integration_latency(
    method_name='delete_employee', integration_point='database'
)
async def delete_employee(
    session: AsyncSession, employee_id: int
) -> Literal[True]:
    result = await session.execute(
        select(Employee).where(Employee.id == employee_id)
    )
    employee = result.scalars().one_or_none()
    if employee:
        await session.delete(employee)
        await session.commit()
    return True
