from __future__ import annotations

import logging

from fastapi import FastAPI

from src.core.config import Settings


LOGGER_NAME = "ecloe.api.access"


def configure_observability(app: FastAPI, settings: Settings) -> None:
    app.state.observability_enabled = settings.observability_enabled
    if not settings.observability_enabled:
        return

    logging.getLogger(LOGGER_NAME).setLevel(logging.INFO)
    _configure_opentelemetry(app, settings)


def _configure_opentelemetry(app: FastAPI, settings: Settings) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace import get_tracer_provider, set_tracer_provider
    except ModuleNotFoundError:
        app.state.telemetry_status = "opentelemetry_unavailable"
        return

    provider = get_tracer_provider()
    if provider.__class__.__module__.startswith("opentelemetry.trace"):
        provider = TracerProvider(
            resource=Resource.create({"service.name": "ecloe-engine-api"})
        )
        set_tracer_provider(provider)

    connection_string = settings.applicationinsights_connection_string
    if connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        except ModuleNotFoundError:
            app.state.telemetry_status = "applicationinsights_exporter_unavailable"
        else:
            provider.add_span_processor(
                BatchSpanProcessor(
                    AzureMonitorTraceExporter(connection_string=connection_string)
                )
            )
            app.state.telemetry_status = "applicationinsights_enabled"
    else:
        app.state.telemetry_status = "opentelemetry_enabled"

    FastAPIInstrumentor.instrument_app(app)
