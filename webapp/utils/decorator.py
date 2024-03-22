import time
import asyncio
from functools import wraps

from webapp.utils.middleware import INTEGRATION_METHOD_LATENCY

# Функция-декоратор для измерения времени выполнения интеграционных методов
def measure_integration_latency(method_name, integration_point):
    # Внутренний декоратор
    def decorator(func):
        # Обертка для измерения времени выполнения функции
        # wrapper - это оберточная функция, созданная декоратором.
        # Она использует wraps для того, чтобы сохранить информацию о декорированной функции func.
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()  # Засекаем начальное время

            # Проверяем функцию на асинхронность
            if asyncio.iscoroutinefunction(func):
                # вызываем с await, если она асинхронная
                result = await func(*args, **kwargs)
            else:
                # без await, если синхронная
                result = func(*args, **kwargs)

            process_time = time.time() - start_time  # Вычисляем время выполнения
            # Записываем время в метрику с метками method и integration_point
            INTEGRATION_METHOD_LATENCY.labels(
                method=method_name, integration_point=integration_point
            ).observe(process_time)

            return result

        return wrapper

    return decorator
