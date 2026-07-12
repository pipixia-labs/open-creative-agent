from contextvars import ContextVar

username_context: ContextVar[str] = ContextVar('username', default='')