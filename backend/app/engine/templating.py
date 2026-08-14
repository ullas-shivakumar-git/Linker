from jinja2.sandbox import SandboxedEnvironment

from app.engine.context import ExecutionContext

# Sandboxed specifically because this template text comes from a user's
# saved node config, not code we wrote — it must not get access to
# arbitrary Python (attribute access to dunder methods, etc.).
_env = SandboxedEnvironment()


def render_template(template_str: str, context: ExecutionContext) -> str:
    """Renders {{ nodes.<node_id>.<field> }} and {{ trigger.<field> }}."""
    template = _env.from_string(template_str)
    return template.render(nodes=context.node_outputs, trigger=context.trigger_payload)
