"""Shared OpenTelemetry tracing setup for local eval runs."""

from __future__ import annotations

import os


def setup_foundry_tracing(service_name: str) -> bool:
    """Configure Azure AI Projects tracing to a local OTLP collector.

    Returns True when tracing is configured, False when required packages are
    unavailable so evals can still run without tracing.
    """
    try:
        from azure.core.settings import settings
        from azure.ai.projects.telemetry import AIProjectInstrumentor
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        print(f"[tracing] disabled: missing package ({exc})")
        return False

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")

    settings.tracing_implementation = "opentelemetry"
    os.environ.setdefault("AZURE_TRACING_GEN_AI_INCLUDE_BINARY_DATA", "true")

    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    AIProjectInstrumentor().instrument(enable_content_recording=True)
    print(f"[tracing] enabled (service={service_name}, endpoint={endpoint})")
    return True
