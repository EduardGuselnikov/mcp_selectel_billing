import pytest

from app.selectel_client import SelectelClient, SelectelValidationError
from app.services.billing_report_formatter import (
    BillingReportParamsError,
    compute_totals,
    extract_report_rows,
    filter_report_rows,
    format_billing_report_by_project_response,
    kopecks_to_rubles,
    validate_report_params,
)


def _sample_row(
    *,
    project_id: str = "proj-1",
    project_name: str = "Dedicated Project",
    product_name: str = "Облачные серверы",
    service_name: str = "Облачные серверы",
    resource_id: str = "srv-1",
    resource_name: str = "Marcie",
    resource_type: str = "cloud_vm",
    resource_type_name: str = "Сервер",
    parent_resource_id: str | None = None,
    parent_resource_name: str | None = None,
    metric_id: str = "vcpu",
    metric_name: str = "vCPU",
    quantity: int = 744,
    unit: str = "item",
    value: int = 68861,
    balance: str = "main",
    location_region_key: str = "ala",
    location_region_name: str = "Алматы",
    location_availability_zone_key: str = "ala-1",
    location_availability_zone_name: str = "Зона доступности 1",
) -> dict:
    return {
        "project_id": project_id,
        "project_name": project_name,
        "product_name": product_name,
        "service_name": service_name,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "resource_type": resource_type,
        "resource_type_name": resource_type_name,
        "parent_resource_id": parent_resource_id,
        "parent_resource_name": parent_resource_name,
        "location_region_key": location_region_key,
        "location_region_name": location_region_name,
        "location_availability_zone_key": location_availability_zone_key,
        "location_availability_zone_name": location_availability_zone_name,
        "metric_id": metric_id,
        "metric_name": metric_name,
        "provision_from": "2026-05-01",
        "provision_till": "2026-05-31",
        "balance": balance,
        "value": value,
        "quantity": quantity,
        "unit": unit,
    }


def test_validate_report_params_requires_dates() -> None:
    with pytest.raises(BillingReportParamsError, match="Укажите период отчёта"):
        validate_report_params(start=None, end="2026-06-01", locale="ru")


def test_validate_report_params_requires_locale() -> None:
    with pytest.raises(BillingReportParamsError, match="Укажите язык отчёта"):
        validate_report_params(start="2026-05-01", end="2026-06-01", locale=None)


def test_validate_report_params_invalid_locale() -> None:
    with pytest.raises(BillingReportParamsError, match="locale должен быть ru или en"):
        validate_report_params(start="2026-05-01", end="2026-06-01", locale="de")


def test_extract_report_rows_from_array() -> None:
    rows = [_sample_row()]
    assert extract_report_rows(rows) == rows


def test_extract_report_rows_from_success_wrapper() -> None:
    rows = [_sample_row()]
    assert extract_report_rows({"status": "success", "data": rows}) == rows


def test_kopecks_to_rubles() -> None:
    assert kopecks_to_rubles(68861) == 688.61
    assert kopecks_to_rubles(112276) == 1122.76


def test_filter_report_rows_case_insensitive() -> None:
    rows = [_sample_row(project_name="Dedicated Project")]
    filtered = filter_report_rows(rows, project_name="dedicated")
    assert len(filtered) == 1


def test_filter_report_rows_by_balance() -> None:
    rows = [
        _sample_row(balance="main"),
        _sample_row(balance="bonus", metric_id="ram", metric_name="RAM"),
    ]
    filtered = filter_report_rows(rows, balance="bonus")
    assert len(filtered) == 1
    assert filtered[0]["balance"] == "bonus"


def test_compute_totals_with_balance_breakdown() -> None:
    rows = [
        _sample_row(value=100, balance="main"),
        _sample_row(value=200, balance="bonus", metric_id="ram", metric_name="RAM"),
    ]
    totals = compute_totals(rows)
    assert totals.total_minor == 300
    assert totals.total == 3.0
    assert totals.by_balance["main"] == 100
    assert totals.by_balance["bonus"] == 200


def test_format_grouped_report_with_child_resources() -> None:
    rows = [
        _sample_row(value=68861),
        _sample_row(
            metric_id="ram",
            metric_name="RAM",
            quantity=1523712,
            unit="MB",
            value=61623,
        ),
        _sample_row(
            resource_id="disk-1",
            resource_name="disk-for-Marcie-#1",
            resource_type="volume",
            resource_type_name="Диск",
            parent_resource_id="srv-1",
            parent_resource_name="Marcie",
            metric_id="ssd",
            metric_name="Универсальные SSD диски",
            quantity=37200,
            unit="GB*H",
            value=112276,
        ),
        _sample_row(
            resource_id="ip-1",
            resource_name="213.148.9.149",
            resource_type="floating_ip",
            resource_type_name="Публичный IP",
            parent_resource_id="srv-1",
            parent_resource_name="Marcie",
            metric_id="public_ip",
            metric_name="Публичные IP",
            value=18463,
        ),
    ]

    result = format_billing_report_by_project_response(
        rows,
        start="2026-05-01",
        end="2026-06-01",
        group=True,
    )

    assert "Отчёт за период 01.05.2026–01.06.2026" in result
    assert "Проект: Dedicated Project" in result
    assert "Продукт: Облачные серверы / Облачные серверы" in result
    assert "Объект: Marcie" in result
    assert "- vCPU: 744 item — 688,61 ₽" in result
    assert "Связанные ресурсы:" in result
    assert "disk-for-Marcie-#1" in result
    assert "213.148.9.149" in result
    assert "Итого по объекту Marcie: 2 612,23 ₽" in result
    assert "Общий итог: 2 612,23 ₽" in result


def test_format_flat_report() -> None:
    rows = [_sample_row()]
    result = format_billing_report_by_project_response(
        rows,
        start="2026-05-01",
        end="2026-06-01",
        group=False,
    )

    assert "Строка 1:" in result
    assert "Проект: Dedicated Project" in result
    assert "Объект: Marcie" in result


def test_no_data_message() -> None:
    result = format_billing_report_by_project_response(
        [],
        start="2026-05-01",
        end="2026-06-01",
    )
    assert result == "За выбранный период данных по оказанным услугам нет."


def test_no_project_placeholder() -> None:
    row = _sample_row()
    row["project_id"] = None
    row["project_name"] = None

    result = format_billing_report_by_project_response(
        [row],
        start="2026-05-01",
        end="2026-06-01",
    )

    assert "Проект: Без проекта" in result


def test_child_without_parent_in_report_shown_separately() -> None:
    rows = [
        _sample_row(
            resource_id="disk-1",
            resource_name="disk-for-Marcie-#1",
            parent_resource_id="missing-parent",
            parent_resource_name="Marcie",
            metric_id="ssd",
            metric_name="Универсальные SSD диски",
            value=112276,
        )
    ]

    result = format_billing_report_by_project_response(
        rows,
        start="2026-05-01",
        end="2026-06-01",
    )

    assert "Объект: disk-for-Marcie-#1" in result
    assert "Родительский объект: Marcie" in result


def test_parse_billing_report_422() -> None:
    import httpx

    client = SelectelClient("acc", "user", "pass")
    response = httpx.Response(
        422,
        json={
            "status": "error",
            "code": "UNPROCESSABLE_ENTITY",
            "error": {"locale": ["Missing data for required field."]},
        },
    )

    with pytest.raises(SelectelValidationError) as exc_info:
        client._parse_billing_report_response(response)

    assert "Не удалось получить отчёт: ошибка в параметрах запроса." in str(exc_info.value)
    assert "Поле locale: Missing data for required field." in str(exc_info.value)
