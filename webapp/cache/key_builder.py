from conf.config import settings

MAIN_KEY = f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:vacations'


def get_employee_cache_key(employee_id: int) -> str:
    return f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:employee_cache:{employee_id}'


def get_vacation_cache_key(vacation_id: int) -> str:
    return f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:vacation_cache:{vacation_id}'


def get_vacation_list_cache_key(
    approved: bool | None, skip: int, limit: int
) -> str:
    return f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:vacations:{approved}:{skip}:{limit}'


def get_vacation_pending_list_cache_key(skip: int, limit: int) -> str:
    return f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:pending:vacations:{skip}:{limit}'
