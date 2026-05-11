"""REST API для MCP-сервера 1C:Предприятие 7.7.

Предоставляет HTTP endpoints для доступа к метаданным конфигурации.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Import from parent package, not relative to avoid circular import
import mcp_1c77.tools as tools


def _json_response(data: Any, status_code: int = 200) -> JSONResponse:
    """Создать JSON response с корректными заголовками CORS."""
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


def _error_response(message: str, status_code: int = 400) -> JSONResponse:
    """Создать JSON response с ошибкой."""
    return _json_response({"ok": False, "error": message}, status_code)


async def cors_options(request: Request) -> Response:
    """Обработчик CORS preflight запросов."""
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


async def api_root(request: Request) -> JSONResponse:
    """Корневой endpoint API - информация о сервере."""
    loader = tools.get_loader()
    return _json_response({
        "name": "1C 7.7 Metadata API",
        "version": "0.2.0",
        "description": "REST API для доступа к метаданным конфигурации 1С 7.7",
        "loaded": loader.is_loaded,
        "endpoints": {
            "status": "/api/status",
            "objects": "/api/objects",
            "object": "/api/objects/{type}/{name}",
            "module": "/api/objects/{type}/{name}/module",
            "form": "/api/objects/{type}/{name}/form",
            "search": "/api/search",
            "validate_path": "/api/validate/path",
            "validate_query": "/api/validate/query",
            "dependencies": "/api/objects/{type}/{name}/dependencies",
            "dependents": "/api/objects/{type}/{name}/dependents",
            "export": "/api/export",
            "export_object": "/api/export/{type}/{name}",
        },
        "tools_count": len([t for t in dir(tools) if not t.startswith("_") and callable(getattr(tools, t))])
    })


async def api_status(request: Request) -> JSONResponse:
    """Статус загруженной конфигурации."""
    loader = tools.get_loader()
    if not loader.is_loaded:
        return _json_response({"loaded": False})
    
    config = loader.config
    return _json_response({
        "loaded": True,
        "name": config.name,
        "version": config.version,
        "file_path": config.file_path,
        "counts": {
            "constants": len(config.constants),
            "catalogs": len(config.catalogs),
            "documents": len(config.documents),
            "registers": len(config.registers),
            "enums": len(config.enums),
            "reports": len(config.reports),
            "journals": len(config.journals),
            "calc_vars": len(config.calc_vars),
        },
    })


async def api_list_objects(request: Request) -> JSONResponse:
    """Список объектов метаданных с фильтрацией."""
    object_type = request.query_params.get("type", "")
    try:
        result = tools.list_objects(object_type)
        # Парсим результат из строки в JSON
        lines = result.strip().split("\n")
        objects = {}
        current_type = None
        for line in lines:
            if line.startswith("### "):
                current_type = line[4:].strip()
                objects[current_type] = []
            elif line.startswith("- ") and current_type:
                objects[current_type].append(line[2:].strip())
        
        return _json_response({"ok": True, "objects": objects, "count": sum(len(v) for v in objects.values())})
    except Exception as e:
        return _error_response(str(e))


async def api_get_object(request: Request, object_type: str, name: str) -> JSONResponse:
    """Детальная информация об объекте."""
    try:
        result = tools.get_object(object_type, name)
        # Возвращаем как есть или парсим при необходимости
        return _json_response({"ok": True, "data": result})
    except Exception as e:
        return _error_response(str(e))


async def api_get_module(request: Request, object_type: str, name: str) -> JSONResponse:
    """Исходный код модуля объекта."""
    try:
        result = tools.get_module(object_type, name)
        return _json_response({"ok": True, "module": result})
    except Exception as e:
        return _error_response(str(e))


async def api_get_form(request: Request, object_type: str, name: str) -> JSONResponse:
    """Описание формы объекта."""
    try:
        result = tools.get_form(object_type, name)
        return _json_response({"ok": True, "form": result})
    except Exception as e:
        return _error_response(str(e))


async def api_search(request: Request) -> JSONResponse:
    """Поиск по метаданным."""
    query = request.query_params.get("q", "")
    if not query:
        return _error_response("Query parameter 'q' is required")
    
    try:
        result = tools.search(query)
        lines = result.strip().split("\n")
        results = []
        for line in lines:
            if line.startswith("- "):
                results.append(line[2:].strip())
        return _json_response({"ok": True, "query": query, "results": results, "count": len(results)})
    except Exception as e:
        return _error_response(str(e))


async def api_validate_path(request: Request) -> JSONResponse:
    """Валидация пути к реквизиту."""
    object_type = request.query_params.get("type", "")
    name = request.query_params.get("name", "")
    path = request.query_params.get("path", "")
    
    if not all([object_type, name, path]):
        return _error_response("Parameters 'type', 'name', 'path' are required")
    
    try:
        result = tools.validate_field_path(object_type, name, path)
        valid = "не найден" not in result.lower() and "ошибка" not in result.lower()
        return _json_response({"ok": True, "valid": valid, "message": result})
    except Exception as e:
        return _error_response(str(e))


async def api_validate_query(request: Request) -> JSONResponse:
    """Валидация запроса 1С."""
    body = await request.json() if request.method == "POST" else {}
    query_text = body.get("query") or request.query_params.get("query", "")
    
    if not query_text:
        return _error_response("Query text is required")
    
    try:
        result = tools.validate_query(query_text)
        valid = "ошибка" not in result.lower()
        return _json_response({"ok": True, "valid": valid, "message": result})
    except Exception as e:
        return _error_response(str(e))


async def api_get_dependencies(request: Request, object_type: str, name: str) -> JSONResponse:
    """Зависимости объекта (что использует данный объект)."""
    try:
        result = tools.get_object_dependencies(object_type, name)
        # Парсим результат
        lines = result.strip().split("\n")
        dependencies = []
        for line in lines:
            if line.startswith("- "):
                dependencies.append(line[2:].strip())
        return _json_response({
            "ok": True, 
            "object": {"type": object_type, "name": name},
            "dependencies": dependencies,
            "count": len(dependencies)
        })
    except Exception as e:
        return _error_response(str(e))


async def api_get_dependents(request: Request, object_type: str, name: str) -> JSONResponse:
    """Зависимые объекты (кто использует данный объект)."""
    try:
        result = tools.find_dependent_objects(object_type, name)
        lines = result.strip().split("\n")
        dependents = []
        for line in lines:
            if line.startswith("- "):
                dependents.append(line[2:].strip())
        return _json_response({
            "ok": True,
            "object": {"type": object_type, "name": name},
            "dependents": dependents,
            "count": len(dependents)
        })
    except Exception as e:
        return _error_response(str(e))


async def api_export_config(request: Request) -> JSONResponse:
    """Экспорт всей конфигурации в JSON."""
    save_to_file = request.query_params.get("save", "false").lower() == "true"
    output_path = request.query_params.get("path", "") if save_to_file else ""
    
    try:
        result = tools.export_to_json(output_path if save_to_file else "")
        if save_to_file:
            return _json_response({"ok": True, "message": result, "path": output_path})
        else:
            # Парсим JSON строку
            data = json.loads(result)
            return _json_response({"ok": True, "data": data})
    except Exception as e:
        return _error_response(str(e))


async def api_export_object(request: Request, object_type: str, name: str) -> JSONResponse:
    """Экспорт объекта в JSON."""
    try:
        result = tools.export_object_to_json(object_type, name)
        data = json.loads(result)
        return _json_response({"ok": True, "data": data})
    except Exception as e:
        return _error_response(str(e))


async def api_reload(request: Request) -> JSONResponse:
    """Перезагрузка конфигурации."""
    body = await request.json() if request.method == "POST" else {}
    path = body.get("path", "")
    
    try:
        result = tools.reload_configuration(path)
        success = "успешно" in result.lower() or "перезагружена" in result.lower()
        return _json_response({"ok": success, "message": result})
    except Exception as e:
        return _error_response(str(e))
