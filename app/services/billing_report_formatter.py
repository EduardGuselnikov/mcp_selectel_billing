from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.balance_formatter import format_money

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_LOCALES = frozenset({"ru", "en"})
VALID_BALANCES = frozenset({"main", "bonus"})
NO_PROJECT_LABEL = "Без проекта"
NO_OBJECT_LABEL = "Без объекта"


class BillingReportParamsError(ValueError):
    """Invalid report parameters before API call."""


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _format_period_date(value: str) -> str:
    return _parse_date(value).strftime("%d.%m.%Y")


def _format_period(start: str, end: str) -> str:
    return f"{_format_period_date(start)}–{_format_period_date(end)}"


def validate_report_params(*, start: str | None, end: str | None, locale: str | None) -> None:
    if not start or not end:
        raise BillingReportParamsError("Укажите период отчёта: дату начала и дату окончания.")

    for label, value in (("start", start), ("end", end)):
        if not DATE_PATTERN.match(value):
            raise BillingReportParamsError(
                f"Некорректный формат даты {label}: ожидается YYYY-MM-DD."
            )

    if not locale:
        raise BillingReportParamsError("Укажите язык отчёта: locale (ru или en).")

    if locale not in VALID_LOCALES:
        raise BillingReportParamsError("Параметр locale должен быть ru или en.")


def validate_balance_filter(balance: str | None) -> None:
    if balance is not None and balance not in VALID_BALANCES:
        raise BillingReportParamsError("Параметр balance должен быть main или bonus.")


def extract_report_rows(raw_response: Any) -> list[dict[str, Any]]:
    if isinstance(raw_response, list):
        return raw_response

    if isinstance(raw_response, dict):
        status = raw_response.get("status")
        if status == "success":
            data = raw_response.get("data")
            return data if isinstance(data, list) else []
        if status == "error":
            error = raw_response.get("error")
            reason = error if isinstance(error, str) else str(error)
            raise ValueError(f"Не удалось получить отчёт по проектам.\nПричина: {reason}")

    return []


def kopecks_to_rubles(value_minor: int) -> float:
    return round(value_minor / 100, 2)


def _metric_from_row(row: dict[str, Any]) -> dict[str, Any]:
    value_minor = int(row.get("value") or 0)
    return {
        "metric_id": row.get("metric_id"),
        "metric_name": row.get("metric_name"),
        "quantity": row.get("quantity", 0),
        "unit": row.get("unit", ""),
        "value_minor": value_minor,
        "value": kopecks_to_rubles(value_minor),
        "balance": row.get("balance"),
        "location_region_key": row.get("location_region_key"),
        "location_region_name": row.get("location_region_name"),
        "location_availability_zone_key": row.get("location_availability_zone_key"),
        "location_availability_zone_name": row.get("location_availability_zone_name"),
        "provision_from": row.get("provision_from"),
        "provision_till": row.get("provision_till"),
    }


def _matches_filter(value: str | None, needle: str) -> bool:
    if value is None:
        return False
    return needle.lower() in value.lower()


def filter_report_rows(
    rows: list[dict[str, Any]],
    *,
    project_name: str | None = None,
    product_name: str | None = None,
    resource_name: str | None = None,
    resource_type: str | None = None,
    metric_id: str | None = None,
    metric_name: str | None = None,
    balance: str | None = None,
    location_region: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for row in rows:
        if project_name and not _matches_filter(row.get("project_name"), project_name):
            continue
        if product_name and not _matches_filter(row.get("product_name"), product_name):
            continue
        if resource_name and not _matches_filter(row.get("resource_name"), resource_name):
            continue
        if resource_type:
            resource_type_value = row.get("resource_type") or row.get("resource_type_name")
            if not _matches_filter(resource_type_value, resource_type):
                continue
        if metric_id and not _matches_filter(row.get("metric_id"), metric_id):
            continue
        if metric_name and not _matches_filter(row.get("metric_name"), metric_name):
            continue
        if balance and row.get("balance") != balance:
            continue
        if location_region:
            region_key = row.get("location_region_key")
            region_name = row.get("location_region_name")
            if not _matches_filter(region_key, location_region) and not _matches_filter(
                region_name, location_region
            ):
                continue
        filtered.append(row)

    return filtered


@dataclass
class Totals:
    total_minor: int = 0
    by_balance: dict[str, int] = field(default_factory=lambda: {"main": 0, "bonus": 0})

    @property
    def total(self) -> float:
        return kopecks_to_rubles(self.total_minor)

    @property
    def by_balance_rubles(self) -> dict[str, float]:
        return {key: kopecks_to_rubles(value) for key, value in self.by_balance.items()}

    def add(self, value_minor: int, balance: str | None) -> None:
        self.total_minor += value_minor
        if balance in self.by_balance:
            self.by_balance[balance] += value_minor


def compute_totals(rows: list[dict[str, Any]]) -> Totals:
    totals = Totals()
    for row in rows:
        value_minor = int(row.get("value") or 0)
        totals.add(value_minor, row.get("balance"))
    return totals


def _project_key(row: dict[str, Any]) -> tuple[str | None, str]:
    project_id = row.get("project_id")
    project_name = row.get("project_name")
    if project_id is None and project_name is None:
        return (None, NO_PROJECT_LABEL)
    return (project_id, project_name or NO_PROJECT_LABEL)


def _product_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row.get("product_name") or "", row.get("service_name") or "")


def _resource_key(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    resource_id = row.get("resource_id")
    resource_name = row.get("resource_name")
    resource_type = row.get("resource_type")
    if resource_id is None and resource_name is None:
        return (None, None, resource_type)
    return (resource_id, resource_name, resource_type)


def _resource_label(row: dict[str, Any]) -> str:
    resource_id, resource_name, _ = _resource_key(row)
    if resource_id is None and resource_name is None:
        return NO_OBJECT_LABEL
    return resource_name or resource_id or NO_OBJECT_LABEL


@dataclass
class ResourceNode:
    resource_id: str | None
    resource_name: str | None
    resource_type: str | None
    resource_type_name: str | None
    parent_resource_id: str | None
    parent_resource_name: str | None
    metrics: list[dict[str, Any]] = field(default_factory=list)
    children: list[ResourceNode] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.resource_id is None and self.resource_name is None:
            return NO_OBJECT_LABEL
        return self.resource_name or self.resource_id or NO_OBJECT_LABEL

    def totals(self) -> Totals:
        totals = Totals()
        for metric in self.metrics:
            totals.add(metric["value_minor"], metric.get("balance"))
        for child in self.children:
            child_totals = child.totals()
            totals.total_minor += child_totals.total_minor
            for balance, amount in child_totals.by_balance.items():
                totals.by_balance[balance] += amount
        return totals

    def first_metric(self) -> dict[str, Any] | None:
        if self.metrics:
            return self.metrics[0]
        for child in self.children:
            metric = child.first_metric()
            if metric:
                return metric
        return None


def _build_resource_nodes(rows: list[dict[str, Any]]) -> list[ResourceNode]:
    nodes_by_id: dict[str, ResourceNode] = {}
    nodes_by_key: dict[tuple[str | None, str | None, str | None], ResourceNode] = {}

    for row in rows:
        key = _resource_key(row)
        node = nodes_by_key.get(key)
        if node is None:
            node = ResourceNode(
                resource_id=row.get("resource_id"),
                resource_name=row.get("resource_name"),
                resource_type=row.get("resource_type"),
                resource_type_name=row.get("resource_type_name"),
                parent_resource_id=row.get("parent_resource_id"),
                parent_resource_name=row.get("parent_resource_name"),
            )
            nodes_by_key[key] = node
            if node.resource_id:
                nodes_by_id[node.resource_id] = node
        node.metrics.append(_metric_from_row(row))

    for node in nodes_by_key.values():
        parent_id = node.parent_resource_id
        if not parent_id or parent_id == node.resource_id:
            continue
        parent = nodes_by_id.get(parent_id)
        if parent is not None and parent is not node:
            parent.children.append(node)

    roots: list[ResourceNode] = []
    for node in nodes_by_key.values():
        parent_id = node.parent_resource_id
        is_child = (
            parent_id
            and parent_id != node.resource_id
            and parent_id in nodes_by_id
            and nodes_by_id[parent_id] is not node
        )
        if not is_child:
            roots.append(node)

    return roots


def _format_quantity(quantity: int | float, unit: str) -> str:
    if isinstance(quantity, float) and quantity.is_integer():
        quantity = int(quantity)
    quantity_str = f"{quantity:,}".replace(",", " ")
    if unit:
        return f"{quantity_str} {unit}"
    return quantity_str


def _format_metric_line(metric: dict[str, Any]) -> str:
    name = metric.get("metric_name") or metric.get("metric_id") or "метрика"
    quantity = metric.get("quantity", 0)
    unit = metric.get("unit", "")
    return f"- {name}: {_format_quantity(quantity, unit)} — {format_money(metric['value_minor'])}"


def _format_resource_header(node: ResourceNode, *, indent: str = "") -> list[str]:
    lines: list[str] = []
    metric = node.first_metric()
    lines.append(f"{indent}Объект: {node.label}")

    if (
        node.parent_resource_id
        and node.parent_resource_id != node.resource_id
        and (node.parent_resource_name or node.parent_resource_id)
    ):
        parent = node.parent_resource_name or node.parent_resource_id
        lines.append(f"{indent}Родительский объект: {parent}")

    type_label = node.resource_type_name or node.resource_type
    if type_label:
        lines.append(f"{indent}Тип: {type_label}")

    if metric:
        if metric.get("location_region_name") or metric.get("location_region_key"):
            region = metric.get("location_region_name") or metric.get("location_region_key")
            lines.append(f"{indent}Регион: {region}")
        if metric.get("location_availability_zone_name") or metric.get(
            "location_availability_zone_key"
        ):
            zone = metric.get("location_availability_zone_name") or metric.get(
                "location_availability_zone_key"
            )
            lines.append(f"{indent}Зона: {zone}")

    return lines


def _format_child_resource(node: ResourceNode) -> list[str]:
    lines = [f"- {node.label}"]
    if node.parent_resource_name or node.parent_resource_id:
        parent = node.parent_resource_name or node.parent_resource_id
        lines.append(f"  Родительский объект: {parent}")

    for metric in node.metrics:
        metric_name = metric.get("metric_name") or metric.get("metric_id") or "метрика"
        lines.append(f"  Метрика: {metric_name}")
        lines.append(
            f"  Количество: {_format_quantity(metric.get('quantity', 0), metric.get('unit', ''))}"
        )
        lines.append(f"  Стоимость: {format_money(metric['value_minor'])}")

    for child in node.children:
        lines.extend(_format_child_resource(child))

    return lines


def _format_resource_section(node: ResourceNode) -> list[str]:
    lines = _format_resource_header(node)

    if node.metrics:
        lines.append("")
        lines.append("Метрики:")
        for metric in node.metrics:
            lines.append(_format_metric_line(metric))

    if node.children:
        lines.append("")
        lines.append("Связанные ресурсы:")
        for child in node.children:
            lines.extend(_format_child_resource(child))

    lines.append("")
    lines.append(f"Итого по объекту {node.label}: {format_money(node.totals().total_minor)}")
    return lines


def _format_grouped_report(rows: list[dict[str, Any]], *, start: str, end: str) -> str:
    lines = [f"Отчёт за период {_format_period(start, end)}", ""]

    projects: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        projects[_project_key(row)].append(row)

    grand_totals = compute_totals(rows)

    for (project_id, project_name), project_rows in sorted(
        projects.items(), key=lambda item: item[0][1]
    ):
        project_totals = compute_totals(project_rows)
        lines.append(f"Проект: {project_name}")
        lines.append("")

        products: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in project_rows:
            products[_product_key(row)].append(row)

        for (product_name, service_name), product_rows in sorted(products.items()):
            product_label = f"{product_name} / {service_name}".strip(" /")
            product_totals = compute_totals(product_rows)
            lines.append(f"Продукт: {product_label}")
            lines.append("")

            resource_nodes = _build_resource_nodes(product_rows)
            for node in sorted(resource_nodes, key=lambda n: n.label):
                lines.extend(_format_resource_section(node))
                lines.append("")

            lines.append(
                f"Итого по продукту {product_name or service_name}: "
                f"{format_money(product_totals.total_minor)}"
            )
            lines.append("")

        lines.append(
            f"Итого по проекту {project_name}: {format_money(project_totals.total_minor)}"
        )
        lines.append("")

    lines.append(f"Общий итог: {format_money(grand_totals.total_minor)}")

    by_balance = grand_totals.by_balance_rubles
    if any(by_balance.values()):
        lines.append(
            f"  Основной баланс: {format_money(grand_totals.by_balance['main'])}"
        )
        lines.append(
            f"  Бонусный баланс: {format_money(grand_totals.by_balance['bonus'])}"
        )

    return "\n".join(lines).rstrip()


def _format_flat_report(rows: list[dict[str, Any]], *, start: str, end: str) -> str:
    lines = [f"Отчёт за период {_format_period(start, end)}", ""]

    for index, row in enumerate(rows, start=1):
        metric = _metric_from_row(row)
        lines.append(f"Строка {index}:")
        lines.append(f"  Проект: {row.get('project_name') or NO_PROJECT_LABEL}")
        lines.append(f"  Продукт: {row.get('product_name') or ''}")
        lines.append(f"  Услуга: {row.get('service_name') or ''}")
        lines.append(f"  Объект: {_resource_label(row)}")
        if row.get("resource_type") or row.get("resource_type_name"):
            lines.append(
                f"  Тип: {row.get('resource_type_name') or row.get('resource_type')}"
            )
        if row.get("parent_resource_name") or row.get("parent_resource_id"):
            parent = row.get("parent_resource_name") or row.get("parent_resource_id")
            lines.append(f"  Родительский объект: {parent}")
        lines.append(
            f"  Метрика: {metric.get('metric_name') or metric.get('metric_id') or ''}"
        )
        lines.append(
            f"  Количество: {_format_quantity(metric.get('quantity', 0), metric.get('unit', ''))}"
        )
        lines.append(f"  Стоимость: {format_money(metric['value_minor'])}")
        lines.append(f"  Баланс: {metric.get('balance') or ''}")
        if metric.get("location_region_name") or metric.get("location_region_key"):
            region = metric.get("location_region_name") or metric.get("location_region_key")
            lines.append(f"  Регион: {region}")
        lines.append("")

    totals = compute_totals(rows)
    lines.append(f"Общий итог: {format_money(totals.total_minor)}")
    return "\n".join(lines).rstrip()


def format_billing_report_by_project_response(
    raw_response: list[dict[str, Any]] | dict[str, Any],
    *,
    start: str,
    end: str,
    group: bool = True,
    project_name: str | None = None,
    product_name: str | None = None,
    resource_name: str | None = None,
    resource_type: str | None = None,
    metric_id: str | None = None,
    metric_name: str | None = None,
    balance: str | None = None,
    location_region: str | None = None,
) -> str:
    rows = extract_report_rows(raw_response)
    rows = filter_report_rows(
        rows,
        project_name=project_name,
        product_name=product_name,
        resource_name=resource_name,
        resource_type=resource_type,
        metric_id=metric_id,
        metric_name=metric_name,
        balance=balance,
        location_region=location_region,
    )

    if not rows:
        return "За выбранный период данных по оказанным услугам нет."

    if group:
        return _format_grouped_report(rows, start=start, end=end)
    return _format_flat_report(rows, start=start, end=end)
